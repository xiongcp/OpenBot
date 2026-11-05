"""Pure, side-effect-free Feishu plain card builders without CardKit dependency (OB-051)."""

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class RenderedApprovalCard:
    approval_id: str
    mode: Literal["REMOTE_INTERACTIVE", "REQUIRE_LOCAL", "RESOLVED"]
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
                    "config": {"wide_screen_mode": True},
                    "header": {
                        "title": {
                            "tag": "plain_text",
                            "content": f"Approval {approval_id} (REQUIRE_LOCAL)",
                        },
                        "template": "grey",
                    },
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
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"⚠️ OpenBot 审批请求: {tool_name} ({approval_id})",
                    },
                    "template": "orange",
                },
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
                                "text": {
                                    "tag": "plain_text",
                                    "content": "✅ 批准执行 (Approve)",
                                },
                                "type": "primary",
                                "value": {
                                    "approval_id": approval_id,
                                    "task_id": task_id,
                                    "tool_name": tool_name,
                                    "expected_version": expected_version,
                                    "expected_binding_hash": binding_hash,
                                    "decision": "APPROVE",
                                    "nonce": nonce,
                                },
                            },
                            {
                                "tag": "button",
                                "text": {
                                    "tag": "plain_text",
                                    "content": "❌ 拒绝执行 (Deny)",
                                },
                                "type": "danger",
                                "value": {
                                    "approval_id": approval_id,
                                    "task_id": task_id,
                                    "tool_name": tool_name,
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

    def build_resolved_approval_card(
        self,
        *,
        approval_id: str,
        task_id: str,
        tool_name: str,
        decision: str,
        operator_open_id: str,
    ) -> RenderedApprovalCard:
        is_approved = decision.upper() == "APPROVE"
        icon = "✅" if is_approved else "❌"
        status_text = "已批准执行 (Approved)" if is_approved else "已拒绝执行 (Denied)"
        template = "green" if is_approved else "red"
        return RenderedApprovalCard(
            approval_id=approval_id,
            mode="RESOLVED",
            remote_approve_enabled=False,
            requires_cardkit=False,
            card_json={
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"{icon} {status_text} ({approval_id})",
                    },
                    "template": template,
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "plain_text",
                            "content": (
                                f"{icon} {status_text} — 任务 {task_id} / 工具 {tool_name} "
                                f"(操作人: {operator_open_id})"
                            ),
                        },
                    }
                ],
            },
        )

    def build_approval_card_v2(
        self,
        *,
        approval_id: str,
        task_id: str,
        tool_name: str,
        data_class: str,
        impact_summary: str,
        diff_lines: tuple[str, ...] = (),
        old_sha256: str | None = None,
        new_sha256: str | None = None,
        budget_used_pct: int = 0,
        expires_at_iso: str = "",
        truncated: bool = False,
        expected_version: int = 1,
        binding_hash: str = "",
        nonce: str = "",
    ) -> RenderedApprovalCard:
        """Feishu 2.0 card with collapsible Diff summary and budget progress (V1-082)."""
        if data_class in {"SENSITIVE", "SECRET"} or truncated:
            return self.build_approval_card(
                approval_id=approval_id,
                task_id=task_id,
                tool_name=tool_name,
                data_class=data_class,
                impact_summary=impact_summary,
                truncated=truncated,
                expected_version=expected_version,
                binding_hash=binding_hash,
                nonce=nonce,
            )
        base = self.build_approval_card(
            approval_id=approval_id,
            task_id=task_id,
            tool_name=tool_name,
            data_class=data_class,
            impact_summary=impact_summary,
            truncated=False,
            expected_version=expected_version,
            binding_hash=binding_hash,
            nonce=nonce,
        )
        card = dict(base.card_json)
        elements = list(card.get("elements", []))
        short_old = (old_sha256 or "none")[:8]
        short_new = (new_sha256 or "none")[:8]
        diff_preview_text = "\n".join(diff_lines[:24]) if diff_lines else "(no diff lines)"
        extra_elements: list[dict[str, Any]] = [
            {
                "tag": "collapsible_panel",
                "expanded": False,
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"📄 Diff 摘要 ({short_old} → {short_new})",
                    }
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "plain_text", "content": diff_preview_text},
                    }
                ],
            },
            {
                "tag": "div",
                "text": {
                    "tag": "plain_text",
                    "content": f"📊 预算进度: {budget_used_pct}% | 有效期至: {expires_at_iso}",
                },
            },
        ]
        card["elements"] = [elements[0], *extra_elements, *elements[1:]]
        return RenderedApprovalCard(
            approval_id=approval_id,
            mode="REMOTE_INTERACTIVE",
            remote_approve_enabled=True,
            requires_cardkit=False,
            card_json=card,
        )

    def build_stale_or_expired_card_v2(
        self,
        *,
        approval_id: str,
        task_id: str,
        tool_name: str,
        reason: Literal["EXPIRED", "TARGET_DRIFTED"],
    ) -> RenderedApprovalCard:
        return RenderedApprovalCard(
            approval_id=approval_id,
            mode="RESOLVED",
            remote_approve_enabled=False,
            requires_cardkit=False,
            card_json={
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"🛑 目标已变更或审批已过期，已为您拦截执行 ({approval_id})",
                    },
                    "template": "red",
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "plain_text",
                            "content": (
                                f"任务 {task_id} / 工具 {tool_name} 因 {reason} 被安全拦截，"
                                "请基于最新状态重新生成提案。"
                            ),
                        },
                    }
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
