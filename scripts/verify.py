"""Run repository checks and preserve real exit codes and logs. Never runs services."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(phase="M0"):
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT / 'services/core/src'}:{ROOT / 'services/feishu_gateway/src'}"
    env["PYTHONNOUSERSITE"] = "1"
    env.pop("OPENBOT_NATIVE_TESTS", None)
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
    output = ROOT / "evidence/implementation"
    output.mkdir(exist_ok=True, parents=True)
    records = []
    for name, argv in commands:
        result = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        content = result.stdout + result.stderr
        prefix = "m1-" if phase == "M1" else ""
        path = output / (prefix + name + ".log")
        path.write_text(content)
        records.append(
            {
                "name": name,
                "command": argv,
                "exit_code": result.returncode,
                "log": str(path.relative_to(ROOT)),
                "log_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
        print(f"{name}: {'PASS' if result.returncode == 0 else 'FAIL'} ({path.relative_to(ROOT)})")
        if result.returncode:
            print(content[-5000:])
    report = {
        "phase": phase,
        "platform": [platform.system(), platform.machine()],
        "python": sys.version,
        "checks": records,
        "passed": all(r["exit_code"] == 0 for r in records),
    }
    report_name = "m1-verification.json" if phase == "M1" else "verification.json"
    (output / report_name).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("M0", "M1"), default="M0")
    raise SystemExit(run(parser.parse_args().phase))
