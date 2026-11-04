"""Bounded model context assembly, tool-call pairing, and taint-preserving summarization."""

import hashlib
import secrets
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Literal

from openbot.application.budgets import OfflineVocabularyEstimator
from openbot.contracts import canonicalize, strict_json
from openbot.storage.inbox import InboundContext, authorize
from openbot.storage.writer import LookupResult, RequestConflict, Writer, WriterCommand

ROLES = frozenset({"SYSTEM", "USER", "ASSISTANT", "TOOL"})
DATA_CLASS_RANK: dict[str, int] = {
    "PUBLIC": 0,
    "WORKSPACE": 1,
    "SENSITIVE": 2,
    "SECRET": 3,
}
PROVENANCE_TAINT_RANK: dict[str, int] = {
    "TRUSTED_SYSTEM": 0,
    "OWNER_INPUT": 1,
    "MODEL_OUTPUT": 2,
    "UNTRUSTED_TOOL_OUTPUT": 3,
    "UNTRUSTED_EXTERNAL": 4,
}
_FORBIDDEN_REASONING_KEYS = frozenset(
    {"hidden_reasoning", "reasoning_trace", "internal_chain_of_thought"}
)


@dataclass(frozen=True, slots=True)
class ContextMessage:
    message_id: str
    turn: int
    role: str
    content: dict[str, Any]
    content_ref: str | None
    provider_call_id: str | None
    tool_call_id: str | None
    provenance_kind: str
    data_class: str
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContextSummary:
    up_to_turn: int
    summary_text: str
    data_class: str
    provenance_kind: str
    source_refs: tuple[str, ...]
    pending_operation_ids: tuple[str, ...]
    approved_operation_ids: tuple[str, ...]
    authoritative_grants: Literal[False] = False


@dataclass(frozen=True, slots=True)
class ModelContextSnapshot:
    task_id: str
    goal: str
    state: str
    network_mode: str
    workspace_id: str
    pending_operation_ids: tuple[str, ...]
    approved_operation_ids: tuple[str, ...]
    summary: ContextSummary | None
    messages: tuple[ContextMessage, ...]
    raw_text_tokens: int
    framing_overhead_tokens: int
    tool_schema_overhead_tokens: int
    multimodal_overhead_tokens: int
    total_conservative_tokens: int
    exact_billing_guaranteed: Literal[False] = False


class ContextService:
    """Manage task messages, taint-inheriting summaries, and bounded model context snapshots."""

    def __init__(self, writer: Writer, estimator: OfflineVocabularyEstimator | None = None) -> None:
        self._writer = writer
        self._estimator = estimator or OfflineVocabularyEstimator()

    def _task_row(
        self, db: sqlite3.Connection, context: InboundContext, task_id: str
    ) -> tuple[str, int, str, dict[str, Any]]:
        authorize(db, context)
        row = db.execute(
            "SELECT owner_id,session_id,state,version,goal,checkpoint_json "
            "FROM tasks WHERE task_id=?",
            (task_id,),
        ).fetchone()
        if not row or row[:2] != (context.principal_id, context.session_id):
            raise PermissionError("Task does not belong to this owner or session")
        checkpoint = {} if row[5] is None else dict(strict_json(str(row[5])))
        return str(row[2]), int(row[3]), str(row[4]), checkpoint

    def _lookup(
        self, db: sqlite3.Connection, context: InboundContext, task_id: str, request_id: str
    ) -> LookupResult | None:
        self._task_row(db, context, task_id)
        row = db.execute(
            "SELECT payload_json FROM events WHERE task_id=? "
            "AND json_extract(payload_json,'$.request_id')=?",
            (task_id, request_id),
        ).fetchone()
        if row is None:
            return None
        val = strict_json(str(row[0]))
        return LookupResult(str(val["command_hash"]), canonicalize(val["receipt"]))

    def _append_context_event(
        self,
        db: sqlite3.Connection,
        context: InboundContext,
        task_id: str,
        aggregate_id: str,
        aggregate_version: int,
        event_type: str,
        request_id: str,
        fingerprint: str,
        receipt: dict[str, Any],
        now: int,
    ) -> None:
        payload = canonicalize(
            {"request_id": request_id, "command_hash": fingerprint, "receipt": receipt}
        ).decode()
        db.execute(
            "INSERT INTO events(event_id,aggregate_kind,aggregate_id,aggregate_version,task_id,"
            "actor_principal_id,event_type,schema_version,trace_id,payload_json,created_at) "
            "VALUES(?,'Context',?,?,?,?,?,1,?,?,?)",
            (
                "evt_" + secrets.token_hex(16),
                aggregate_id,
                aggregate_version,
                task_id,
                context.principal_id,
                event_type,
                "trc_" + hashlib.sha256(request_id.encode()).hexdigest()[:32],
                payload,
                now,
            ),
        )

    def append_message(
        self,
        context: InboundContext,
        task_id: str,
        *,
        role: str,
        content: dict[str, Any],
        provenance_kind: str,
        data_class: str,
        source_refs: tuple[str, ...] = (),
        provider_call_id: str | None = None,
        tool_call_id: str | None = None,
        content_ref: str | None = None,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        if role not in ROLES:
            raise ValueError(f"Unsupported message role: {role}")
        if data_class not in DATA_CLASS_RANK:
            raise ValueError(f"Unsupported data_class: {data_class}")
        if data_class == "SECRET":
            raise PermissionError("SECRET data cannot be persisted into model context messages")
        if provenance_kind not in PROVENANCE_TAINT_RANK:
            raise ValueError(f"Unsupported provenance_kind: {provenance_kind}")
        if set(content) & _FORBIDDEN_REASONING_KEYS:
            raise PermissionError("Persisting hidden_reasoning in context is forbidden")
        if role == "TOOL":
            if tool_call_id is None or not tool_call_id.strip():
                raise ValueError("TOOL message requires non-empty tool_call_id")
            if provenance_kind not in {"UNTRUSTED_TOOL_OUTPUT", "UNTRUSTED_EXTERNAL"}:
                raise PermissionError("TOOL output provenance must remain untrusted")
        if role == "ASSISTANT" and provenance_kind != "MODEL_OUTPUT":
            raise PermissionError("ASSISTANT message provenance must be MODEL_OUTPUT")

        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "context_append_message",
                    "task": task_id,
                    "role": role,
                    "content": content,
                    "provenance": provenance_kind,
                    "data_class": data_class,
                    "refs": list(source_refs),
                    "provider_call_id": provider_call_id,
                    "tool_call_id": tool_call_id,
                    "content_ref": content_ref,
                    "actor": context.principal_id,
                    "profile": context.profile_id,
                    "session": context.session_id,
                    "identity": context.identity_epoch,
                    "surface": context.source_scope,
                }
            )
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return self._lookup(db, context, task_id, request_id)

        def apply(db: sqlite3.Connection) -> bytes:
            self._task_row(db, context, task_id)
            if role == "TOOL":
                paired = db.execute(
                    "SELECT 1 FROM messages WHERE task_id=? AND role='ASSISTANT' "
                    "AND tool_call_id=?",
                    (task_id, tool_call_id),
                ).fetchone()
                if paired is None:
                    raise RequestConflict(
                        f"TOOL message has no matching ASSISTANT tool_call_id={tool_call_id}"
                    )

            next_turn_row = db.execute(
                "SELECT coalesce(max(turn),-1)+1 FROM messages WHERE task_id=?", (task_id,)
            ).fetchone()
            turn = int(next_turn_row[0]) if next_turn_row else 0
            msg_id = "msg_" + secrets.token_hex(16)
            now = time.time_ns() // 1_000_000
            prov_doc = {
                "provenance_kind": provenance_kind,
                "data_class": data_class,
                "source_refs": list(source_refs),
                "authoritative_grants": False,
            }
            db.execute(
                "INSERT INTO messages("
                "message_id,task_id,turn,role,provider_call_id,tool_call_id,content_ref,"
                "content_json,provenance_json,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    msg_id,
                    task_id,
                    turn,
                    role,
                    provider_call_id,
                    tool_call_id,
                    content_ref,
                    canonicalize(content).decode(),
                    canonicalize(prov_doc).decode(),
                    now,
                ),
            )
            receipt: dict[str, Any] = {
                "message_id": msg_id,
                "task_id": task_id,
                "turn": turn,
                "role": role,
                "provenance_kind": provenance_kind,
                "data_class": data_class,
            }
            self._append_context_event(
                db,
                context,
                task_id,
                msg_id,
                turn,
                "CONTEXT_MESSAGE_APPENDED",
                request_id,
                fingerprint,
                receipt,
                now,
            )
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "normal", deadline_monotonic_ms, apply, lookup
        )

    def summarize_window(
        self,
        context: InboundContext,
        task_id: str,
        *,
        up_to_turn: int,
        summary_text: str,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        if up_to_turn < 0 or not summary_text.strip():
            raise ValueError("Invalid summary parameters")
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "context_summarize",
                    "task": task_id,
                    "up_to_turn": up_to_turn,
                    "summary_text": summary_text,
                    "actor": context.principal_id,
                    "profile": context.profile_id,
                    "session": context.session_id,
                    "identity": context.identity_epoch,
                    "surface": context.source_scope,
                }
            )
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return self._lookup(db, context, task_id, request_id)

        def apply(db: sqlite3.Connection) -> bytes:
            _, t_ver, _, checkpoint = self._task_row(db, context, task_id)
            rows = db.execute(
                "SELECT turn,provenance_json FROM messages WHERE task_id=? AND turn<=? "
                "ORDER BY turn",
                (task_id, up_to_turn),
            ).fetchall()
            if not rows:
                raise RequestConflict("No messages found in the requested summary window")

            # Inherit highest data classification and least-trusted provenance across all
            # summarized turns plus any prior summary so taint is NEVER laundered.
            prev_summary = checkpoint.get("context_summary")
            max_class = "PUBLIC"
            max_taint = "TRUSTED_SYSTEM"
            refs: list[str] = []
            if isinstance(prev_summary, dict):
                prev_dc = str(prev_summary.get("data_class", "PUBLIC"))
                prev_pk = str(prev_summary.get("provenance_kind", "TRUSTED_SYSTEM"))
                if DATA_CLASS_RANK.get(prev_dc, 0) > DATA_CLASS_RANK[max_class]:
                    max_class = prev_dc
                if PROVENANCE_TAINT_RANK.get(prev_pk, 0) > PROVENANCE_TAINT_RANK[max_taint]:
                    max_taint = prev_pk
                for r in prev_summary.get("source_refs", []):
                    if str(r) not in refs:
                        refs.append(str(r))

            for _, prov_raw in rows:
                prov = strict_json(str(prov_raw))
                dc = str(prov.get("data_class", "WORKSPACE"))
                pk = str(prov.get("provenance_kind", "MODEL_OUTPUT"))
                if DATA_CLASS_RANK.get(dc, 0) > DATA_CLASS_RANK[max_class]:
                    max_class = dc
                if PROVENANCE_TAINT_RANK.get(pk, 0) > PROVENANCE_TAINT_RANK[max_taint]:
                    max_taint = pk
                for r in prov.get("source_refs", []):
                    if str(r) not in refs:
                        refs.append(str(r))

            # Summary is produced/rewritten for context compression, so its provenance can
            # never be more trusted than MODEL_OUTPUT, and inherits UNTRUSTED_* when present.
            if PROVENANCE_TAINT_RANK[max_taint] < PROVENANCE_TAINT_RANK["MODEL_OUTPUT"]:
                max_taint = "MODEL_OUTPUT"

            pending_ops = [
                str(r[0])
                for r in db.execute(
                    "SELECT operation_id FROM operations WHERE task_id=? "
                    "AND state IN ('PROPOSED','AWAITING_APPROVAL','READY','CLAIMED',"
                    "'DISPATCHING','UNKNOWN') ORDER BY ordinal",
                    (task_id,),
                ).fetchall()
            ]
            approved_ops = [
                str(r[0])
                for r in db.execute(
                    "SELECT o.operation_id FROM operations o "
                    "JOIN approvals a ON a.operation_id=o.operation_id "
                    "WHERE o.task_id=? AND a.status IN ('APPROVED','CONSUMED') ORDER BY o.ordinal",
                    (task_id,),
                ).fetchall()
            ]

            summary_doc: dict[str, Any] = {
                "up_to_turn": up_to_turn,
                "summary_text": summary_text,
                "data_class": max_class,
                "provenance_kind": max_taint,
                "source_refs": refs,
                "pending_operation_ids": pending_ops,
                "approved_operation_ids": approved_ops,
                "authoritative_grants": False,
            }
            checkpoint["context_summary"] = summary_doc
            now = time.time_ns() // 1_000_000
            db.execute(
                "UPDATE tasks SET checkpoint_json=?,version=version+1,updated_at=? "
                "WHERE task_id=? AND version=?",
                (canonicalize(checkpoint).decode(), now, task_id, t_ver),
            )
            self._append_context_event(
                db,
                context,
                task_id,
                task_id,
                t_ver + 1,
                "CONTEXT_SUMMARIZED",
                request_id,
                fingerprint,
                summary_doc,
                now,
            )
            return canonicalize(summary_doc)

        return WriterCommand(
            request_id, fingerprint, "normal", deadline_monotonic_ms, apply, lookup
        )

    def build_model_context(
        self,
        context: InboundContext,
        task_id: str,
        *,
        model: str,
        max_context_tokens: int,
        tool_count: int = 0,
        multimodal_count: int = 0,
    ) -> ModelContextSnapshot:
        if max_context_tokens <= 0:
            raise ValueError("max_context_tokens must be positive")

        def query(db: sqlite3.Connection) -> ModelContextSnapshot:
            state, _, goal, checkpoint = self._task_row(db, context, task_id)
            pending_ops = tuple(
                str(r[0])
                for r in db.execute(
                    "SELECT operation_id FROM operations WHERE task_id=? "
                    "AND state IN ('PROPOSED','AWAITING_APPROVAL','READY','CLAIMED',"
                    "'DISPATCHING','UNKNOWN') ORDER BY ordinal",
                    (task_id,),
                ).fetchall()
            )
            approved_ops = tuple(
                str(r[0])
                for r in db.execute(
                    "SELECT o.operation_id FROM operations o "
                    "JOIN approvals a ON a.operation_id=o.operation_id "
                    "WHERE o.task_id=? AND a.status IN ('APPROVED','CONSUMED') ORDER BY o.ordinal",
                    (task_id,),
                ).fetchall()
            )

            summary_obj: ContextSummary | None = None
            min_turn = 0
            raw_sum = checkpoint.get("context_summary")
            if isinstance(raw_sum, dict):
                min_turn = int(raw_sum["up_to_turn"]) + 1
                summary_obj = ContextSummary(
                    up_to_turn=int(raw_sum["up_to_turn"]),
                    summary_text=str(raw_sum["summary_text"]),
                    data_class=str(raw_sum["data_class"]),
                    provenance_kind=str(raw_sum["provenance_kind"]),
                    source_refs=tuple(str(x) for x in raw_sum.get("source_refs", [])),
                    pending_operation_ids=pending_ops,
                    approved_operation_ids=approved_ops,
                    authoritative_grants=False,
                )

            rows = db.execute(
                "SELECT message_id,turn,role,provider_call_id,tool_call_id,content_ref,"
                "content_json,provenance_json FROM messages WHERE task_id=? AND turn>=? "
                "ORDER BY turn",
                (task_id, min_turn),
            ).fetchall()
            all_msgs: list[ContextMessage] = []
            for r in rows:
                prov = strict_json(str(r[7]))
                all_msgs.append(
                    ContextMessage(
                        message_id=str(r[0]),
                        turn=int(r[1]),
                        role=str(r[2]),
                        provider_call_id=None if r[3] is None else str(r[3]),
                        tool_call_id=None if r[4] is None else str(r[4]),
                        content_ref=None if r[5] is None else str(r[5]),
                        content=dict(strict_json(str(r[6]))),
                        provenance_kind=str(prov.get("provenance_kind", "MODEL_OUTPUT")),
                        data_class=str(prov.get("data_class", "WORKSPACE")),
                        source_refs=tuple(str(x) for x in prov.get("source_refs", [])),
                    )
                )

            # Group messages into indivisible units so ASSISTANT+TOOL pairs are never split
            units: list[list[ContextMessage]] = []
            idx = 0
            while idx < len(all_msgs):
                msg = all_msgs[idx]
                if (
                    msg.role == "ASSISTANT"
                    and msg.tool_call_id is not None
                    and idx + 1 < len(all_msgs)
                    and all_msgs[idx + 1].role == "TOOL"
                    and all_msgs[idx + 1].tool_call_id == msg.tool_call_id
                ):
                    units.append([msg, all_msgs[idx + 1]])
                    idx += 2
                else:
                    units.append([msg])
                    idx += 1

            tool_overhead = max(0, tool_count) * 32
            mm_overhead = max(0, multimodal_count) * 256
            header_text = goal + (" " + summary_obj.summary_text if summary_obj else "")

            selected_units: list[list[ContextMessage]] = []
            for unit in reversed(units):
                candidate_units = [unit, *selected_units]
                flat = [m for u in candidate_units for m in u]
                body_text = header_text + " ".join(canonicalize(m.content).decode() for m in flat)
                est = self._estimator.estimate(model, body_text, tool_count=0)
                framing = len(flat) * 8 + 16
                total = est.estimated_tokens + framing + tool_overhead + mm_overhead
                if total <= max_context_tokens or not selected_units:
                    selected_units = candidate_units
                else:
                    break

            final_msgs = tuple(m for u in selected_units for m in u)
            final_text = header_text + " ".join(
                canonicalize(m.content).decode() for m in final_msgs
            )
            raw_est = self._estimator.estimate(model, final_text, tool_count=0).estimated_tokens
            framing_tokens = len(final_msgs) * 8 + 16
            total_conservative = raw_est + framing_tokens + tool_overhead + mm_overhead

            return ModelContextSnapshot(
                task_id=task_id,
                goal=goal,
                state=state,
                network_mode=str(checkpoint.get("network_mode", "OFFLINE")),
                workspace_id=str(checkpoint.get("workspace_id", context.workspace_id)),
                pending_operation_ids=pending_ops,
                approved_operation_ids=approved_ops,
                summary=summary_obj,
                messages=final_msgs,
                raw_text_tokens=raw_est,
                framing_overhead_tokens=framing_tokens,
                tool_schema_overhead_tokens=tool_overhead,
                multimodal_overhead_tokens=mm_overhead,
                total_conservative_tokens=total_conservative,
                exact_billing_guaranteed=False,
            )

        return self._writer.read(query)
