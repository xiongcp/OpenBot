"""Bounded official-SDK consumer, externally supervised; credentials are memory-only."""

import argparse
import getpass
import json
import logging
import os
import re
import secrets
import select
import signal
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from openbot.cli import CliApiSession, discover_cli_session
from openbot.contracts import canonicalize, strict_json
from openbot.observability.redaction import RedactionPipeline


def normalize_message(payload: dict[str, Any]) -> dict[str, str] | None:
    try:
        header, event = payload["header"], payload["event"]
        message, sender = event["message"], event["sender"]
        if (
            message["chat_type"] != "p2p"
            or message["message_type"] != "text"
            or sender.get("sender_type", "user") != "user"
        ):
            return None
        content = strict_json(message["content"])
        result = {
            "event_id": header["event_id"],
            "tenant_key": header["tenant_key"],
            "app_id": header["app_id"],
            "open_id": sender["sender_id"]["open_id"],
            "chat_id": message["chat_id"],
            "text": content["text"],
            "message_id": message["message_id"],
        }
        if any(
            type(v) is not str or not v.strip() or len(v) > (4096 if k == "text" else 200)
            for k, v in result.items()
        ):
            return None
        if not re.fullmatch(r"om_[A-Za-z0-9_-]{1,196}", result["message_id"]):
            return None
        return result
    except (KeyError, TypeError, ValueError):
        return None


class ConsumerLock:
    def __init__(self, profile: Path):
        self.path = profile / "feishu-consumer.lock"
        self.fd: int | None = None

    def __enter__(self) -> "ConsumerLock":
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if nofollow is None:
            raise PermissionError("FEISHU_POSIX_PLATFORM_REQUIRED")
        self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR | nofollow, 0o600)
        try:
            import fcntl

            flock = getattr(fcntl, "flock", None)
            lock_ex = getattr(fcntl, "LOCK_EX", None)
            lock_nb = getattr(fcntl, "LOCK_NB", None)
            if flock is None or lock_ex is None or lock_nb is None:
                raise PermissionError("FEISHU_POSIX_PLATFORM_REQUIRED")
            flock(self.fd, lock_ex | lock_nb)
        except BlockingIOError:
            os.close(self.fd)
            self.fd = None
            raise PermissionError("FEISHU_CONSUMER_ALREADY_RUNNING") from None
        return self

    def __exit__(self, *_args: Any) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


RECEIPT_EMOJI = "Get"  # Feishu has no bot read receipt; a reaction is the visible equivalent.


class Reactor:
    """Best-effort receipt reaction. Called only after durable admission; secret stays in memory."""

    def __init__(self, app_id: str, app_secret: str, *, post: Any = None):
        self._app, self._secret, self._token, self._expires = app_id, app_secret, "", 0.0
        self._post = post or self._https_post

    @staticmethod
    def _https_post(
        path: str, body: dict[str, Any], token: str, method: str = "POST"
    ) -> dict[str, Any]:
        import urllib.request

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args: Any, **kwargs: Any) -> None:
                return None

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if token:
            headers["Authorization"] = "Bearer " + token
        data = json.dumps(body).encode() if body else None
        request = urllib.request.Request(
            "https://open.feishu.cn" + path, data, headers, method=method
        )
        with opener.open(request, timeout=5) as response:
            return dict(strict_json(response.read(65537)))

    def acknowledge(self, message_id: str) -> str:
        if time.monotonic() >= self._expires:
            doc = self._post(
                "/open-apis/auth/v3/tenant_access_token/internal",
                {"app_id": self._app, "app_secret": self._secret},
                "",
                "POST",
            )
            if doc.get("code") != 0 or not doc.get("tenant_access_token"):
                raise PermissionError("FEISHU_TOKEN_UNAVAILABLE")
            self._token = str(doc["tenant_access_token"])
            self._expires = time.monotonic() + max(60, int(doc.get("expire", 0)) - 120)
        doc = self._post(
            f"/open-apis/im/v1/messages/{message_id}/reactions",
            {"reaction_type": {"emoji_type": RECEIPT_EMOJI}},
            self._token,
            "POST",
        )
        if doc.get("code") != 0:
            raise PermissionError("FEISHU_REACTION_REJECTED")
        return str((doc.get("data") or {}).get("reaction_id") or "")

    def remove(self, message_id: str, reaction_id: str) -> None:
        if not message_id or not reaction_id:
            return
        if time.monotonic() >= self._expires:
            doc = self._post(
                "/open-apis/auth/v3/tenant_access_token/internal",
                {"app_id": self._app, "app_secret": self._secret},
                "",
                "POST",
            )
            if doc.get("code") != 0 or not doc.get("tenant_access_token"):
                raise PermissionError("FEISHU_TOKEN_UNAVAILABLE")
            self._token = str(doc["tenant_access_token"])
            self._expires = time.monotonic() + max(60, int(doc.get("expire", 0)) - 120)
        self._post(
            f"/open-apis/im/v1/messages/{message_id}/reactions/{reaction_id}",
            {},
            self._token,
            "DELETE",
        )


@dataclass(frozen=True)
class DurableEvent:
    event_id: str
    task_id: str
    message_id: str


def forward_event(session: CliApiSession, line: bytes) -> DurableEvent:
    """Admission only: a pairing candidate's HTTP 201 is not a durable Inbox receipt."""
    doc = dict(strict_json(line))
    message_id = doc.pop("message_id", "")
    event_id = doc.get("event_id")
    if (
        not isinstance(event_id, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", event_id)
        or not isinstance(message_id, str)
        or (message_id and not re.fullmatch(r"om_[A-Za-z0-9_-]{1,196}", message_id))
    ):
        raise ValueError("FEISHU_EVENT_INVALID")
    response = session.call("POST", "/v1/feishu/events", body=doc)
    if response.status_code not in {200, 201}:
        raise ConnectionError("FEISHU_INGRESS_REJECTED")
    receipt = response.json()
    if (
        not isinstance(receipt, dict)
        or not isinstance(receipt.get("task_id"), str)
        or not re.fullmatch(r"tsk_[A-Za-z0-9_-]{1,80}", receipt["task_id"])
        or not isinstance(receipt.get("state"), str)
        or not receipt["state"]
        or type(receipt.get("version")) is not int
        or receipt["version"] < 0
    ):
        raise ConnectionError("FEISHU_INGRESS_REJECTED")
    return DurableEvent(event_id, receipt["task_id"], message_id)


class _Presentation:
    """Single-flight, no-queue best effort. Network work never holds the state lock."""

    def __init__(self, reactor: Reactor):
        self._reactor = reactor
        self._lock = threading.Lock()
        self._busy = self._closed = False
        self._pending: dict[str, tuple[str, str]] = {}

    def _launch(self, job: Callable[[], None]) -> None:
        with self._lock:
            if self._busy or self._closed:
                return
            self._busy = True

        def run() -> None:
            try:
                job()
            except Exception:
                print("FEISHU_RECEIPT_UNAVAILABLE", flush=True)  # never SDK/error bodies
            finally:
                with self._lock:
                    self._busy = False

        threading.Thread(target=run, daemon=True, name="feishu-presentation").start()

    def task_ids(self) -> list[str]:
        with self._lock:
            return list(self._pending)

    def acknowledge(self, task_id: str, message_id: str) -> None:
        with self._lock:
            if not message_id or task_id in self._pending or len(self._pending) >= 64:
                return

        def add() -> None:
            reaction_id = self._reactor.acknowledge(message_id)
            with self._lock:
                if reaction_id and not self._closed:
                    self._pending[task_id] = (message_id, reaction_id)

        self._launch(add)

    def finish(self, finished: dict[str, Any]) -> None:
        with self._lock:
            selected = [tid for tid in self._pending if tid in finished]
        if not selected:
            return

        def remove() -> None:
            for task_id in selected:
                with self._lock:
                    message_id, reaction_id = self._pending.pop(task_id)
                try:
                    self._reactor.remove(message_id, reaction_id)
                except Exception:
                    print("FEISHU_RECEIPT_UNAVAILABLE", flush=True)

        self._launch(remove)

    def close(self) -> None:
        # Cleanup may be skipped if a job is stuck. Never join a presentation network call.
        self.finish(dict.fromkeys(self.task_ids()))
        with self._lock:
            self._closed = True


def _write_frame(fd: int, frame: bytes, deadline: float) -> None:
    """The caller owns a nonblocking pipe and serializes writers."""
    while frame:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([], [fd], [], remaining)[1]:
            raise TimeoutError("FEISHU_PIPE_WRITE_DEADLINE")
        try:
            written = os.write(fd, frame)
        except BlockingIOError:
            continue
        if not written:
            raise ConnectionError("FEISHU_PIPE_CLOSED")
        frame = frame[written:]


class _CallbackProtocol:
    """One reader per worker; callback-local IDs also fence late ACKs for redeliveries."""

    def __init__(self, input_fd: int, output_fd: int):
        self._input, self._output = input_fd, output_fd
        os.set_blocking(input_fd, False)
        os.set_blocking(output_fd, False)
        self._callbacks, self._writes = threading.Lock(), threading.Lock()
        self._buffer = b""

    def emit(self, frame: bytes, deadline: float | None = None) -> None:
        deadline = deadline if deadline is not None else time.monotonic() + 7
        if len(frame) > 65536 or not frame.endswith(b"\n"):
            raise ValueError("FEISHU_CONSUMER_OUTPUT_LIMIT")
        if not self._writes.acquire(timeout=max(0, deadline - time.monotonic())):
            raise TimeoutError("FEISHU_PIPE_WRITE_DEADLINE")
        try:
            _write_frame(self._output, frame, deadline)
        finally:
            self._writes.release()

    def read_frame(self, deadline: float) -> bytes | None:
        """One guardian-side frame from the consumer; None means the pipe reached EOF."""
        while b"\n" not in self._buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("FEISHU_FRAME_DEADLINE")
            if not select.select([self._input], [], [], remaining)[0]:
                continue
            try:
                chunk = os.read(self._input, min(4096, 65537 - len(self._buffer)))
            except BlockingIOError:
                continue
            if not chunk:
                return None
            self._buffer += chunk
            if len(self._buffer) > 65536:
                raise ValueError("FEISHU_CONSUMER_OUTPUT_LIMIT")
        line, self._buffer = self._buffer.split(b"\n", 1)
        return line

    def receive(self, event: dict[str, str]) -> None:
        deadline = time.monotonic() + 7
        if not self._callbacks.acquire(timeout=max(0, deadline - time.monotonic())):
            raise RuntimeError("FEISHU_DURABLE_ADMISSION_REQUIRED")
        try:
            callback_id = secrets.token_hex(16)
            frame = {"type": "event", "callback_id": callback_id, "event": event}
            self.emit((json.dumps(frame, ensure_ascii=True) + "\n").encode(), deadline)
            expected = {"type": "ack", "event_id": event["event_id"], "callback_id": callback_id}
            while time.monotonic() < deadline:
                if b"\n" in self._buffer:
                    line, self._buffer = self._buffer.split(b"\n", 1)
                    if strict_json(line) == expected:
                        return
                    # A stale/different ACK cannot extend the original deadline.
                    continue
                if len(self._buffer) >= 512:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([self._input], [], [], remaining)[0]:
                    break
                chunk = os.read(self._input, 512 - len(self._buffer))
                if not chunk:
                    break
                self._buffer += chunk
        except (OSError, ValueError, TimeoutError):
            raise RuntimeError("FEISHU_DURABLE_ADMISSION_REQUIRED") from None
        finally:
            self._callbacks.release()
        raise RuntimeError("FEISHU_DURABLE_ADMISSION_REQUIRED")


def _allowed(session: CliApiSession, app_id: str) -> bool:
    response = session.call("GET", "/v1/feishu/config")
    if response.status_code != 200:
        return False
    doc = response.json()
    return bool(doc.get("connect_allowed") and doc.get("app_id") == app_id)


def supervise(
    session: CliApiSession,
    profile: Path,
    app_id: str,
    app_secret: str,
    *,
    spawn: Any = subprocess.Popen,
    lifetime_seconds: int = 1800,
) -> None:
    if not _allowed(session, app_id):
        raise PermissionError("FEISHU_DISABLED_OR_OFFLINE")
    with ConsumerLock(profile) as lock:
        # Source paths support the checked-out CLI; no proxy/credential env is inherited.
        env = {"PATH": os.defpath, "PYTHONPATH": os.pathsep.join(str(p) for p in sys.path if p)}
        child = spawn(
            [sys.executable, "-m", "openbot_feishu.live_gateway", "--worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
            pass_fds=(lock.fd,),
        )
        protocol = _CallbackProtocol(child.stdout.fileno(), child.stdin.fileno())
        presentation = _Presentation(Reactor(app_id, app_secret))
        stage = "CONNECTING"
        started, last_heartbeat = time.monotonic(), 0.0
        last_transport = started
        try:
            child.stdin.write(
                (json.dumps({"app_id": app_id, "app_secret": app_secret}) + "\n").encode()
            )
            child.stdin.flush()
            while child.poll() is None:
                now = time.monotonic()
                if now - started >= lifetime_seconds or not _allowed(session, app_id):
                    break
                if now - started > 15 and stage != "CONNECTED":
                    raise TimeoutError("FEISHU_CONNECT_DEADLINE")
                if now - last_transport > 180:
                    raise TimeoutError("FEISHU_TRANSPORT_HEARTBEAT_EXPIRED")
                if now - last_heartbeat >= 2:
                    body: dict[str, Any] = {"stage": stage}
                    if tracked := presentation.task_ids():
                        body["task_ids"] = tracked
                    try:
                        resp = session.call("POST", "/v1/feishu/health", body=body)
                        if resp.status_code == 200:
                            presentation.finish(dict(resp.json().get("finished", {})))
                    except Exception:
                        print("FEISHU_HEALTH_UNAVAILABLE", flush=True)
                    last_heartbeat = time.monotonic()
                try:
                    frame = protocol.read_frame(time.monotonic() + 0.5)
                except TimeoutError:
                    continue
                if frame is None:
                    break
                if frame == b"CONNECTED":
                    stage = "CONNECTED"
                    last_transport = time.monotonic()
                    print("FEISHU_CONNECTED", flush=True)
                elif frame == b"HEARTBEAT":
                    last_transport = time.monotonic()
                elif frame == b"FAILED":
                    raise ConnectionError("FEISHU_TRANSPORT_FAILED")
                else:
                    report = dict(strict_json(frame))
                    callback_id, event_doc = report.get("callback_id"), report.get("event")
                    if (
                        report.get("type") != "event"
                        or not isinstance(callback_id, str)
                        or not re.fullmatch(r"[0-9a-f]{32}", callback_id)
                        or not isinstance(event_doc, dict)
                    ):
                        raise ValueError("FEISHU_CONSUMER_FRAME_INVALID")
                    durable = forward_event(session, canonicalize(event_doc))
                    protocol.emit(
                        canonicalize(
                            {
                                "type": "ack",
                                "event_id": durable.event_id,
                                "callback_id": callback_id,
                            }
                        )
                        + b"\n",
                        time.monotonic() + 1,
                    )
                    presentation.acknowledge(durable.task_id, durable.message_id)
                    print("FEISHU_EVENT_PERSISTED", flush=True)
        finally:
            presentation.close()
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            child.stdout.close()
            child.stdin.close()
            session.call("POST", "/v1/feishu/health", body={"stage": "STOPPED"})


def _worker() -> None:
    # SDK raw URLs, exception bodies and callback payloads never reach ordinary logs.
    logging.disable(logging.CRITICAL)
    alarm = getattr(signal, "alarm", None)
    if alarm is not None:
        alarm(1800)
    config = strict_json(sys.stdin.buffer.readline(4096))
    app_id, app_secret = config["app_id"], config["app_secret"]
    import lark_oapi as lark  # type: ignore[import-not-found]
    import lark_oapi.ws.client as sdk_ws  # type: ignore[import-not-found]
    import requests  # type: ignore[import-untyped]

    redactor = RedactionPipeline(registered_secrets=(app_secret,))
    http = requests.Session()
    http.trust_env = False

    def discovery(url: str, **kwargs: Any) -> Any:
        if url != "https://open.feishu.cn/callback/ws/endpoint":
            raise PermissionError("FEISHU_DISCOVERY_URL_FORBIDDEN")
        response = http.post(url, **kwargs, timeout=(3, 5), allow_redirects=False, stream=True)
        data = bytearray()
        for chunk in response.iter_content(8192):
            data.extend(chunk)
            if len(data) > 262144:
                response.close()
                raise ValueError("FEISHU_DISCOVERY_LIMIT")
        response.close()
        response._content = bytes(data)
        return response

    sdk_ws.requests = SimpleNamespace(post=discovery)
    protocol = _CallbackProtocol(sys.stdin.fileno(), sys.stdout.fileno())

    def receive(data: Any) -> None:
        result = normalize_message(json.loads(lark.JSON.marshal(data)))
        if result:
            result["text"] = redactor.sanitize_sink(
                sink="model_input", text=result["text"], data_class="WORKSPACE"
            ).sanitized_text
            # The callback completes only after the guardian confirms a durable Inbox receipt.
            protocol.receive(result)

    def marker(frame: bytes) -> None:
        protocol.emit(frame)

    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(receive)
        .build()
    )
    client = lark.ws.Client(app_id, app_secret, event_handler=handler, auto_reconnect=False)
    connect = client._connect

    async def connected() -> None:
        await connect()
        marker(b"CONNECTED\n")

    client._connect = connected
    disconnect = client._disconnect

    async def disconnected() -> None:
        await disconnect()
        marker(b"FAILED\n")

    client._disconnect = disconnected
    control_frame = client._handle_control_frame

    async def transport_frame(frame: Any) -> None:
        await control_frame(frame)
        marker(b"HEARTBEAT\n")

    client._handle_control_frame = transport_frame
    try:
        client.start()
    finally:
        http.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Feishu memory-only gateway / 飞书内存凭据网关")
    parser.add_argument("--profile-dir", type=Path)
    parser.add_argument("--app-id")
    parser.add_argument("--secret-stdin", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.worker:
            _worker()
            return 0
        if args.profile_dir is None or not args.app_id:
            raise ValueError("FEISHU_PROFILE_AND_APP_REQUIRED")
        profile = args.profile_dir.resolve(strict=True)
        owner = discover_cli_session(profile)
        if owner is None:
            raise PermissionError("DAEMON_REQUIRED")
        response = owner.call("POST", "/v1/client/feishu/configure", body={"app_id": args.app_id})
        if response.status_code != 200:
            raise PermissionError("FEISHU_SETUP_REJECTED")
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if nofollow is None:
            raise PermissionError("FEISHU_POSIX_PLATFORM_REQUIRED")
        fd = os.open(profile / "feishu_gateway.token", os.O_RDONLY | nofollow)
        try:
            mode = os.fstat(fd)
            if not stat.S_ISREG(mode.st_mode) or mode.st_mode & 0o077:
                raise PermissionError("FEISHU_TOKEN_PERMISSIONS")
            token = os.read(fd, 1025).decode().strip()
            if not token or len(token) > 1024:
                raise ValueError("FEISHU_TOKEN_INVALID")
        finally:
            os.close(fd)
        session = CliApiSession(owner.profile_id, token, owner.transport, owner.host)
        del owner
        secret = (
            sys.stdin.readline(2049).rstrip("\r\n")
            if args.secret_stdin
            else getpass.getpass("飞书 App Secret / Feishu App Secret: ")
        )
        if not secret or len(secret) > 2048:
            raise ValueError("FEISHU_SECRET_REQUIRED")

        def stop(_signal: int, _frame: Any) -> None:
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, stop)
        supervise(session, profile, args.app_id, secret)
        return 0
    except (Exception, KeyboardInterrupt):
        print("FEISHU_GATEWAY_STOPPED_OR_FAILED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
