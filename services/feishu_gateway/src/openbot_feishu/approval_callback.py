"""Feishu card.action.trigger callback adapter ignoring forged payload authority (OB-050)."""

from typing import Any

from openbot.application.approval_use_case import RemoteApprovalResult, RemoteApprovalUseCase


class FeishuApprovalCallbackHandler:
    """Extract real operator open_id from callback envelope and delegate to daemon use case."""

    def __init__(
        self,
        *,
        expected_tenant_key: str,
        expected_app_id: str,
        use_case: RemoteApprovalUseCase,
    ) -> None:
        self._tenant = expected_tenant_key
        self._app = expected_app_id
        self._use_case = use_case

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

        return self._use_case.execute_remote_callback(
            operator_open_id=real_open_id,
            approval_id=str(val.get("approval_id", "")),
            expected_version=int(val.get("expected_version", 0)),
            expected_binding_hash=str(val.get("expected_binding_hash", "")),
            decision=str(val.get("decision", "DENY")),
            nonce=str(val.get("nonce", "")),
            request_id=f"feishu_cb:{event_id}",
            simulate_db_timeout=simulate_db_timeout,
        )
