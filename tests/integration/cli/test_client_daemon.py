import io
import os
import subprocess
import sys
import time
from pathlib import Path

from openbot.cli import discover_cli_session


def test_model_credentials_are_bounded_memory_input_without_echo(monkeypatch, capsys):
    from openbot.application.runtime_factory import read_model_credentials

    monkeypatch.setattr(
        sys, "stdin", io.StringIO("https://example.test/v1\nsynthetic-memory-only\n")
    )
    assert read_model_credentials() == ("https://example.test/v1", "synthetic-memory-only")
    captured = capsys.readouterr()
    assert "synthetic-memory-only" not in captured.out + captured.err


def test_daemon_client_api_restart_forgets_credentials_and_keeps_settings(tmp_path):
    profile, workspace = tmp_path / "profile", tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "demo.txt").write_text("synthetic demo")
    root = Path(__file__).resolve().parents[3]
    env = {**os.environ, "PYTHONPATH": str(root / "services/core/src")}
    base = [
        sys.executable,
        "-m",
        "openbot",
        "daemon",
        "serve",
        "--profile-dir",
        str(profile),
        "--workspace-root",
        str(workspace),
    ]

    def launch(with_credentials):
        process = subprocess.Popen(
            base + (["--model-credentials"] if with_credentials else []),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if with_credentials:
            process.stdin.write("https://example.test/v1\nsynthetic-memory-only\n")
            process.stdin.flush()
        end = time.monotonic() + 8
        while time.monotonic() < end:
            if process.poll() is not None:
                raise AssertionError(process.communicate(timeout=2)[1])
            try:
                session = discover_cli_session(profile)
                response = session.call("GET", "/v1/client/health")
                if response.status_code == 200:
                    return process, session
            except (PermissionError, ConnectionError, FileNotFoundError):
                pass
            time.sleep(0.03)
        process.terminate()
        process.communicate(timeout=5)
        raise AssertionError("Client API did not become ready")

    process, session = launch(True)
    try:
        assert session.call("GET", "/v1/client/health").json()["credentials_configured"] is True
        initial = session.call("GET", "/v1/client/settings").json()
        preview = session.call(
            "POST",
            "/v1/client/settings/preview",
            body={
                "expected_revision": initial["revision"],
                "config": initial["config"] | {"locale": "en"},
            },
        ).json()
        assert (
            session.call(
                "POST", "/v1/client/settings/apply", body=preview | {"confirm": True}
            ).status_code
            == 200
        )
        # Dropping an HTTP client does not terminate the separate daemon.
        assert process.poll() is None
    finally:
        process.terminate()
        out, err = process.communicate(timeout=8)
        assert "synthetic-memory-only" not in out + err
    process, session = launch(False)
    try:
        assert session.call("GET", "/v1/client/health").json()["credentials_configured"] is False
        assert session.call("GET", "/v1/client/settings").json()["config"]["locale"] == "en"
    finally:
        process.terminate()
        process.communicate(timeout=8)
    for path in profile.rglob("*"):
        if path.is_file():
            assert b"synthetic-memory-only" not in path.read_bytes()
