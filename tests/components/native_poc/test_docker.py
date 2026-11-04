import io
import json
import os
import tarfile
from pathlib import Path

import pytest

from tests.components.native_poc.docker_poc import run_poc, validate_receipt_tar


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
