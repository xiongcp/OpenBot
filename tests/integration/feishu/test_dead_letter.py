import json

import pytest
from openbot.application.outbox import GatewaySendResult, OutboxService
from openbot.storage.outbox import OutboxStore
from openbot_feishu.dead_letter import DeadLetterInspectorService

from tests.integration.storage.test_recovery import _deadline, recovery_env

__all__ = ["recovery_env"]


def test_dead_letter_requeues_notifications_without_rerunning_business_and_refuses_unknown(
    recovery_env,
) -> None:
    _, context, writer, inbox, _, _, _, _, _, _ = recovery_env
    store = OutboxStore(writer)
    outbox = OutboxService(writer, store)
    dlq = DeadLetterInspectorService(writer)

    task_id = json.loads(
        inbox.submit(
            context,
            "dlq-t1",
            json.dumps(
                {"workspace_id": "wsp_test1", "goal": "dlq-goal", "network_mode": "OFFLINE"}
            ),
            _deadline(),
        ).result(5)
    )["task_id"]

    # 1. Enqueue a DEAD notification and an UNKNOWN RECONCILE_ONLY record
    enq_dead = json.loads(
        writer.submit(
            outbox.enqueue(
                context,
                task_id=task_id,
                target_key="feishu:ou_1",
                target={"channel": "feishu", "open_id": "ou_1"},
                semantic_key="notify:1",
                payload={"text": "status"},
                delivery_class="UPSERT_REVISION",
                request_id="dlq-enq-1",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    claim_dead = store.claim_due(
        context,
        runtime_epoch="ep_1",
        lease_ttl_ms=5000,
        target_key="feishu:ou_1",
        request_id="dlq-c1",
        deadline_monotonic_ms=_deadline(),
    )
    assert claim_dead is not None
    writer.submit(
        outbox.complete_delivery(
            context,
            outbox_id=claim_dead.outbox_id,
            lease_token=claim_dead.lease_token,
            expected_version=claim_dead.version,
            result=GatewaySendResult(status="PERMANENT_ERROR", error_code="CARD_INVALID"),
            request_id="dlq-cmp-1",
            deadline_monotonic_ms=_deadline(),
        )
    ).result(5)

    enq_unk = json.loads(
        writer.submit(
            outbox.enqueue(
                context,
                task_id=task_id,
                target_key="feishu:ou_2",
                target={"channel": "feishu", "open_id": "ou_2"},
                semantic_key="append:1",
                payload={"text": "msg"},
                delivery_class="RECONCILE_ONLY",
                request_id="dlq-enq-2",
                deadline_monotonic_ms=_deadline(),
            )
        ).result(5)
    )
    claim_unk = store.claim_due(
        context,
        runtime_epoch="ep_1",
        lease_ttl_ms=5000,
        target_key="feishu:ou_2",
        request_id="dlq-c2",
        deadline_monotonic_ms=_deadline(),
    )
    assert claim_unk is not None
    writer.submit(
        outbox.complete_delivery(
            context,
            outbox_id=claim_unk.outbox_id,
            lease_token=claim_unk.lease_token,
            expected_version=claim_unk.version,
            result=GatewaySendResult(status="UNKNOWN", error_code="NET_DROP"),
            request_id="dlq-cmp-2",
            deadline_monotonic_ms=_deadline(),
        )
    ).result(5)

    # 2. Cross-owner cannot list dead letters
    from dataclasses import replace

    stranger_ctx = replace(context, principal_id="pri_stranger")
    with pytest.raises(PermissionError):
        dlq.list_dead_letters(stranger_ctx)

    # 3. UNKNOWN side effects CANNOT be blindly redelivered or discarded via dead-letter tools!
    with pytest.raises(PermissionError, match="UNKNOWN_REQUIRES_RECONCILE"):
        dlq.redeliver_notification(
            context,
            outbox_id=enq_unk["outbox_id"],
            request_id="dlq-bad-re",
            deadline_monotonic_ms=_deadline(),
        )
    with pytest.raises(PermissionError, match="UNKNOWN_REQUIRES_RECONCILE"):
        dlq.discard_dead_letter(
            context,
            outbox_id=enq_unk["outbox_id"],
            request_id="dlq-bad-disc",
            deadline_monotonic_ms=_deadline(),
        )

    # 4. Inspecting and redelivering a DEAD notification resets only the notification to PENDING
    items = dlq.list_dead_letters(context)
    assert len(items) == 1
    assert items[0].outbox_id == enq_dead["outbox_id"]
    assert items[0].error_code == "CARD_INVALID"

    redeliv = dlq.redeliver_notification(
        context,
        outbox_id=enq_dead["outbox_id"],
        request_id="dlq-re-1",
        deadline_monotonic_ms=_deadline(),
    )
    assert redeliv["state"] == "PENDING"
    assert redeliv["business_operation_reexecuted"] is False
