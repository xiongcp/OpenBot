"""Pure, side-effect-free Feishu plain card builders without CardKit dependency (OB-051)."""

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class RenderedApprovalCard:
    approval_id: str
    mode: Literal["REMOTE_INTERACTIVE", "REQUIRE_LOCAL"]
    remote_approve_enabled: bool
    requires_cardkit: Literal[False]
    card_json: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RenderedResultCard:
    task_id: str
    operation_id: str
    state: str
    reconciliation_required: bool
    card_json: dict[str, Any]


class FeishuPlainCardBuilder:
    """Construct plain Feishu cards. Forces REQUIRE_LOCAL when sensitive or truncated."""

    def build_approval_card(
        self,
        *,
        approval_id: str,
        task_id: str,
        tool_name: str,
        data_class: str,
        impact_summary: str,
        truncated: bool,
        expected_version: int,
        binding_hash: str,
        nonce: str,
    ) -> RenderedApprovalCard:
        if data_class in {"SENSITIVE", "SECRET"} or truncated:
            return RenderedApprovalCard(
                approval_id=approval_id,
                mode="REQUIRE_LOCAL",
                remote_approve_enabled=False,
                requires_cardkit=False,
                card_json={
                    "header": {"title": f"Approval {approval_id} (REQUIRE_LOCAL)"},
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "plain_text",
                                "content": (
                                    f"Task {task_id} / Tool {tool_name}: impact is {data_class} "
                                    "or truncated. Review and approve via local CLI/Desktop."
                                ),
                            },
                        }
                    ],
                },
            )

        return RenderedApprovalCard(
            approval_id=approval_id,
            mode="REMOTE_INTERACTIVE",
            remote_approve_enabled=True,
            requires_cardkit=False,
            card_json={
                "header": {"title": f"Approve {tool_name} ({approval_id})"},
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "plain_text", "content": impact_summary},
                    },
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": "Approve"},
                                "value": {
                                    "approval_id": approval_id,
                                    "expected_version": expected_version,
                                    "expected_binding_hash": binding_hash,
                                    "decision": "APPROVE",
                                    "nonce": nonce,
                                },
                            },
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": "Deny"},
                                "value": {
                                    "approval_id": approval_id,
                                    "expected_version": expected_version,
                                    "expected_binding_hash": binding_hash,
                                    "decision": "DENY",
                                    "nonce": nonce,
                                },
                            },
                        ],
                    },
                ],
            },
        )

    def build_result_card(
        self,
        *,
        task_id: str,
        operation_id: str,
        state: str,
        summary: str,
    ) -> RenderedResultCard:
        rec_req = state == "UNKNOWN"
        status_badge = "RECONCILIATION_REQUIRED (UNKNOWN)" if rec_req else state
        return RenderedResultCard(
            task_id=task_id,
            operation_id=operation_id,
            state=state,
            reconciliation_required=rec_req,
            card_json={
                "header": {"title": f"Task {task_id} [{status_badge}]"},
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "plain_text",
                            "content": f"Operation {operation_id}: {summary}",
                        },
                    }
                ],
            },
        )
