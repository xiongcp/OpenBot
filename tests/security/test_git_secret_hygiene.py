"""Repository rules must protect local credentials without relying on global Git ignores."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def ignored(path: str) -> bool:
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.excludesFile=/dev/null",
            "check-ignore",
            "--no-index",
            "--quiet",
            path,
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    assert result.returncode in {0, 1}, result.stderr.decode()
    return result.returncode == 0


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        "config/.env.feishu",
        "local/owner_cli.token",
        "local/challenges.json",
        "local/daemon_session.json",
        "local/state.sqlite",
        "local/state.sqlite-wal",
        "local/state.db",
        "local/client.pem",
        "local/client.key",
        "local/client.p12",
        "profiles/test/config.json",
        ".openbot/config.json",
    ],
)
def test_local_credentials_and_runtime_state_are_ignored(path):
    assert ignored(path), f"Repository ignore rule missing for {path}"


@pytest.mark.parametrize(
    "path",
    [
        ".env.example",
        ".env.template",
        "config.example.toml",
        "contracts/examples/task.valid.json",
        "services/core/src/openbot/policy/secrets/broker.py",
        "native/supervisor/src/credential_transport.rs",
    ],
)
def test_public_examples_and_credential_handling_source_remain_trackable(path):
    assert not ignored(path)
