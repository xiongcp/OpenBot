"""Single-consumer Feishu WebSocket inbound adapter with persist-before-ACK semantics (OB-049)."""

import json
import time
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from openbot.adapters.local_api.server import ApiResponse
from openbot.policy.pairing import PairingService

_FEISHU_REACTION_IN_PROGRESS = "Typing"
_FEISHU_REACTION_FAILURE = "CrossMark"
_MAX_REACTION_CACHE_SIZE = 1024


class GatewayDaemonClientPort(Protocol):
    def post_task(self, idempotency_key: str, body: dict[str, object]) -> ApiResponse: ...


class FeishuReactionClientPort(Protocol):
    def add_reaction(self, message_id: str, emoji_type: str) -> str | None: ...

    def remove_reaction(self, message_id: str, reaction_id: str) -> bool: ...


class FeishuHttpReactionClient:
    """Add/remove Feishu message status reactions (Typing / CrossMark) like HermesAgent."""

    def __init__(
        self, *, tenant_access_token: str, base_url: str = "https://open.feishu.cn"
    ) -> None:
        self._token = tenant_access_token
        self._base = base_url.rstrip("/")

    def add_reaction(self, message_id: str, emoji_type: str) -> str | None:
        if not message_id or not emoji_type:
            return None
        url = f"{self._base}/open-apis/im/v1/messages/{message_id}/reactions"
        body = json.dumps({"reaction_type": {"emoji_type": emoji_type}}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {self._token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                doc = json.loads(resp.read().decode("utf-8"))
                if doc.get("code") == 0:
                    return str((doc.get("data") or {}).get("reaction_id") or "")
        except Exception:
            return None
        return None

    def remove_reaction(self, message_id: str, reaction_id: str) -> bool:
        if not message_id or not reaction_id:
            return False
        url = f"{self._base}/open-apis/im/v1/messages/{message_id}/reactions/{reaction_id}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self._token}"},
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                doc = json.loads(resp.read().decode("utf-8"))
                return bool(doc.get("code") == 0)
        except Exception:
            return False


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
    processing_reaction_id: str | None = None
    processing_reaction_emoji: str | None = None


class FeishuInboundAdapter:
    """Normalize Feishu WS events, enforce guards, and ACK only after Inbox commit."""

    def __init__(
        self,
        *,
        config: FeishuInboundConfig,
        pairing: PairingService,
        api_client: GatewayDaemonClientPort,
        reaction_client: FeishuReactionClientPort | None = None,
    ) -> None:
        self._cfg = config
        self._pairing = pairing
        self._client = api_client
        self._reactions = reaction_client
        self._pending_reactions: OrderedDict[str, str] = OrderedDict()

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
                "event_id": event_id,
                "tenant_key": tenant_key,
                "app_id": app_id,
                "open_id": open_id,
                "chat_id": str(msg.get("chat_id", "")),
                "text": goal,
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
        msg_id = str(msg.get("message_id", ""))
        reaction_id: str | None = None
        reaction_emoji: str | None = None
        if self._reactions is not None and msg_id:
            if msg_id in self._pending_reactions:
                reaction_id = self._pending_reactions[msg_id]
                reaction_emoji = _FEISHU_REACTION_IN_PROGRESS
            else:
                added_id = self._reactions.add_reaction(msg_id, _FEISHU_REACTION_IN_PROGRESS)
                if added_id:
                    reaction_id = added_id
                    reaction_emoji = _FEISHU_REACTION_IN_PROGRESS
                    self._pending_reactions[msg_id] = added_id
                    self._pending_reactions.move_to_end(msg_id)
                    while len(self._pending_reactions) > _MAX_REACTION_CACHE_SIZE:
                        self._pending_reactions.popitem(last=False)
        return InboundEventOutcome(
            ws_ack=True,
            task_id=task_id,
            rejection_code=None,
            ack_latency_ms=elapsed_ms,
            processing_reaction_id=reaction_id,
            processing_reaction_emoji=reaction_emoji,
        )

    def complete_processing(self, message_id: str, *, failed: bool = False) -> bool:
        if self._reactions is None or not message_id:
            return False
        rxn_id = self._pending_reactions.get(message_id)
        if rxn_id:
            if not self._reactions.remove_reaction(message_id, rxn_id):
                return False
            self._pending_reactions.pop(message_id, None)
        if failed:
            self._reactions.add_reaction(message_id, _FEISHU_REACTION_FAILURE)
        return True
