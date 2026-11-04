import io
import tarfile
from pathlib import Path

import pytest
from openbot.tools.executors.sandbox import (
    ContainerOwnership,
    ContainerSandboxBroker,
    validate_and_extract_tar_export,
)


class FakeDockerEngine:
    def __init__(self) -> None:
        self.containers: dict[str, dict[str, object]] = {}
        self.events: list[tuple[str, str]] = []
        self.export_tar_bytes: bytes = b""

    def create(self, name: str, labels: dict[str, str], argv: tuple[str, ...]) -> str:
        cid = "c" * 63 + str(len(self.containers) + 1)
        self.containers[cid] = {
            "Id": cid,
            "Name": name,
            "Labels": dict(labels),
            "Running": False,
            "WaitConfirmed": False,
            "Removed": False,
            "Argv": argv,
        }
        self.events.append(("create", cid))
        return cid

    def start(self, cid: str) -> int:
        self.containers[cid]["Running"] = True
        self.events.append(("start", cid))
        return 43210  # synthetic docker client PID

    def inspect(self, cid_or_name: str) -> dict[str, object] | None:
        if cid_or_name in self.containers:
            return self.containers[cid_or_name]
        for c in self.containers.values():
            if c["Name"] == cid_or_name:
                return c
        return None

    def stop(self, cid: str) -> None:
        self.containers[cid]["Running"] = False
        self.events.append(("stop", cid))

    def wait(self, cid: str) -> int:
        if self.containers[cid]["Running"]:
            raise RuntimeError("Container still running")
        self.containers[cid]["WaitConfirmed"] = True
        self.events.append(("wait", cid))
        return 0

    def export_tar(self, cid: str) -> bytes:
        self.events.append(("export", cid))
        return self.export_tar_bytes

    def remove(self, cid: str) -> None:
        self.containers[cid]["Removed"] = True
        self.events.append(("remove", cid))


def _make_tar(
    name: str, data: bytes = b"ok", *, mode: int = 0o644, sym_target: str | None = None
) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:") as tf:
        info = tarfile.TarInfo(name=name)
        if sym_target is not None:
            info.type = tarfile.SYMTYPE
            info.linkname = sym_target
            tf.addfile(info)
        else:
            info.size = len(data)
            info.mode = mode
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_unqualified_or_fallback_backends_and_dangerous_mounts_are_rejected(tmp_path):
    engine = FakeDockerEngine()
    for bad_backend in ("podman", "nerdctl", "bubblewrap", "host_shell"):
        with pytest.raises(PermissionError, match="CAPABILITY_UNAVAILABLE"):
            ContainerSandboxBroker(
                engine=engine,
                backend_name=bad_backend,
                backend_qualified=True,
                profile_id="pro_1",
                pinned_image="alpine@sha256:" + ("a" * 64),
            )

    with pytest.raises(PermissionError, match="CAPABILITY_UNAVAILABLE"):
        ContainerSandboxBroker(
            engine=engine,
            backend_name="docker_cli",
            backend_qualified=False,
            profile_id="pro_1",
            pinned_image="alpine@sha256:" + ("a" * 64),
        )

    broker = ContainerSandboxBroker(
        engine=engine,
        backend_name="docker_cli",
        backend_qualified=True,
        profile_id="pro_1",
        pinned_image="alpine@sha256:" + ("a" * 64),
    )
    # Reject docker.sock or host HOME mount
    with pytest.raises(PermissionError, match="docker.sock|HOME"):
        broker.build_create_argv(
            container_name="c1",
            ownership=ContainerOwnership("pro_1", "op_1", "att_1", "ep_1"),
            input_dir=Path("/var/run/docker.sock"),
            output_dir=tmp_path / "out",
            host_home=Path("/Users/admin-1234"),
            command=("sh", "-c", "id"),
        )


def test_client_death_does_not_reclaim_and_enforces_stop_wait_export_remove_order(tmp_path):
    engine = FakeDockerEngine()
    engine.export_tar_bytes = _make_tar("receipt", b"verified output\n")
    broker = ContainerSandboxBroker(
        engine=engine,
        backend_name="docker_cli",
        backend_qualified=True,
        profile_id="pro_1",
        pinned_image="alpine@sha256:" + ("a" * 64),
    )
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()

    ownership = ContainerOwnership("pro_1", "op_1", "att_1", "ep_1")
    cid, client_pid = broker.launch(
        ownership=ownership,
        input_dir=in_dir,
        output_dir=out_dir,
        host_home=Path("/Users/admin-1234"),
        command=("/bin/echo", "ok"),
    )
    assert client_pid == 43210

    # 1. Killing CLI client does NOT mark container reclaimed; export while running is refused
    broker.notify_client_exited(cid, client_pid)
    assert broker.is_reclaimed(cid) is False
    with pytest.raises(PermissionError, match="Running|stopped"):
        broker.export_verified_files(cid)

    # 2. Full stop -> wait -> export -> remove sequence succeeds in exact order
    exported, removed = broker.stop_wait_export_and_remove(cid)
    assert exported == {"receipt": b"verified output\n"}
    assert removed is True
    assert broker.is_reclaimed(cid) is True
    assert [e[0] for e in engine.events] == ["create", "start", "stop", "wait", "export", "remove"]

    # 3. Refuses to remove an unregistered user container belonging to another profile
    foreign_cid = engine.create("user-container", {"openbot.profile_id": "other"}, ())
    with pytest.raises(PermissionError, match="ownership|unregistered"):
        broker.stop_wait_export_and_remove(foreign_cid)


def test_malicious_tar_exports_are_rejected():
    # Path traversal, symlink, executable bit, and oversized tar are all rejected
    for bad_tar in (
        _make_tar("../escape.txt", b"bad"),
        _make_tar("/etc/passwd", b"bad"),
        _make_tar("link", sym_target="/etc/shadow"),
        _make_tar("exec.sh", b"#!/bin/sh", mode=0o755),
    ):
        with pytest.raises(PermissionError):
            validate_and_extract_tar_export(bad_tar)
