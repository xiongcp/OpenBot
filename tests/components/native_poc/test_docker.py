import io
import json
import os
import tarfile
from pathlib import Path

import pytest

from tests.components.native_poc.docker_poc import (
    resolve_docker_cli_and_socket,
    run_poc,
    validate_receipt_tar,
)


def archive(name="receipt", content=b"synthetic receipt\n", kind=tarfile.REGTYPE):
    target = io.BytesIO()
    with tarfile.open(fileobj=target, mode="w") as tar:
        member = tarfile.TarInfo(name)
        member.type = kind
        member.uid = 65532
        member.mode = 0o644
        member.size = len(content) if kind == tarfile.REGTYPE else 0
        member.linkname = "/etc/passwd" if kind == tarfile.SYMTYPE else ""
        tar.addfile(member, io.BytesIO(content) if member.size else None)
    return target.getvalue()


def test_stopped_container_export_validates_bytes_before_writing_files():
    assert validate_receipt_tar(archive()) == b"synthetic receipt\n"


@pytest.mark.parametrize(
    "data",
    [
        archive("../../receipt"),
        archive("/receipt"),
        archive(kind=tarfile.SYMTYPE),
        archive(content=b"x" * 5000),
        b"invalid tar",
        b"x" * 65537,
    ],
)
def test_untrusted_container_export_is_rejected(data):
    with pytest.raises(ValueError):
        validate_receipt_tar(data)


def test_portable_docker_cli_and_socket_discovery_and_security_guards(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    # Layout 1: Homebrew CLI + Docker Desktop user socket
    brew_bin = tmp_path / "opt/homebrew/bin/docker"
    brew_bin.parent.mkdir(parents=True)
    brew_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    brew_bin.chmod(0o755)
    dd_sock = fake_home / ".docker/run/docker.sock"
    dd_sock.parent.mkdir(parents=True)
    dd_sock.write_text("", encoding="utf-8")

    cli1, sock1 = resolve_docker_cli_and_socket(
        home_dir=fake_home,
        cli_candidates=(brew_bin,),
    )
    assert cli1 == str(brew_bin)
    assert sock1 == f"unix://{dd_sock}"

    # Layout 2: /usr/local/bin/docker + OrbStack user socket
    dd_sock.unlink()
    orb_sock = fake_home / ".orbstack/run/docker.sock"
    orb_sock.parent.mkdir(parents=True)
    orb_sock.write_text("", encoding="utf-8")
    local_bin = tmp_path / "usr/local/bin/docker"
    local_bin.parent.mkdir(parents=True)
    local_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    local_bin.chmod(0o755)

    cli2, sock2 = resolve_docker_cli_and_socket(
        home_dir=fake_home,
        cli_candidates=(local_bin,),
    )
    assert cli2 == str(local_bin)
    assert sock2 == f"unix://{orb_sock}"

    # Reject remote tcp:// or another user's socket or missing socket
    for bad_host in (
        "tcp://192.168.1.10:2375",
        "ssh://user@remote",
        "unix:///Users/Zhuanz/.docker/run/docker.sock",
        "unix:///var/run/docker.sock",
    ):
        with pytest.raises(PermissionError, match="CAPABILITY_UNAVAILABLE"):
            resolve_docker_cli_and_socket(
                home_dir=fake_home,
                cli_candidates=(local_bin,),
                explicit_host=bad_host,
            )

    orb_sock.unlink()
    with pytest.raises(PermissionError, match="CAPABILITY_UNAVAILABLE"):
        resolve_docker_cli_and_socket(
            home_dir=fake_home,
            cli_candidates=(local_bin,),
        )


@pytest.mark.native_container
@pytest.mark.skipif(
    os.environ.get("OPENBOT_NATIVE_TESTS") != "1",
    reason="Requires explicit native Docker qualification command",
)
def test_actual_native_container_limits_and_independent_lifecycle():
    report = run_poc()
    assert report["checks"]["readonly_and_no_network"]
    assert report["checks"]["client_exit_does_not_stop_container"]
    assert report["checks"]["stop_wait_export_remove"]
    assert report["checks"]["memory_limit_enforced"]
    assert report["checks"]["pids_limit_enforced"]
    assert report["remaining_owned_containers"] == []
    path = Path(__file__).resolve().parents[3] / "evidence/implementation/native-container.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
