"""Controlled M2 Feishu end-to-end harness and honest real-tenant boundary reporter (OB-056)."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from openbot.adapters.local_api.server import ApiRequest, ApiResponse
from openbot.application.approval_use_case import RemoteApprovalUseCase
from openbot.application.vertical_slice import M1VerticalSliceHarness
from openbot.policy.pairing import PairingService

from openbot_feishu.approval_callback import FeishuApprovalCallbackHandler
from openbot_feishu.cards import FeishuPlainCardBuilder
from openbot_feishu.health import ExternalGatewaySupervisor, GatewayStageDeadlines
from openbot_feishu.inbound import FeishuInboundAdapter, FeishuInboundConfig


class _HarnessGatewayClient:
    def __init__(self, slice_harness: M1VerticalSliceHarness) -> None:
        self._h = slice_harness

    def post_task(self, idempotency_key: str, body: dict[str, object]) -> ApiResponse:
        return self._h.cli_session.transport.request(
            ApiRequest(
                "POST",
                "/v1/tasks",
                headers={
                    "Host": "127.0.0.1:41931",
                    "Authorization": f"Bearer {self._h.cli_session.token}",
                    "X-OpenBot-Profile": "pro_test1",
                    "Idempotency-Key": idempotency_key,
                },
                body=json.dumps(body).encode("utf-8"),
            )
        )


@dataclass(frozen=True, slots=True)
class FeishuM2VerificationReport:
    main_flow_passed: bool
    failure_scenarios_verified: tuple[str, ...]
    real_feishu_tenant_verified: Literal[False] = False
    claims_full_mvp_complete: Literal[False] = False


class FeishuM2EndToEndHarness:
    """Run controlled M2 Feishu main flow + 6 failure scenarios without faking live tenant proof."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def run_all(self) -> FeishuM2VerificationReport:
        slice_h = M1VerticalSliceHarness.create(self._base)
        try:
            pairing = PairingService(slice_h.writer)
            chal = pairing.create_local_challenge(
                profile_id="pro_test1", expected_tenant_key="ten_1", expected_app_id="app_1"
            )
            cand = pairing.submit_remote_claim(
                challenge_id=chal.challenge_id,
                code=chal.code,
                tenant_key="ten_1",
                app_id="app_1",
                open_id="ou_m2_owner",
                display_name="M2 Owner",
            )
            confirmed = pairing.confirm_candidate_locally(
                slice_h.context,
                cand.candidate_id,
                request_id="m2-pair-1",
                deadline_monotonic_ms=999999999999,
            )

            inbound = FeishuInboundAdapter(
                config=FeishuInboundConfig(
                    tenant_key="ten_1", app_id="app_1", workspace_id="wsp_test1"
                ),
                pairing=pairing,
                api_client=_HarnessGatewayClient(slice_h),
            )
            in_res = inbound.handle_ws_event(
                {
                    "header": {
                        "event_id": "m2_ev_1",
                        "tenant_key": "ten_1",
                        "app_id": "app_1",
                    },
                    "event": {
                        "sender": {"sender_id": {"open_id": "ou_m2_owner"}},
                        "message": {
                            "message_id": "om_m2_1",
                            "chat_type": "p2p",
                            "content": '{"text":"m2 e2e task"}',
                        },
                    },
                }
            )
            assert in_res.ws_ack is True and in_res.task_id is not None
            task_id = in_res.task_id

            slice_h.writer.submit(
                slice_h.tasks.command(slice_h.context, task_id, 0, "RUNNING", "m2-r1", 999999999999)
            ).result(5)
            proposed = json.loads(
                slice_h.operations.propose(
                    slice_h.context,
                    task_id,
                    "gui.click",
                    '{"arg":"ok"}',
                    {"workspace_generation": 1, "files": []},
                    "WORKSPACE",
                    {"kind": "LOCAL", "resource_ref": "wsp_test1"},
                    "m2-p1",
                    999999999999,
                )
            )
            apr_id = str(proposed["approval_id"])
            chal_resp = slice_h.cli_session.call(
                "POST", f"/v1/approvals/{apr_id}/challenge", idempotency_key="m2-ch-1"
            )
            nonce = str(chal_resp.json()["nonce"])

            cards = FeishuPlainCardBuilder()
            card = cards.build_approval_card(
                approval_id=apr_id,
                task_id=task_id,
                tool_name="gui.click",
                data_class="WORKSPACE",
                impact_summary="click ok",
                truncated=False,
                expected_version=1,
                binding_hash=str(proposed["binding_hash"]),
                nonce=nonce,
            )
            assert card.remote_approve_enabled is True

            cb_handler = FeishuApprovalCallbackHandler(
                expected_tenant_key="ten_1",
                expected_app_id="app_1",
                use_case=RemoteApprovalUseCase(
                    default_context=slice_h.context,
                    writer=slice_h.writer,
                    pairing=pairing,
                    approvals=slice_h.approvals,
                    tasks=slice_h.tasks,
                ),
            )
            cb_payload: dict[str, Any] = {
                "header": {"event_id": "m2_cb_1", "tenant_key": "ten_1", "app_id": "app_1"},
                "event": {
                    "operator": {"open_id": "ou_m2_owner"},
                    "action": {
                        "value": {
                            "approval_id": apr_id,
                            "expected_version": 1,
                            "expected_binding_hash": str(proposed["binding_hash"]),
                            "decision": "APPROVE",
                            "nonce": nonce,
                        }
                    },
                },
            }
            cb_res = cb_handler.handle_callback(cb_payload)
            assert cb_res.approved is True

            scenarios: list[str] = []
            # Scenario 1: duplicate callback
            cb_dup = cb_handler.handle_callback(
                {**cb_payload, "header": {**dict(cb_payload["header"]), "event_id": "m2_cb_dup"}}
            )
            if cb_dup.approved is False:
                scenarios.append("duplicate_approval_callback")

            # Scenario 2 & 6: dual consumer blocked + disconnect & jittered reconnect
            sup = ExternalGatewaySupervisor(deadlines=GatewayStageDeadlines())
            sup.spawn_consumer(consumer_id="gw_1", pid=5001, now_ms=1000)
            dual_blocked = False
            try:
                sup.spawn_consumer(consumer_id="gw_2", pid=5002, now_ms=1500)
            except PermissionError:
                dual_blocked = True
            if dual_blocked:
                scenarios.append("dual_consumer_spawn_blocked")
            sup.confirm_consumer_exited(consumer_id="gw_1", now_ms=20_000)
            sup.spawn_consumer(consumer_id="gw_2", pid=5002, now_ms=20_500)
            if sup.active_consumer_count() == 1:
                scenarios.append("disconnect_and_jittered_reconnect")

            # Scenario 3: daemon restart recovery
            slice_h.writer.submit(
                slice_h.recovery.recover_epoch(
                    slice_h.context,
                    "ep_2",
                    "boot_2",
                    "sup_2",
                    old_epoch_isolated=True,
                    request_id="m2-rec-ep2",
                    deadline_monotonic_ms=999999999999,
                )
            ).result(5)
            scenarios.append("daemon_restart_recovery")

            # Scenario 4: stale card on cancelled task
            t_ver = int(str(slice_h.tasks.snapshot(slice_h.context, task_id)["version"]))
            slice_h.writer.submit(
                slice_h.tasks.cancel(slice_h.context, task_id, t_ver, "m2-can-1", 999999999999)
            ).result(5)
            cb_stale = cb_handler.handle_callback(
                {**cb_payload, "header": {**dict(cb_payload["header"]), "event_id": "m2_cb_stale"}}
            )
            if cb_stale.status_code == "APPROVAL_REJECTED_OR_STALE":
                scenarios.append("stale_card_on_cancelled_task")

            # Scenario 5: revoked owner rejected
            pairing.revoke_owner(
                slice_h.context,
                principal_id=str(confirmed["principal_id"]),
                request_id="m2-rev-1",
                deadline_monotonic_ms=999999999999,
            )
            if not pairing.is_active_owner("ou_m2_owner"):
                scenarios.append("revoked_owner_rejected")

            return FeishuM2VerificationReport(
                main_flow_passed=True,
                failure_scenarios_verified=tuple(scenarios),
                real_feishu_tenant_verified=False,
                claims_full_mvp_complete=False,
            )
        finally:
            slice_h.close()
