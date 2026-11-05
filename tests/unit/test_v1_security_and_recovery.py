from pathlib import Path

import pytest
from openbot.application.vertical_slice import M1VerticalSliceHarness
from openbot.policy.secrets.broker import (
    MacOSKeychainCliBackend,
    SecretBroker,
    SecretUnavailableError,
)
from openbot.tools.filesystem_guard import WorkspaceFileGuard
from openbot.tools.workspace.commit_journal import PatchCommitJournal


def test_v1_015_keychain_set_secret_uses_stdin_never_argv_and_ephemeral_memory(
    tmp_path: Path,
) -> None:
    fake_sec = tmp_path / "fake_security.sh"
    stdin_log = tmp_path / "stdin_captured.txt"
    argv_log = tmp_path / "argv_captured.txt"
    fake_sec.write_text(
        f'#!/bin/sh\necho "$@" > "{argv_log}"\ncat > "{stdin_log}"\nexit 0\n',
        encoding="utf-8",
    )
    fake_sec.chmod(0o755)

    kc = MacOSKeychainCliBackend(service_name="com.openbot.v1015", security_binary=str(fake_sec))
    canary = b"sk-v1015-secret-never-in-argv"
    kc.set_secret("keychain:provider:openai:main", canary)
    assert kc.last_argv == (str(fake_sec), "-i")
    argv_text = argv_log.read_text(encoding="utf-8")
    assert canary.decode() not in argv_text
    assert canary.hex() not in argv_text
    assert "-w" not in argv_text
    assert canary.hex() in stdin_log.read_text(encoding="utf-8")

    # Ephemeral in-memory injection works without disk fallback and clears on restart
    broken_kc = MacOSKeychainCliBackend(
        service_name="com.openbot.v1015", security_binary="/nonexistent/security"
    )
    broker = SecretBroker(broken_kc)
    ref = "keychain:provider:openai:ephemeral"
    with pytest.raises(SecretUnavailableError):
        broker.resolve_for_model_provider(ref, "openai")

    broker.inject_ephemeral_secret(ref, b"sk-ephemeral-in-ram")
    assert broker.resolve_for_model_provider(ref, "openai") == b"sk-ephemeral-in-ram"
    broker.clear_ephemeral_secrets()
    with pytest.raises(SecretUnavailableError):
        broker.resolve_for_model_provider(ref, "openai")


def test_v1_013_recover_epoch_rejects_client_boolean_and_uses_supervisor_proof(
    tmp_path: Path,
) -> None:
    harness = M1VerticalSliceHarness.create(tmp_path / "v1013")
    try:
        ses = harness.cli_session
        # 1. Client asserting old_epoch_isolated or fencing_proof is rejected with 403
        for bad_body in (
            {"new_epoch": "ep_2", "old_epoch_isolated": True},
            {"new_epoch": "ep_2", "old_epoch_isolated": "true"},
            {"new_epoch": "ep_2", "fencing_proof": "forged"},
            {"new_epoch": "ep_2", "executor_result": "SUCCEEDED"},
        ):
            resp = ses.call("POST", "/v1/runtime/recover-epoch", body=bad_body)
            assert resp.status_code == 403
            assert resp.json()["code"] == "CLIENT_ISOLATION_ASSERTION_FORBIDDEN"

        # 2. Unreclaimed container or residual worker in supervisor blocks takeover
        api = ses.transport._api  # type: ignore[attr-defined]
        api.supervisor.register_worker(
            worker_id="wrk_stuck",
            operation_id="op_1",
            attempt_id="att_1",
            pid=999999,
            pgid=999999,
            process_start_token="tok_1",
            container_id="cid_orphan_1",
        )
        api.supervisor.set_worker_recovery_fault(
            "wrk_stuck", residual_pids=(999999,), container_unreclaimable=True
        )
        blocked = ses.call("POST", "/v1/runtime/recover-epoch", body={"new_epoch": "ep_2"})
        assert blocked.status_code == 200
        assert blocked.json()["takeover_allowed"] is False
        assert blocked.json()["active_runtime_epoch"] is None

        # 3. Once supervisor isolates the worker/container, recovery succeeds
        api.supervisor.set_worker_recovery_fault(
            "wrk_stuck", residual_pids=(), container_unreclaimable=False
        )
        ok = ses.call("POST", "/v1/runtime/recover-epoch", body={"new_epoch": "ep_3"})
        assert ok.status_code == 200
        assert ok.json()["takeover_allowed"] is True
        assert ok.json()["active_runtime_epoch"] == "ep_3"
    finally:
        harness.close()


def test_v1_020_commit_journal_cross_process_reload_and_corruption_guard(
    tmp_path: Path,
) -> None:
    ws = tmp_path / "ws"
    j_root = tmp_path / "journals"
    ws.mkdir()
    j_root.mkdir()
    guard = WorkspaceFileGuard(ws)

    (ws / "a.txt").write_text("old-a\n", encoding="utf-8")
    (ws / "b.txt").write_text("old-b\n", encoding="utf-8")
    snap_a = guard.observe("a.txt")
    snap_b = guard.observe("b.txt")
    new_a = b"new-a\n"
    new_b = b"new-b\n"
    import hashlib

    jnl = PatchCommitJournal(j_root, "pbd_v1020")
    jnl.record_Backup(
        relative_path="a.txt",
        old_bytes=b"old-a\n",
        old_sha256=snap_a.sha256,
        new_sha256=hashlib.sha256(new_a).hexdigest(),
    )
    jnl.record_Backup(
        relative_path="b.txt",
        old_bytes=b"old-b\n",
        old_sha256=snap_b.sha256,
        new_sha256=hashlib.sha256(new_b).hexdigest(),
    )
    # Apply a.txt, then simulate crash before b.txt
    guard.write_atomic("a.txt", new_a, snap_a)
    jnl.mark_file_applied("a.txt")

    # Reload journal in a fresh instance across process boundary
    reloaded = PatchCommitJournal.load(jnl.journal_path)
    actions = reloaded.recover_partial_failure(guard)
    assert actions["a.txt"] == "RESTORED_ORIGINAL"
    assert actions["b.txt"] == "FAILED_NOT_APPLIED"
    assert (ws / "a.txt").read_text(encoding="utf-8") == "old-a\n"

    # Tampered or truncated journal fails closed
    bad_path = jnl.journal_path
    raw = bad_path.read_text(encoding="utf-8")
    bad_path.write_text(raw.replace("RESTORED_ORIGINAL", "APPLIED"), encoding="utf-8")
    with pytest.raises(PermissionError, match="JOURNAL_ENTRIES_DIGEST_MISMATCH"):
        PatchCommitJournal.load(bad_path)

    bad_path.write_text("{truncated", encoding="utf-8")
    with pytest.raises(PermissionError, match="JOURNAL_CORRUPTED_OR_TRUNCATED"):
        PatchCommitJournal.load(bad_path)


def test_v1_014_out_of_process_writer_sigkill_across_crash_windows(tmp_path: Path) -> None:
    harness = M1VerticalSliceHarness.create(tmp_path / "v1014")
    try:
        rep = harness.run_fault_crash_scenario("after_effect_before_receipt")
        assert rep["killed_pid"] > 0
        assert rep["post_crash_operation_state"] == "UNKNOWN"
        assert rep["blind_replay_count"] == 0
        assert rep["resolved_operation_state"] == "SUCCEEDED"
    finally:
        harness.close()
