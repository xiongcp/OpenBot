import json

from openbot.application.approval_use_case import RemoteApprovalUseCase
from openbot.policy.pairing import PairingService
from openbot_feishu.approval_callback import FeishuApprovalCallbackHandler

from tests.integration.storage.test_recovery import _deadline, recovery_env

__all__ = ["recovery_env"]


def test_feishu_approval_callback_verifies_operator_ignores_forged_and_rejects_cancelled(
    recovery_env,
) -> None:
    _, context, writer, inbox, tasks, ops, approvals, _, _, challenges = recovery_env
    pairing = PairingService(writer)
    chal = pairing.create_local_challenge(
        profile_id="pro_test1", expected_tenant_key="ten_1", expected_app_id="app_1"
    )
    cand = pairing.submit_remote_claim(
        challenge_id=chal.challenge_id,
        code=chal.code,
        tenant_key="ten_1",
        app_id="app_1",
        open_id="ou_owner_real",
        display_name="Real Owner",
    )
    pairing.confirm_candidate_locally(
        context, cand.candidate_id, request_id="cb-pair-1", deadline_monotonic_ms=_deadline()
    )

    use_case = RemoteApprovalUseCase(
        default_context=context,
        writer=writer,
        pairing=pairing,
        approvals=approvals,
        tasks=tasks,
    )
    updated_cards: list[tuple[str, dict[str, object]]] = []

    def _record_card_update(msg_id: str, card_doc: dict[str, object]) -> bool:
        updated_cards.append((msg_id, card_doc))
        return True

    handler = FeishuApprovalCallbackHandler(
        expected_tenant_key="ten_1",
        expected_app_id="app_1",
        use_case=use_case,
        card_updater=_record_card_update,
    )

    # Create task & propose operation
    task_id = json.loads(
        inbox.submit(
            context,
            "cb-t1",
            json.dumps({"workspace_id": "wsp_test1", "goal": "cb-goal", "network_mode": "OFFLINE"}),
            _deadline(),
        ).result(5)
    )["task_id"]
    writer.submit(tasks.command(context, task_id, 0, "RUNNING", "cb-r1", _deadline())).result(5)
    proposed = json.loads(
        ops.propose(
            context,
            task_id,
            "gui.click",
            '{"arg":"btn"}',
            {"workspace_generation": 1, "files": []},
            "WORKSPACE",
            {"kind": "LOCAL", "resource_ref": context.workspace_id},
            "cb-p1",
            _deadline(),
        )
    )
    apr_id = proposed["approval_id"]
    nonce = challenges.get(apr_id).decode("utf-8")

    # 1. Forged is_owner=True in action.value from an unpaired operator is REJECTED
    forged_cb = {
        "header": {"event_id": "cb_1", "tenant_key": "ten_1", "app_id": "app_1"},
        "event": {
            "operator": {"open_id": "ou_attacker"},
            "action": {
                "value": {
                    "is_owner": True,
                    "principal_id": "pri_test1",
                    "approval_id": apr_id,
                    "expected_version": 1,
                    "expected_binding_hash": proposed["binding_hash"],
                    "decision": "APPROVE",
                    "nonce": nonce,
                }
            },
        },
    }
    res_forged = handler.handle_callback(forged_cb)
    assert res_forged.approved is False
    assert res_forged.status_code == "FORBIDDEN_OPERATOR"

    # 2. Database busy / commit failure NEVER claims approved=True
    res_busy = handler.handle_callback(forged_cb, simulate_db_timeout=True)
    assert res_busy.approved is False
    assert res_busy.status_code == "COMMIT_UNCONFIRMED"

    # 3. Real paired owner succeeds and repeat click is safely rejected without double wake
    valid_cb = {
        **forged_cb,
        "header": {"event_id": "cb_2", "tenant_key": "ten_1", "app_id": "app_1"},
        "event": {
            **forged_cb["event"],
            "operator": {"open_id": "ou_owner_real"},
            "context": {"open_message_id": "om_card_msg_1"},
        },
    }
    res_ok = handler.handle_callback(valid_cb)
    assert res_ok.approved is True
    assert res_ok.operation_state == "READY"
    assert res_ok.decision == "APPROVE"
    assert res_ok.resolved_card_json is not None
    assert all(el.get("tag") != "action" for el in res_ok.resolved_card_json["elements"])
    assert res_ok.callback_response is not None
    assert res_ok.callback_response["card"]["type"] == "raw"
    assert res_ok.callback_response["card"]["data"] == res_ok.resolved_card_json
    assert len(updated_cards) == 1
    assert updated_cards[0][0] == "om_card_msg_1"

    # 4. Old card on a CANCELLED task is rejected
    task2_id = json.loads(
        inbox.submit(
            context,
            "cb-t2",
            json.dumps(
                {"workspace_id": "wsp_test1", "goal": "cb-cancel", "network_mode": "OFFLINE"}
            ),
            _deadline(),
        ).result(5)
    )["task_id"]
    writer.submit(tasks.command(context, task2_id, 0, "RUNNING", "cb-r2", _deadline())).result(5)
    prop2 = json.loads(
        ops.propose(
            context,
            task2_id,
            "gui.click",
            '{"arg":"btn2"}',
            {"workspace_generation": 1, "files": []},
            "WORKSPACE",
            {"kind": "LOCAL", "resource_ref": context.workspace_id},
            "cb-p2",
            _deadline(),
        )
    )
    apr2_id = prop2["approval_id"]
    nonce2 = challenges.get(apr2_id).decode("utf-8")
    t2_ver = tasks.snapshot(context, task2_id)["version"]
    writer.submit(tasks.cancel(context, task2_id, t2_ver, "cb-can-2", _deadline())).result(5)

    cancelled_cb = {
        "header": {"event_id": "cb_3", "tenant_key": "ten_1", "app_id": "app_1"},
        "event": {
            "operator": {"open_id": "ou_owner_real"},
            "action": {
                "value": {
                    "approval_id": apr2_id,
                    "expected_version": 1,
                    "expected_binding_hash": prop2["binding_hash"],
                    "decision": "APPROVE",
                    "nonce": nonce2,
                }
            },
        },
    }
    res_can = handler.handle_callback(cancelled_cb)
    assert res_can.approved is False
    assert res_can.status_code == "APPROVAL_REJECTED_OR_STALE"
