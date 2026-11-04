"""Single-consumer Feishu WebSocket inbound adapter with persist-before-ACK semantics (OB-049)."""

import json
import time
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from openbot.adapters.local_api.server import ApiResponse
from openbot.policy.pairing import PairingService


class GatewayDaemonClientPort(Protocol):
    def post_task(self, idempotency_key: str, body: dict[str, object]) -> ApiResponse: ...


@dataclass(frozen=True, slots=True)
class FeishuInboundConfig:
    tenant_key: str
    app_id: str
    workspace_id: str
    allow_group_chat: bool = False
    max_attachment_bytes: int = 10_485_760


@dataclass(frozen=True, slots=True)
class InboundEventOutcome:
    ws_ack: bool
    task_id: str | None
    rejection_code: str | None
    ack_latency_ms: int
    llm_waited_in_callback: Literal[False] = False


class FeishuInboundAdapter:
    """Normalize Feishu WS events, enforce guards, and ACK only after Inbox commit."""

    def __init__(
        self,
        *,
        config: FeishuInboundConfig,
        pairing: PairingService,
        api_client: GatewayDaemonClientPort,
    ) -> None:
        self._cfg = config
        self._pairing = pairing
        self._client = api_client

    def handle_ws_event(self, payload: dict[str, Any]) -> InboundEventOutcome:
        t0 = time.monotonic()
        header = dict(payload.get("header") or {})
        event = dict(payload.get("event") or {})
        event_id = str(header.get("event_id", ""))
        tenant_key = str(header.get("tenant_key", ""))
        app_id = str(header.get("app_id", ""))

        if tenant_key != self._cfg.tenant_key or app_id != self._cfg.app_id:
            return InboundEventOutcome(
                ws_ack=True,
                task_id=None,
                rejection_code="TENANT_OR_APP_MISMATCH",
                ack_latency_ms=int((time.monotonic() - t0) * 1000),
            )

        msg = dict(event.get("message") or {})
        chat_type = str(msg.get("chat_type", "p2p"))
        if chat_type != "p2p" and not self._cfg.allow_group_chat:
            return InboundEventOutcome(
                ws_ack=True,
                task_id=None,
                rejection_code="GROUP_CHAT_DISABLED",
                ack_latency_ms=int((time.monotonic() - t0) * 1000),
            )

        sender = dict(event.get("sender") or {})
        sender_id = dict(sender.get("sender_id") or {})
        open_id = str(sender_id.get("open_id", ""))
        if not open_id or not self._pairing.is_active_owner(open_id):
            return InboundEventOutcome(
                ws_ack=True,
                task_id=None,
                rejection_code="UNPAIRED_SENDER",
                ack_latency_ms=int((time.monotonic() - t0) * 1000),
            )

        att_size = int(msg.get("attachment_size_bytes", 0))
        if att_size > self._cfg.max_attachment_bytes:
            return InboundEventOutcome(
                ws_ack=True,
                task_id=None,
                rejection_code="ATTACHMENT_TOO_LARGE",
                ack_latency_ms=int((time.monotonic() - t0) * 1000),
            )

        raw_content = str(msg.get("content", "{}"))
        try:
            content_doc = json.loads(raw_content)
        except Exception:
            content_doc = {"text": raw_content}
        goal = str(content_doc.get("text", "")).strip() or "feishu_task"

        resp = self._client.post_task(
            idempotency_key=f"feishu_evt:{event_id}",
            body={
                "workspace_id": self._cfg.workspace_id,
                "goal": goal,
                "network_mode": "OFFLINE",
            },
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        if resp.status_code not in {200, 201}:
            return InboundEventOutcome(
                ws_ack=False,
                task_id=None,
                rejection_code="INBOX_PERSIST_FAILED",
                ack_latency_ms=elapsed_ms,
            )

        task_id = str(resp.json()["task_id"])
        return InboundEventOutcome(
            ws_ack=True,
            task_id=task_id,
            rejection_code=None,
            ack_latency_ms=elapsed_ms,
        )
