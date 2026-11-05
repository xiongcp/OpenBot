"""Feishu card.action.trigger callback adapter ignoring forged payload authority (OB-050)."""

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from openbot.application.approval_use_case import RemoteApprovalResult, RemoteApprovalUseCase

from openbot_feishu.cards import FeishuPlainCardBuilder


class FeishuApprovalCallbackHandler:
    """Extract real operator open_id from callback envelope and delegate to daemon use case."""

    def __init__(
        self,
        *,
        expected_tenant_key: str,
        expected_app_id: str,
        use_case: RemoteApprovalUseCase,
        card_builder: FeishuPlainCardBuilder | None = None,
        card_updater: Callable[[str, dict[str, Any]], bool] | None = None,
    ) -> None:
        self._tenant = expected_tenant_key
        self._app = expected_app_id
        self._use_case = use_case
        self._cards = card_builder or FeishuPlainCardBuilder()
        self._card_updater = card_updater

    def handle_callback(
        self, payload: dict[str, Any], *, simulate_db_timeout: bool = False
    ) -> RemoteApprovalResult:
        header = dict(payload.get("header") or {})
        event = dict(payload.get("event") or {})
        if header.get("tenant_key") != self._tenant or header.get("app_id") != self._app:
            return RemoteApprovalResult(
                approved=False,
                status_code="TENANT_OR_APP_MISMATCH",
                operation_state=None,
            )

        # NEVER trust action.value.is_owner or action.value.principal_id!
        operator = dict(event.get("operator") or {})
        real_open_id = str(operator.get("open_id", ""))
        action = dict(event.get("action") or {})
        val = dict(action.get("value") or {})
        event_id = str(header.get("event_id", "cb"))
        approval_id = str(val.get("approval_id", ""))
        decision = str(val.get("decision", "DENY")).upper()
        task_id = str(val.get("task_id", "tsk_remote"))
        tool_name = str(val.get("tool_name", "tool"))

        res = self._use_case.execute_remote_callback(
            operator_open_id=real_open_id,
            approval_id=approval_id,
            expected_version=int(val.get("expected_version", 0)),
            expected_binding_hash=str(val.get("expected_binding_hash", "")),
            decision=decision,
            nonce=str(val.get("nonce", "")),
            request_id=f"feishu_cb:{event_id}",
            simulate_db_timeout=simulate_db_timeout,
        )
        if res.status_code != "DECISION_RECORDED":
            return res

        resolved_card = self._cards.build_resolved_approval_card(
            approval_id=approval_id,
            task_id=task_id,
            tool_name=tool_name,
            decision=decision,
            operator_open_id=real_open_id,
        )
        callback_response: dict[str, Any] = {
            "toast": {
                "type": "success" if decision == "APPROVE" else "info",
                "content": "已批准执行" if decision == "APPROVE" else "已拒绝执行",
            },
            "card": {
                "type": "raw",
                "data": resolved_card.card_json,
            },
        }
        ctx = dict(event.get("context") or {})
        open_msg_id = str(ctx.get("open_message_id") or event.get("open_message_id") or "")
        if open_msg_id and self._card_updater is not None:
            self._card_updater(open_msg_id, resolved_card.card_json)

        return replace(
            res,
            decision=decision,
            resolved_card_json=resolved_card.card_json,
            callback_response=callback_response,
        )
