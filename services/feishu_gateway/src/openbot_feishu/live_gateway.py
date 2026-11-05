"""Bounded official-SDK consumer, externally supervised; credentials are memory-only."""

import argparse
import getpass
import json
import logging
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from openbot.cli import CliApiSession, discover_cli_session
from openbot.contracts import strict_json
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
    def _https_post(path: str, body: dict[str, Any], token: str) -> dict[str, Any]:
        import urllib.request

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args: Any, **kwargs: Any) -> None:
                return None

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(
            "https://open.feishu.cn" + path, json.dumps(body).encode(), headers, method="POST"
        )
        with opener.open(request, timeout=5) as response:
            return dict(strict_json(response.read(65537)))

    def acknowledge(self, message_id: str) -> None:
        if time.monotonic() >= self._expires:
            doc = self._post(
                "/open-apis/auth/v3/tenant_access_token/internal",
                {"app_id": self._app, "app_secret": self._secret},
                "",
            )
            if doc.get("code") != 0 or not doc.get("tenant_access_token"):
                raise PermissionError("FEISHU_TOKEN_UNAVAILABLE")
            self._token = str(doc["tenant_access_token"])
            self._expires = time.monotonic() + max(60, int(doc.get("expire", 0)) - 120)
        doc = self._post(
            f"/open-apis/im/v1/messages/{message_id}/reactions",
            {"reaction_type": {"emoji_type": RECEIPT_EMOJI}},
            self._token,
        )
        if doc.get("code") != 0:
            raise PermissionError("FEISHU_REACTION_REJECTED")


def forward_event(session: CliApiSession, line: bytes, reactor: Any) -> str:
    doc = dict(strict_json(line))
    message_id = doc.pop("message_id", "")
    response = session.call("POST", "/v1/feishu/events", body=doc)
    if response.status_code not in {200, 201}:
        # Do not ACK the SDK callback when durable admission failed.
        raise ConnectionError("FEISHU_INGRESS_REJECTED")
    receipt = response.json()
    if "task_id" in receipt and reactor is not None and message_id:
        try:
            reactor.acknowledge(message_id)
        except Exception:
            print("FEISHU_RECEIPT_UNAVAILABLE", flush=True)  # fixed code; no SDK/error body
    return str(receipt.get("status", "TASK_PERSISTED"))


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
        selector = selectors.DefaultSelector()
        reactor = Reactor(app_id, app_secret)
        stage, buffer = "CONNECTING", b""
        started, last_heartbeat = time.monotonic(), 0.0
        last_transport = started
        try:
            child.stdin.write(
                (json.dumps({"app_id": app_id, "app_secret": app_secret}) + "\n").encode()
            )
            child.stdin.flush()
            selector.register(child.stdout, selectors.EVENT_READ)
            while child.poll() is None:
                if time.monotonic() - started >= lifetime_seconds or not _allowed(session, app_id):
                    break
                if time.monotonic() - started > 15 and stage != "CONNECTED":
                    raise TimeoutError("FEISHU_CONNECT_DEADLINE")
                if time.monotonic() - last_transport > 180:
                    raise TimeoutError("FEISHU_TRANSPORT_HEARTBEAT_EXPIRED")
                if time.monotonic() - last_heartbeat >= 2:
                    session.call("POST", "/v1/feishu/health", body={"stage": stage})
                    last_heartbeat = time.monotonic()
                for _key, _ in selector.select(timeout=0.5):
                    chunk = os.read(child.stdout.fileno(), 16384)
                    if not chunk:
                        break
                    buffer += chunk
                    if len(buffer) > 65536:
                        raise ValueError("FEISHU_CONSUMER_OUTPUT_LIMIT")
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        if line == b"CONNECTED":
                            stage = "CONNECTED"
                            last_transport = time.monotonic()
                            print("FEISHU_CONNECTED", flush=True)
                        elif line == b"HEARTBEAT":
                            last_transport = time.monotonic()
                        elif line == b"FAILED":
                            raise ConnectionError("FEISHU_TRANSPORT_FAILED")
                        else:
                            print("FEISHU_" + forward_event(session, line, reactor), flush=True)
        finally:
            selector.close()
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

    def receive(data: Any) -> None:
        result = normalize_message(json.loads(lark.JSON.marshal(data)))
        if result:
            result["text"] = redactor.sanitize_sink(
                sink="model_input", text=result["text"], data_class="WORKSPACE"
            ).sanitized_text
            print(json.dumps(result, ensure_ascii=True), flush=True)
            # The callback completes only after the daemon confirms durable admission.
            import select

            if (
                not select.select([sys.stdin.buffer], [], [], 7)[0]
                or sys.stdin.buffer.readline(8) != b"ACK\n"
            ):
                raise RuntimeError("FEISHU_DURABLE_ADMISSION_REQUIRED")

    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(receive)
        .build()
    )
    client = lark.ws.Client(app_id, app_secret, event_handler=handler, auto_reconnect=False)
    connect = client._connect

    async def connected() -> None:
        await connect()
        print("CONNECTED", flush=True)

    client._connect = connected
    disconnect = client._disconnect

    async def disconnected() -> None:
        await disconnect()
        print("FAILED", flush=True)

    client._disconnect = disconnected
    control_frame = client._handle_control_frame

    async def transport_frame(frame: Any) -> None:
        await control_frame(frame)
        print("HEARTBEAT", flush=True)

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
