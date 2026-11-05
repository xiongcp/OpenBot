"""Local immutable message.draft tool with recipient resolution and attachment digests."""

import time
from dataclasses import dataclass
from typing import Any, Literal

from openbot.application.state_machine import TaskStateService
from openbot.artifacts.store import ArtifactStore
from openbot.contracts import canonicalize, strict_json
from openbot.storage.inbox import InboundContext
from openbot.storage.writer import Writer


@dataclass(frozen=True, slots=True)
class ContactCandidate:
    recipient_id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class MessageDraftOutcome:
    status: Literal["DRAFT_READY", "WAITING_INPUT"]
    sendable: bool
    revision: int
    channel: str
    account_id: str
    recipient_id: str | None
    draft_artifact_id: str | None
    draft_sha256: str | None
    attachment_digests: tuple[tuple[str, str], ...]
    network_calls_made: Literal[0] = 0


class MessageDraftService:
    """Create local immutable message drafts and require WAITING_INPUT on ambiguous recipients."""

    def __init__(self, writer: Writer, tasks: TaskStateService, artifacts: ArtifactStore) -> None:
        self._writer = writer
        self._tasks = tasks
        self._artifacts = artifacts
        self._latest_by_recipient: dict[tuple[str, str, str], tuple[str, str, int]] = {}

    def create_or_revise_draft(
        self,
        context: InboundContext,
        *,
        task_id: str,
        channel: str,
        account_id: str,
        recipient_candidates: tuple[ContactCandidate, ...],
        body_text: str,
        attachment_artifact_ids: tuple[str, ...] = (),
        prior_revision: int = 0,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> MessageDraftOutcome:
        if not channel.strip() or not account_id.strip() or not body_text.strip():
            raise ValueError("channel, account_id, and body_text must be non-empty")

        # 1. Ambiguous or missing recipient MUST transition Task to WAITING_INPUT
        if len(recipient_candidates) != 1 or not recipient_candidates[0].recipient_id.strip():
            snap = self._tasks.snapshot(context, task_id)
            if snap["state"] == "RUNNING":
                ver = snap["version"]
                assert isinstance(ver, int)
                self._writer.submit(
                    self._tasks.command(
                        context,
                        task_id,
                        ver,
                        "WAITING_INPUT",
                        request_id + ":wait_input",
                        deadline_monotonic_ms,
                    )
                ).result(
                    timeout=min(
                        300.0,
                        max(0.001, (deadline_monotonic_ms - time.monotonic() * 1000) / 1000 + 0.05),
                    )
                )
            return MessageDraftOutcome(
                status="WAITING_INPUT",
                sendable=False,
                revision=prior_revision,
                channel=channel,
                account_id=account_id,
                recipient_id=None,
                draft_artifact_id=None,
                draft_sha256=None,
                attachment_digests=(),
                network_calls_made=0,
            )

        recipient = recipient_candidates[0]
        att_digests: list[tuple[str, str]] = []
        for aid in attachment_artifact_ids:
            dl = self._artifacts.download(context, aid)
            att_digests.append((aid, dl.sha256))

        new_rev = prior_revision + 1
        draft_doc: dict[str, Any] = {
            "task_id": task_id,
            "channel": channel,
            "account_id": account_id,
            "recipient_id": recipient.recipient_id,
            "recipient_display_name": recipient.display_name,
            "revision": new_rev,
            "body_text": body_text,
            "attachments": [{"artifact_id": aid, "sha256": sha} for aid, sha in att_digests],
        }
        draft_bytes = canonicalize(draft_doc)
        art_rec = self._artifacts.put(
            context,
            data=draft_bytes,
            mime="application/json",
            classification="WORKSPACE",
            scope_kind="TASK",
            task_id=task_id,
            purpose=f"message_draft:v{new_rev}",
            request_id=request_id + ":artifact",
            deadline_monotonic_ms=deadline_monotonic_ms,
        )
        key = (task_id, account_id, recipient.recipient_id)
        self._latest_by_recipient[key] = (art_rec.object_id, art_rec.sha256, new_rev)
        return MessageDraftOutcome(
            status="DRAFT_READY",
            sendable=True,
            revision=new_rev,
            channel=channel,
            account_id=account_id,
            recipient_id=recipient.recipient_id,
            draft_artifact_id=art_rec.object_id,
            draft_sha256=art_rec.sha256,
            attachment_digests=tuple(att_digests),
            network_calls_made=0,
        )

    def verify_latest_draft_binding(
        self,
        context: InboundContext,
        draft_artifact_id: str | None,
        expected_sha256: str | None,
    ) -> bool:
        if not draft_artifact_id or not expected_sha256:
            return False
        dl = self._artifacts.download(context, draft_artifact_id)
        if dl.sha256 != expected_sha256:
            return False
        doc = dict(strict_json(dl.data))
        key = (str(doc["task_id"]), str(doc["account_id"]), str(doc["recipient_id"]))
        latest = self._latest_by_recipient.get(key)
        return latest == (draft_artifact_id, expected_sha256, int(doc["revision"]))
