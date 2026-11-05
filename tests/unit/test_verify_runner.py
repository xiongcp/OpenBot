import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_verify_module():
    spec = importlib.util.spec_from_file_location("verify_script", ROOT / "scripts/verify.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_verify_runner_isolates_runs_captures_timeouts_and_fails_closed(tmp_path: Path) -> None:
    mod = _load_verify_module()
    assert hasattr(mod, "run_verification")
    assert hasattr(mod, "validate_verification_report")

    out_root = tmp_path / "verify_runs"

    # 1. Passing run produces run-scoped directory, source_sha, lockfile_sha256, and COMPLETE status
    code_ok, rep_ok_path = mod.run_verification(
        phase="M0",
        output_root=out_root,
        run_id="run_pass_1",
        commands_override=[("fast-ok", [sys.executable, "-c", "print('ok')"])],
        timeout_seconds=5,
    )
    assert code_ok == 0
    rep_ok = json.loads(rep_ok_path.read_text(encoding="utf-8"))
    assert rep_ok["run_id"] == "run_pass_1"
    assert rep_ok["status"] == "COMPLETE"
    assert rep_ok["passed"] is True
    assert len(rep_ok["source_sha"]) == 40
    assert len(rep_ok["lockfile_sha256"]) == 64
    assert mod.validate_verification_report(
        rep_ok_path, expected_run_id="run_pass_1", expected_source_sha=rep_ok["source_sha"]
    )

    # 2. Subsequent failing/timeout run does NOT overwrite run_pass_1 and records TIMEOUT cleanly
    code_to, rep_to_path = mod.run_verification(
        phase="M0",
        output_root=out_root,
        run_id="run_timeout_2",
        commands_override=[
            ("slow-timeout", [sys.executable, "-c", "import time; time.sleep(2)"]),
            ("after-timeout", [sys.executable, "-c", "print('still recorded')"]),
        ],
        timeout_seconds=0.1,
    )
    assert code_to == 1
    assert rep_ok_path.is_file()
    rep_to = json.loads(rep_to_path.read_text(encoding="utf-8"))
    assert rep_to["run_id"] == "run_timeout_2"
    assert rep_to["status"] == "COMPLETE"
    assert rep_to["passed"] is False
    assert rep_to["checks"][0]["timed_out"] is True
    assert rep_to["checks"][0]["status"] == "TIMEOUT"
    assert rep_to["checks"][0]["exit_code"] is None

    # 3. Stale run_id, wrong source_sha, or IN_PROGRESS report must fail validation
    with pytest.raises(PermissionError, match="VERIFICATION_RUN_ID_MISMATCH"):
        mod.validate_verification_report(
            rep_ok_path, expected_run_id="run_timeout_2", expected_source_sha=rep_ok["source_sha"]
        )
    with pytest.raises(PermissionError, match="VERIFICATION_SOURCE_SHA_MISMATCH"):
        mod.validate_verification_report(
            rep_ok_path, expected_run_id="run_pass_1", expected_source_sha="0" * 40
        )
    with pytest.raises(PermissionError, match="VERIFICATION_NOT_PASSED"):
        mod.validate_verification_report(
            rep_to_path, expected_run_id="run_timeout_2", expected_source_sha=rep_to["source_sha"]
        )

    in_progress_path = out_root / "in_progress.json"
    in_progress_path.write_text(
        json.dumps(
            {
                "run_id": "run_ip",
                "status": "IN_PROGRESS",
                "passed": False,
                "source_sha": rep_ok["source_sha"],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(PermissionError, match="VERIFICATION_INCOMPLETE"):
        mod.validate_verification_report(
            in_progress_path, expected_run_id="run_ip", expected_source_sha=rep_ok["source_sha"]
        )
