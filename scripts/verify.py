"""Run repository checks and preserve real exit codes and logs. Never runs services."""

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import stat
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAX_REPORT_BYTES = 1024 * 1024
MAX_LOG_BYTES = 16 * 1024 * 1024


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
    output.mkdir(exist_ok=False, parents=True)

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


def _read_evidence(path: Path, limit: int, kind: str) -> bytes:
    """Read bounded regular-file bytes without following a final symlink or blocking on a FIFO."""
    nofollow, nonblock = getattr(os, "O_NOFOLLOW", None), getattr(os, "O_NONBLOCK", None)
    if nofollow is None or nonblock is None:
        raise PermissionError(f"VERIFICATION_{kind}_GUARDS_UNAVAILABLE")
    try:
        with os.fdopen(os.open(path, os.O_RDONLY | nofollow | nonblock), "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise PermissionError(f"VERIFICATION_{kind}_INVALID_FILE")
            content = stream.read(limit + 1)
            if len(content) > limit:
                raise PermissionError(f"VERIFICATION_{kind}_TOO_LARGE")
            return content
    except OSError as exc:
        raise PermissionError(f"VERIFICATION_{kind}_UNREADABLE: {path}") from exc


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate report key")
        result[key] = value
    return result


def _completed_interval(record: dict[str, Any]) -> tuple[datetime, datetime]:
    try:
        start = datetime.strptime(record["started_at"], "%Y-%m-%dT%H:%M:%SZ")
        end = datetime.strptime(record["ended_at"], "%Y-%m-%dT%H:%M:%SZ")
    except (KeyError, TypeError, ValueError) as exc:
        raise PermissionError("VERIFICATION_INCOMPLETE_TIMESTAMPS") from exc
    if end < start:
        raise PermissionError("VERIFICATION_INCOMPLETE_TIMESTAMPS")
    return start, end


def validate_verification_report(
    report_path: Path,
    *,
    expected_run_id: str,
    expected_source_sha: str,
    expected_phase: str = "M0",
    expected_tree_sha: str | None = None,
    expected_lockfile_sha256: str | None = None,
    expected_commands: Sequence[tuple[str, list[str]]] | None = None,
) -> bool:
    """Validate development evidence, not release artifacts or a dirty-worktree snapshot.

    Expectations must come from the caller, never from the report being validated.
    Defaults bind the candidate commit's tree, the current checkout's lockfile, and
    the fixed phase commands using this interpreter. Synthetic runner tests must
    explicitly supply expected_commands; production qualification must omit it.
    """
    try:
        doc = json.loads(
            _read_evidence(report_path, MAX_REPORT_BYTES, "REPORT").decode("utf-8"),
            object_pairs_hook=_unique_keys,
        )
    except (ValueError, RecursionError) as exc:
        raise PermissionError("VERIFICATION_REPORT_INVALID") from exc
    if not isinstance(doc, dict):
        raise PermissionError("VERIFICATION_REPORT_INVALID")
    if doc.get("status") != "COMPLETE":
        raise PermissionError(f"VERIFICATION_INCOMPLETE: status={doc.get('status')}")
    if doc.get("run_id") != expected_run_id:
        raise PermissionError(
            f"VERIFICATION_RUN_ID_MISMATCH: expected {expected_run_id}, got {doc.get('run_id')}"
        )
    if (
        not re.fullmatch(r"[0-9a-f]{40}", expected_source_sha)
        or doc.get("source_sha") != expected_source_sha
    ):
        raise PermissionError(
            f"VERIFICATION_SOURCE_SHA_MISMATCH: {expected_source_sha} != {doc.get('source_sha')}"
        )
    if expected_phase not in ("M0", "M1") or doc.get("phase") != expected_phase:
        raise PermissionError("VERIFICATION_PHASE_MISMATCH")
    tree_sha = (
        _git_rev(f"{expected_source_sha}^{{tree}}")
        if expected_tree_sha is None
        else expected_tree_sha
    )
    lock_sha = (
        hashlib.sha256(_read_evidence(ROOT / "uv.lock", MAX_LOG_BYTES, "LOCKFILE")).hexdigest()
        if expected_lockfile_sha256 is None
        else expected_lockfile_sha256
    )
    for field, expected, length in (
        ("tree_sha", tree_sha, 40),
        ("lockfile_sha256", lock_sha, 64),
    ):
        if not re.fullmatch(rf"[0-9a-f]{{{length}}}", expected) or doc.get(field) != expected:
            raise PermissionError(f"VERIFICATION_{field.upper()}_MISMATCH")
    start, end = _completed_interval(doc)
    checks = doc.get("checks")
    if doc.get("passed") is not True or not checks:
        raise PermissionError("VERIFICATION_NOT_PASSED")
    commands = (
        list(expected_commands)
        if expected_commands is not None
        else _default_commands(expected_phase)
    )
    expected_by_name = dict(commands)
    if not commands or len(expected_by_name) != len(commands):
        raise PermissionError("VERIFICATION_CHECK_SET_MISMATCH")
    if not isinstance(checks, list) or any(
        not isinstance(chk, dict) or not isinstance(chk.get("name"), str) for chk in checks
    ):
        raise PermissionError("VERIFICATION_CHECK_SET_MISMATCH")
    names = [chk["name"] for chk in checks]
    if len(names) != len(expected_by_name) or set(names) != set(expected_by_name):
        raise PermissionError("VERIFICATION_CHECK_SET_MISMATCH")
    prefix = "m1-" if expected_phase == "M1" else ""
    for chk in checks:
        name = chk["name"]
        if chk.get("command") != expected_by_name[name]:
            raise PermissionError(f"VERIFICATION_COMMAND_MISMATCH: {name}")
        if (
            type(chk.get("exit_code")) is not int
            or chk["exit_code"] != 0
            or chk.get("timed_out") is not False
            or chk.get("status") != "PASS"
        ):
            raise PermissionError(f"VERIFICATION_CHECK_FAILED: {name}")
        check_start, check_end = _completed_interval(chk)
        if not start <= check_start <= check_end <= end:
            raise PermissionError(f"VERIFICATION_INCOMPLETE_TIMESTAMPS: {name}")
        log = chk.get("log")
        if not isinstance(log, str):
            raise PermissionError(f"VERIFICATION_LOG_PATH_MISMATCH: {name}")
        # Runner paths are either repository-relative or absolute for external output roots.
        log_path = Path(log) if Path(log).is_absolute() else ROOT / log
        expected_log = report_path.absolute().parent / f"{prefix}{name}.log"
        if log_path != expected_log:
            raise PermissionError(f"VERIFICATION_LOG_PATH_MISMATCH: {name}")
        digest = hashlib.sha256(_read_evidence(log_path, MAX_LOG_BYTES, "LOG")).hexdigest()
        if chk.get("log_sha256") != digest:
            raise PermissionError(f"VERIFICATION_LOG_HASH_MISMATCH: {name}")
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
