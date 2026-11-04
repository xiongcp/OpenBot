import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

pytest.importorskip("openai", reason="M1 SDK group absent from M0")
ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.sdk


@pytest.mark.parametrize(
    ("probe", "code"), [("imports", 0), ("network-canary", 4), ("process-canary", 4)]
)
def test_probe_catches_canaries_without_real_credentials(tmp_path, probe, code):
    env = {
        "PATH": os.defpath,
        "HOME": str(tmp_path),
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(ROOT / "services/core/src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests/components/probes/deny_io.py"), probe],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == code, result.stderr
    report = json.loads(result.stdout)
    assert bool(report["violations"]) == bool(code)


def test_probe_does_not_treat_every_workspace_file_as_an_approved_import(tmp_path):
    env = {
        "PATH": os.defpath,
        "HOME": str(tmp_path),
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(ROOT / "services/core/src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    with TemporaryDirectory(dir=ROOT, prefix=".probe-canary-") as directory:
        target = Path(directory) / "synthetic-private-file"
        target.write_text("synthetic-do-not-read")
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tests/components/probes/deny_io.py"),
                "file-canary",
                str(target),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
    assert result.returncode == 4, result.stderr
    assert json.loads(result.stdout)["violations"]
    assert "synthetic-do-not-read" not in result.stdout
