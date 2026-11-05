"""Run repository checks and preserve real exit codes and logs. Never runs services."""

import argparse
import hashlib
import json
import os
import platform
import secrets
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _git_rev(rev: str) -> str:
    res = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--verify", rev],
        capture_output=True,
        text=True,
        check=False,
    )
    return res.stdout.strip() if res.returncode == 0 else "unknown"


def _default_commands(phase: str) -> list[tuple[str, list[str]]]:
    return [
        ("unit-contract-protocol", [sys.executable, "-m", "pytest", "-q"]),
        ("lint", [sys.executable, "-m", "ruff", "check"]),
        ("format", [sys.executable, "-m", "ruff", "format", "--check"]),
        ("types", [sys.executable, "-m", "mypy"]),
        ("components", [sys.executable, "scripts/check_components.py", phase]),
        ("design", [sys.executable, "validation/verify_design.py"]),
        ("design-components", [sys.executable, "validation/verify_components.py"]),
        ("database-design", [sys.executable, "validation/verify_database.py"]),
    ]


def _decode_stream(data: str | bytes | None) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


def run_verification(
    phase: str = "M0",
    *,
    output_root: Path | None = None,
    run_id: str | None = None,
    commands_override: Sequence[tuple[str, list[str]]] | None = None,
    timeout_seconds: float = 60.0,
) -> tuple[int, Path]:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT / 'services/core/src'}:{ROOT / 'services/feishu_gateway/src'}"
    env["PYTHONNOUSERSITE"] = "1"
    env.pop("OPENBOT_NATIVE_TESTS", None)

    commands = (
        list(commands_override) if commands_override is not None else _default_commands(phase)
    )
    effective_run_id = (
        run_id or f"run_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{secrets.token_hex(4)}"
    )
    base_out = output_root or Path(
        os.environ.get("OPENBOT_VERIFY_OUTPUT_DIR", str(ROOT / "evidence/implementation/runs"))
    )
    output = base_out / effective_run_id
    output.mkdir(exist_ok=True, parents=True)

    source_sha = _git_rev("HEAD^{commit}")
    tree_sha = _git_rev("HEAD^{tree}")
    lockfile_sha256 = hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest()
    started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    report_name = "m1-verification.json" if phase == "M1" else "verification.json"
    report_path = output / report_name
    in_progress_doc: dict[str, Any] = {
        "run_id": effective_run_id,
        "status": "IN_PROGRESS",
        "phase": phase,
        "source_sha": source_sha,
        "tree_sha": tree_sha,
        "lockfile_sha256": lockfile_sha256,
        "started_at": started_at,
        "ended_at": None,
        "platform": [platform.system(), platform.machine()],
        "python": sys.version,
        "checks": [],
        "passed": False,
    }
    report_path.write_text(
        json.dumps(in_progress_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    records: list[dict[str, Any]] = []
    prefix = "m1-" if phase == "M1" else ""
    for name, argv in commands:
        cmd_start = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        path = output / (prefix + name + ".log")
        timed_out = False
        exit_code: int | None = None
        try:
            result = subprocess.run(
                argv,
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            content = result.stdout + result.stderr
            exit_code = result.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            content = (
                _decode_stream(exc.stdout)
                + _decode_stream(exc.stderr)
                + f"\n[TIMEOUT after {timeout_seconds}s]\n"
            )
        cmd_end = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        path.write_text(content, encoding="utf-8")
        status = "TIMEOUT" if timed_out else ("PASS" if exit_code == 0 else "FAIL")
        try:
            rel_log = str(path.relative_to(ROOT))
        except ValueError:
            rel_log = str(path)
        records.append(
            {
                "name": name,
                "command": argv,
                "started_at": cmd_start,
                "ended_at": cmd_end,
                "timeout_seconds": timeout_seconds,
                "timed_out": timed_out,
                "exit_code": exit_code,
                "status": status,
                "log": rel_log,
                "log_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
        print(f"{name}: {status} ({rel_log})")
        if status != "PASS":
            print(content[-5000:])

    ended_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    passed = bool(records) and all(
        r["exit_code"] == 0 and not r["timed_out"] and r["status"] == "PASS" for r in records
    )
    report = {
        "run_id": effective_run_id,
        "status": "COMPLETE",
        "phase": phase,
        "source_sha": source_sha,
        "tree_sha": tree_sha,
        "lockfile_sha256": lockfile_sha256,
        "started_at": started_at,
        "ended_at": ended_at,
        "platform": [platform.system(), platform.machine()],
        "python": sys.version,
        "checks": records,
        "passed": passed,
    }
    tmp_path = output / (report_name + ".tmp")
    tmp_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_path, report_path)
    return (0 if passed else 1), report_path


def validate_verification_report(
    report_path: Path, *, expected_run_id: str, expected_source_sha: str
) -> bool:
    if not report_path.is_file():
        raise PermissionError(f"VERIFICATION_REPORT_MISSING: {report_path}")
    doc = json.loads(report_path.read_text(encoding="utf-8"))
    if doc.get("status") != "COMPLETE":
        raise PermissionError(f"VERIFICATION_INCOMPLETE: status={doc.get('status')}")
    if doc.get("run_id") != expected_run_id:
        raise PermissionError(
            f"VERIFICATION_RUN_ID_MISMATCH: expected {expected_run_id}, got {doc.get('run_id')}"
        )
    if doc.get("source_sha") != expected_source_sha:
        raise PermissionError(
            f"VERIFICATION_SOURCE_SHA_MISMATCH: {expected_source_sha} != {doc.get('source_sha')}"
        )
    checks = doc.get("checks", [])
    if not doc.get("passed") or not checks:
        raise PermissionError("VERIFICATION_NOT_PASSED")
    for chk in checks:
        if chk.get("exit_code") != 0 or chk.get("timed_out") is not False:
            raise PermissionError(f"VERIFICATION_CHECK_FAILED: {chk.get('name')}")
    return True


def run(
    phase: str = "M0",
    *,
    output_dir: Path | None = None,
    run_id: str | None = None,
    timeout_seconds: float = 60.0,
) -> int:
    code, _ = run_verification(
        phase=phase,
        output_root=output_dir,
        run_id=run_id,
        timeout_seconds=timeout_seconds,
    )
    return code


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("M0", "M1"), default="M0")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    args = parser.parse_args()
    raise SystemExit(
        run(
            args.phase,
            output_dir=args.output_dir,
            run_id=args.run_id,
            timeout_seconds=args.timeout_seconds,
        )
    )
