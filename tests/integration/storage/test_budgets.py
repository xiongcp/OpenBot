import hashlib
import json
import time
from concurrent.futures import Future

import pytest
from openbot.application.budgets import (
    BudgetService,
    OfflineVocabularyEstimator,
    TaskBudgetPolicy,
)
from openbot.application.runtime_budget import RuntimeBudget
from openbot.application.state_machine import TaskStateService
from openbot.contracts import SchemaRegistry
from openbot.storage.inbox import InboundContext, Inbox
from openbot.storage.migrate import connect, load_migrations, migrate
from openbot.storage.writer import Writer

from tests.integration.storage.test_migrations import ROOT


def _deadline() -> int:
    return int(time.monotonic() * 1000) + 5000


@pytest.fixture
def budget_env(tmp_path):
    path = tmp_path / "budgets.sqlite"
    migrate(path, load_migrations(ROOT / "db/migrations"))
    db = connect(path)
    try:
        db.execute("INSERT INTO policy_revisions VALUES(1,?,'{}',1000,1000)", ("a" * 64,))
        db.execute(
            "INSERT INTO runtime_instances("
            "runtime_epoch,boot_id,supervisor_ref,state,started_at,heartbeat_at) "
            "VALUES('ep_1','boot_1','sup_1','ACTIVE',1000,1000)"
        )
        db.execute(
            "INSERT INTO profile_config("
            "singleton,profile_id,schema_version,policy_version,identity_epoch,"
            "privacy_mode,active_runtime_epoch,last_fencing_token,created_at,updated_at) "
            "VALUES(1,'pro_test1',1,1,1,'OFFLINE','ep_1',0,1000,1000)"
        )
        db.execute(
            "INSERT INTO principals(principal_id,role,status,display_name,created_at) "
            "VALUES('pri_test1','OWNER','ACTIVE','synthetic owner',1000)"
        )
        db.execute(
            "INSERT INTO workspaces("
            "workspace_id,root_ref,generation,status,version,created_at,updated_at) "
            "VALUES('wsp_test1','synthetic-workspace',1,'ACTIVE',0,1000,1000)"
        )
        db.execute(
            "INSERT INTO sessions(session_id,owner_id,workspace_id,status,created_at,updated_at) "
            "VALUES('ses_test1','pri_test1','wsp_test1','OPEN',1000,1000)"
        )
    finally:
        db.close()

    context = InboundContext(
        "pro_test1", "pri_test1", 1, "local", "tenant1", "app1", "ses_test1", "wsp_test1"
    )
    registry = SchemaRegistry.from_directory(ROOT / "contracts")
    writer = Writer(path)
    inbox = Inbox(writer, registry)
    tasks = TaskStateService(writer)
    budgets = BudgetService(writer)
    try:
        yield path, context, writer, inbox, tasks, budgets
    finally:
        writer.close()


@pytest.mark.parametrize(
    "receipt",
    [
        b'{"admitted":false}',
        b"{}",
        b"[]",
        b'{"admitted":1}',
        b'{"admitted":"true"}',
        b'{"admitted":true,"admitted":false}',
        b"not-json",
    ],
)
def test_runtime_budget_requires_explicit_admission_receipt(budget_env, monkeypatch, receipt):
    _, context, writer, _, _, _ = budget_env
    result = Future()
    result.set_result(receipt)
    # Fault injection at the durable writer boundary, not a substitute budget implementation.
    monkeypatch.setattr(writer, "submit", lambda _: result)
    with pytest.raises(PermissionError, match="^BUDGET_ADMISSION_DENIED$"):
        RuntimeBudget(writer, context, "tsk_synthetic").reserve("request", 500)


def test_reserve_settle_unknown_retention_and_pause_on_exhaustion(budget_env):
    path, context, writer, inbox, tasks, budgets = budget_env
    payload = json.dumps(
        {"workspace_id": "wsp_test1", "goal": "budget-ledger", "network_mode": "OFFLINE"}
    )
    task_id = json.loads(inbox.submit(context, "evt-bdg-1", payload, _deadline()).result(5))[
        "task_id"
    ]
    writer.submit(tasks.command(context, task_id, 0, "RUNNING", "run-bdg-1", _deadline())).result(5)

    policy = TaskBudgetPolicy(
        max_steps=5,
        max_model_calls=3,
        max_tool_calls=3,
        max_retries_per_call=1,
        max_duration_ms=60_000,
        max_single_artifact_bytes=1024,
        max_total_artifact_bytes=2048,
    )
    writer.submit(
        budgets.configure_limits(
            context,
            task_id,
            amount_limit_micros=1000,
            token_limit=500,
            policy=policy,
            request_id="cfg-bdg-1",
            deadline_monotonic_ms=_deadline(),
        )
    ).result(5)

    # 1. Call 1: reserve 400 micros / 200 tokens, then settle actual 350 micros / 180 tokens
    r1 = json.loads(
        writer.submit(
            budgets.reserve(
                context,
                task_id,
                call_ref="model_req_1:try_1",
                kind="MODEL",
                reserved_amount_micros=400,
                reserved_tokens=200,
                estimated_tokens=150,
                attempt_index=1,
                request_id="res-bdg-1",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    assert r1["admitted"] is True
    s1 = json.loads(
        writer.submit(
            budgets.settle(
                context,
                task_id,
                call_ref="model_req_1:try_1",
                actual_amount_micros=350,
                actual_tokens=180,
                estimated_tokens=150,
                request_id="set-bdg-1",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    assert s1["status"] == "SETTLED"
    assert s1["usage_delta_tokens"] == 30

    # 2. Call 2 (429/503/stream cut): reserve 400 micros / 200 tokens, then mark UNKNOWN.
    # Unknown cost MUST remain held in reserved_amount_micros/tokens_reserved (never zeroed on cut!)
    r2 = json.loads(
        writer.submit(
            budgets.reserve(
                context,
                task_id,
                call_ref="model_req_2:try_1",
                kind="MODEL",
                reserved_amount_micros=400,
                reserved_tokens=200,
                estimated_tokens=160,
                attempt_index=1,
                request_id="res-bdg-2",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    assert r2["admitted"] is True
    u2 = json.loads(
        writer.submit(
            budgets.mark_unknown(
                context,
                task_id,
                call_ref="model_req_2:try_1",
                reason="stream_cut_after_first_chunk",
                request_id="unk-bdg-2",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    assert u2["status"] == "UNKNOWN"
    snap = budgets.snapshot(context, task_id)
    # Spent = 350, Reserved (held by UNKNOWN) = 400, Remaining = 250
    assert snap["amount_spent_micros"] == 350
    assert snap["amount_reserved_micros"] == 400
    assert snap["tokens_spent"] == 180
    assert snap["tokens_reserved"] == 200

    # 3. Call 3 requests 300 micros (> remaining 250) -> rejected, Task enters PAUSED
    r3 = json.loads(
        writer.submit(
            budgets.reserve(
                context,
                task_id,
                call_ref="model_req_2:try_2",
                kind="MODEL",
                reserved_amount_micros=300,
                reserved_tokens=100,
                attempt_index=2,
                request_id="res-bdg-3-exhausted",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    assert r3["admitted"] is False
    assert r3["task_state"] == "PAUSED"
    assert "BUDGET_EXHAUSTED" in r3["reason"]
    assert tasks.snapshot(context, task_id)["state"] == "PAUSED"


def test_circuit_breaker_on_repeated_proposals_and_errors_and_cancel_blocks_reserve(budget_env):
    path, context, writer, inbox, tasks, budgets = budget_env
    payload = json.dumps(
        {"workspace_id": "wsp_test1", "goal": "budget-breaker", "network_mode": "OFFLINE"}
    )
    task_id = json.loads(inbox.submit(context, "evt-bdg-2", payload, _deadline()).result(5))[
        "task_id"
    ]
    writer.submit(tasks.command(context, task_id, 0, "RUNNING", "run-bdg-2", _deadline())).result(5)

    policy = TaskBudgetPolicy(
        max_repeated_proposals=2,
        max_consecutive_errors=2,
        max_idle_turns=2,
    )
    writer.submit(
        budgets.configure_limits(
            context,
            task_id,
            amount_limit_micros=10_000,
            token_limit=10_000,
            policy=policy,
            request_id="cfg-bdg-2",
            deadline_monotonic_ms=_deadline(),
        )
    ).result(5)

    # Same proposal fingerprint twice trips the runaway proposal circuit breaker -> PAUSED
    t1 = json.loads(
        writer.submit(
            budgets.record_turn_activity(
                context,
                task_id,
                proposal_fingerprint="fp_same_tool_args",
                request_id="turn-1",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    assert t1["tripped"] is False
    t2 = json.loads(
        writer.submit(
            budgets.record_turn_activity(
                context,
                task_id,
                proposal_fingerprint="fp_same_tool_args",
                request_id="turn-2",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    assert t2["tripped"] is True
    assert t2["task_state"] == "PAUSED"
    assert t2["reason"] == "CIRCUIT_BREAKER:REPEATED_PROPOSAL"
    assert tasks.snapshot(context, task_id)["state"] == "PAUSED"

    # Owner resets circuit breaker and increases budget to resume PAUSED -> QUEUED -> RUNNING
    cur_ver = int(tasks.snapshot(context, task_id)["version"])
    resumed = json.loads(
        writer.submit(
            budgets.resume_paused(
                context,
                task_id,
                expected_version=cur_ver,
                additional_amount_micros=1000,
                additional_tokens=1000,
                reset_circuit_breaker=True,
                request_id="resume-bdg-2",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    assert resumed["state"] == "QUEUED"
    writer.submit(
        tasks.command(
            context, task_id, int(resumed["version"]), "RUNNING", "run-again", _deadline()
        )
    ).result(5)

    # Cancel the task; subsequent budget reserve MUST be refused immediately
    ver_before_cancel = int(tasks.snapshot(context, task_id)["version"])
    writer.submit(
        tasks.cancel(context, task_id, ver_before_cancel, "can-bdg-2", _deadline())
    ).result(5)
    with pytest.raises(PermissionError, match="cancelled|RUNNING"):
        writer.submit(
            budgets.reserve(
                context,
                task_id,
                call_ref="model_req_after_cancel",
                kind="MODEL",
                reserved_amount_micros=100,
                reserved_tokens=50,
                request_id="res-after-cancel",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)


def test_offline_vocabulary_estimator_verifies_hash_and_never_claims_exact_for_unknown_models(
    tmp_path,
):
    vocab_file = tmp_path / "o200k_base.tiktoken"
    vocab_bytes = b"dGVzdA== 0\ndG9rZW4= 1\n"
    vocab_file.write_bytes(vocab_bytes)
    vocab_hash = hashlib.sha256(vocab_bytes).hexdigest()

    estimator = OfflineVocabularyEstimator(
        model_encodings={"gpt-4o-mini": ("o200k_base", vocab_file, vocab_hash)}
    )
    # 1. Known model with verified offline vocabulary succeeds offline with framing margin
    known_est = estimator.estimate("gpt-4o-mini", "hello world", tool_count=2)
    assert known_est.encoding_name == "o200k_base"
    assert known_est.vocab_sha256 == vocab_hash
    assert known_est.exact_billing_guaranteed is False
    assert known_est.estimated_tokens < known_est.conservative_reserved_tokens
    # A verified asset is not a tokenizer: multibyte text must still use a byte bound.
    unicode_est = estimator.estimate(
        "gpt-4o-mini", "预算界限" * 1000, tool_count=2, completion_reserve_tokens=256
    )
    assert unicode_est.estimated_tokens < 12000
    assert unicode_est.conservative_reserved_tokens >= 12000 + 256 + 80
    assert unicode_est.exact_billing_guaranteed is False

    # 2. Unknown model never pretends OpenAI tokenizer is exact; uses conservative upper bound
    unknown_est = estimator.estimate("claude-sonnet-4", "hello world", tool_count=1)
    assert unknown_est.encoding_name == "conservative_utf8_bound"
    assert unknown_est.vocab_sha256 is None
    assert unknown_est.exact_billing_guaranteed is False

    # 3. Missing or tampered offline vocabulary fails closed without network download
    bad_estimator = OfflineVocabularyEstimator(
        model_encodings={"gpt-4o-mini": ("o200k_base", tmp_path / "missing.tiktoken", vocab_hash)}
    )
    with pytest.raises(ValueError, match="CAPABILITY_UNAVAILABLE"):
        bad_estimator.estimate("gpt-4o-mini", "hello world")
