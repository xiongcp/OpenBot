import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_console_pytest_and_python_m_pytest_collect_identically_without_pythonpath() -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("OPENBOT_NATIVE_TESTS", None)

    pytest_bin = Path(sys.executable).with_name("pytest")
    res_console = subprocess.run(
        [str(pytest_bin), "--collect-only", "-q"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    res_module = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert res_console.returncode == 0, res_console.stdout + res_console.stderr
    assert res_module.returncode == 0, res_module.stdout + res_module.stderr

    console_items = [
        line.strip()
        for line in res_console.stdout.splitlines()
        if "::" in line and not line.startswith(("SKIPPED", "ERROR", "="))
    ]
    module_items = [
        line.strip()
        for line in res_module.stdout.splitlines()
        if "::" in line and not line.startswith(("SKIPPED", "ERROR", "="))
    ]
    assert len(console_items) >= 300
    assert console_items == module_items
