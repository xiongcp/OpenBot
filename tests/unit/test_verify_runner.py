import hashlib
import importlib.util
import json
import os
import subprocess
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
    synthetic_commands = [("fast-ok", [sys.executable, "-c", "print('ok')"])]
    code_ok, rep_ok_path = mod.run_verification(
        phase="M0",
        output_root=out_root,
        run_id="run_pass_1",
        commands_override=synthetic_commands,
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
        rep_ok_path,
        expected_run_id="run_pass_1",
        expected_source_sha=rep_ok["source_sha"],
        expected_commands=synthetic_commands,
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


def test_same_run_id_cannot_replace_failure(tmp_path: Path) -> None:
    mod = _load_verify_module()
    code, report = mod.run_verification(
        output_root=tmp_path,
        run_id="fixed",
        commands_override=[("probe", [sys.executable, "-c", "raise SystemExit(1)"])],
    )
    assert code == 1
    original = {path.name: path.read_bytes() for path in report.parent.iterdir()}
    with pytest.raises(FileExistsError):
        mod.run_verification(
            output_root=tmp_path,
            run_id="fixed",
            commands_override=[("probe", [sys.executable, "-c", "print('ok')"])],
        )
    assert {path.name: path.read_bytes() for path in report.parent.iterdir()} == original
    code, new_report = mod.run_verification(
        output_root=tmp_path,
        commands_override=[("probe", [sys.executable, "-c", "print('ok')"])],
    )
    assert code == 0
    assert new_report.parent != report.parent
    assert {path.name: path.read_bytes() for path in report.parent.iterdir()} == original


def _candidate() -> dict[str, str]:
    def rev(value: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "--verify", value], text=True
        ).strip()

    return {
        "source_sha": rev("HEAD^{commit}"),
        "tree_sha": rev("HEAD^{tree}"),
        "lockfile_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
    }


def _production_report(tmp_path: Path, phase: str = "M0"):
    """Synthetic validator fixture, not evidence that production commands ran."""
    commands = [
        ("unit-contract-protocol", [sys.executable, "-m", "pytest", "-q"]),
        ("lint", [sys.executable, "-m", "ruff", "check"]),
        ("format", [sys.executable, "-m", "ruff", "format", "--check"]),
        ("types", [sys.executable, "-m", "mypy"]),
        ("components", [sys.executable, "scripts/check_components.py", phase]),
        ("design", [sys.executable, "validation/verify_design.py"]),
        ("design-components", [sys.executable, "validation/verify_components.py"]),
        ("database-design", [sys.executable, "validation/verify_database.py"]),
    ]
    output = tmp_path / "fixture"
    output.mkdir()
    candidate = _candidate()
    doc = {
        "run_id": "fixture",
        "status": "COMPLETE",
        "phase": phase,
        **candidate,
        "started_at": "2026-11-05T00:00:00Z",
        "ended_at": "2026-11-05T00:00:01Z",
        "passed": True,
        "checks": [],
    }
    for name, argv in commands:
        log = output / f"{'m1-' if phase == 'M1' else ''}{name}.log"
        log.write_bytes(f"synthetic log for {name}\n".encode())
        doc["checks"].append(
            {
                "name": name,
                "command": argv,
                "started_at": doc["started_at"],
                "ended_at": doc["ended_at"],
                "exit_code": 0,
                "timed_out": False,
                "status": "PASS",
                "log": str(log),
                "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
            }
        )
    report = output / ("m1-verification.json" if phase == "M1" else "verification.json")
    report.write_text(json.dumps(doc), encoding="utf-8")
    return _load_verify_module(), report, doc, candidate


def _validate(mod, report, candidate, **kwargs):
    return mod.validate_verification_report(
        report, expected_run_id="fixture", expected_source_sha=candidate["source_sha"], **kwargs
    )


def test_complete_production_report_validates(tmp_path: Path) -> None:
    mod, report, _, candidate = _production_report(tmp_path)
    assert _validate(mod, report, candidate)


@pytest.mark.parametrize("damage", ["tamper", "missing", "directory", "symlink", "oversized"])
def test_report_rejects_invalid_log_bytes(tmp_path: Path, damage: str) -> None:
    mod, report, doc, candidate = _production_report(tmp_path)
    log = Path(doc["checks"][0]["log"])
    content = log.read_bytes()
    log.unlink()
    if damage == "tamper":
        log.write_bytes(b"different bytes\n")
    elif damage == "directory":
        log.mkdir()
    elif damage == "symlink":
        target = tmp_path / "outside.log"
        target.write_bytes(content)
        log.symlink_to(target)
    elif damage == "oversized":
        with log.open("wb") as stream:
            stream.truncate(64 * 1024 * 1024)
        doc["checks"][0]["log_sha256"] = hashlib.sha256(log.read_bytes()).hexdigest()
        report.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(PermissionError, match="VERIFICATION_LOG"):
        _validate(mod, report, candidate)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="Requires POSIX FIFO")
def test_report_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    mod, report, doc, candidate = _production_report(tmp_path)
    log = Path(doc["checks"][0]["log"])
    log.unlink()
    os.mkfifo(log)
    # A subprocess deadline makes regressions that block on FIFO observable, not a hung suite.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import runpy, sys; "
            "mod = runpy.run_path(sys.argv[1]); "
            "mod['validate_verification_report']("
            "__import__('pathlib').Path(sys.argv[2]), expected_run_id='fixture', "
            "expected_source_sha=sys.argv[3])",
            str(ROOT / "scripts/verify.py"),
            str(report),
            candidate["source_sha"],
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode != 0
    assert "PermissionError: VERIFICATION_LOG" in result.stderr


@pytest.mark.parametrize("damage", ["missing", "duplicate", "extra", "renamed", "empty"])
def test_report_requires_exact_check_set(tmp_path: Path, damage: str) -> None:
    mod, report, doc, candidate = _production_report(tmp_path)
    if damage == "missing":
        doc["checks"].pop()
    elif damage == "duplicate":
        doc["checks"][-1] = doc["checks"][0].copy()
    elif damage == "extra":
        doc["checks"].append({**doc["checks"][0], "name": "unexpected"})
    elif damage == "renamed":
        doc["checks"][0]["name"] = "unexpected"
    else:
        doc["checks"] = []
    report.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(PermissionError):
        _validate(mod, report, candidate)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("phase", "M1"),
        ("phase", "RELEASE"),
        ("source_sha", "0" * 40),
        ("tree_sha", "0" * 40),
        ("tree_sha", None),
        ("lockfile_sha256", "0" * 64),
        ("lockfile_sha256", None),
        ("status", "IN_PROGRESS"),
        ("ended_at", None),
        ("ended_at", "2026-11-04T00:00:00Z"),
        ("passed", "true"),
    ],
)
def test_report_requires_completed_matching_candidate(tmp_path: Path, field, value) -> None:
    mod, report, doc, candidate = _production_report(tmp_path)
    doc[field] = value
    report.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(PermissionError):
        _validate(mod, report, candidate)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("command", [sys.executable, "-c", "print('not qualification')"]),
        ("command", ["/another/python", "-m", "pytest", "-q"]),
        ("command", None),
        ("status", "FAIL"),
        ("exit_code", False),
        ("timed_out", 0),
        ("ended_at", None),
        ("log_sha256", "0" * 64),
        ("log_sha256", None),
    ],
)
def test_report_requires_matching_successful_check(tmp_path: Path, field, value) -> None:
    mod, report, doc, candidate = _production_report(tmp_path)
    doc["checks"][0][field] = value
    report.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(PermissionError):
        _validate(mod, report, candidate)


def test_report_cannot_borrow_other_run_log(tmp_path: Path) -> None:
    mod, report, doc, candidate = _production_report(tmp_path)
    log = Path(doc["checks"][0]["log"])
    other = tmp_path / log.name
    other.write_bytes(log.read_bytes())
    doc["checks"][0]["log"] = str(other)
    report.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(PermissionError, match="VERIFICATION_LOG"):
        _validate(mod, report, candidate)


@pytest.mark.parametrize("content", ["{", "null", "[]", '{"checks": null}', "\udcff"])
def test_invalid_report_load_fails_closed(tmp_path: Path, content: str) -> None:
    mod, report, _, candidate = _production_report(tmp_path)
    report.write_bytes(content.encode("utf-8", errors="surrogatepass"))
    with pytest.raises(PermissionError):
        _validate(mod, report, candidate)


def test_override_cannot_qualify_as_production(tmp_path: Path) -> None:
    mod = _load_verify_module()
    code, report = mod.run_verification(
        output_root=tmp_path,
        run_id="fixture",
        commands_override=[("probe", [sys.executable, "-c", "print('ok')"])],
    )
    assert code == 0
    with pytest.raises(PermissionError):
        _validate(mod, report, _candidate())


@pytest.mark.parametrize("phase", ["M0", "M1"])
def test_explicit_candidate_and_phase_validate(tmp_path: Path, phase: str) -> None:
    mod, report, _, candidate = _production_report(tmp_path, phase)
    assert _validate(
        mod,
        report,
        candidate,
        expected_phase=phase,
        expected_tree_sha=candidate["tree_sha"],
        expected_lockfile_sha256=candidate["lockfile_sha256"],
    )


@pytest.mark.parametrize(
    ("expectation", "value"),
    [
        ("expected_phase", "M1"),
        ("expected_tree_sha", "0" * 40),
        ("expected_lockfile_sha256", "0" * 64),
        ("expected_commands", [("different", [sys.executable, "-c", "print('ok')"])]),
        ("expected_commands", []),
    ],
)
def test_explicit_expectations_are_not_taken_from_report(
    tmp_path: Path, expectation, value
) -> None:
    mod, report, _, candidate = _production_report(tmp_path)
    with pytest.raises(PermissionError):
        _validate(mod, report, candidate, **{expectation: value})


def test_m1_component_command_must_match_phase(tmp_path: Path) -> None:
    mod, report, doc, candidate = _production_report(tmp_path, "M1")
    doc["checks"][4]["command"][-1] = "M0"
    report.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(PermissionError, match="VERIFICATION_COMMAND_MISMATCH"):
        _validate(mod, report, candidate, expected_phase="M1")


def test_synthetic_m1_run_requires_explicit_commands(tmp_path: Path) -> None:
    mod = _load_verify_module()
    commands = [("probe", [sys.executable, "-c", "print('ok')"])]
    code, report = mod.run_verification(
        phase="M1", output_root=tmp_path, run_id="fixture", commands_override=commands
    )
    assert code == 0
    assert _validate(mod, report, _candidate(), expected_phase="M1", expected_commands=commands)
    with pytest.raises(PermissionError):
        _validate(
            mod,
            report,
            _candidate(),
            expected_phase="M1",
            expected_commands=[("probe", [sys.executable, "-c", "print('different')"])],
        )


@pytest.mark.parametrize("checks", [None, {}, [None], [{"name": []}]])
def test_malformed_check_structure_fails_closed(tmp_path: Path, checks) -> None:
    mod, report, doc, candidate = _production_report(tmp_path)
    doc["checks"] = checks
    report.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(PermissionError):
        _validate(mod, report, candidate)


def test_duplicate_json_keys_fail_closed(tmp_path: Path) -> None:
    mod, report, doc, candidate = _production_report(tmp_path)
    report.write_text('{"passed": false, ' + json.dumps(doc)[1:], encoding="utf-8")
    with pytest.raises(PermissionError):
        _validate(mod, report, candidate)


def test_missing_report_fails_closed(tmp_path: Path) -> None:
    mod, report, _, candidate = _production_report(tmp_path)
    report.unlink()
    with pytest.raises(PermissionError):
        _validate(mod, report, candidate)


@pytest.mark.parametrize("damage", ["symlink", "oversized"])
def test_report_itself_must_be_bounded_regular_file(tmp_path: Path, damage: str) -> None:
    mod, report, _, candidate = _production_report(tmp_path)
    if damage == "symlink":
        target = tmp_path / "outside.json"
        report.rename(target)
        report.symlink_to(target)
    else:
        with report.open("ab") as stream:
            stream.write(b" " * (2 * 1024 * 1024))
    with pytest.raises(PermissionError):
        _validate(mod, report, candidate)
