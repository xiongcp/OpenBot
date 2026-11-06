"""Durable task budgets, reservation/settlement ledger, and circuit breakers."""

import hashlib
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from openbot.contracts import canonicalize, strict_json
from openbot.storage.inbox import InboundContext, authorize, emit_state
from openbot.storage.writer import LookupResult, RequestConflict, Writer, WriterCommand

type ReservationKind = Literal["MODEL", "TOOL"]


@dataclass(frozen=True, slots=True)
class TaskBudgetPolicy:
    """Conservative per-task operational and circuit-breaker limits."""

    max_steps: int = 200
    max_model_calls: int = 200
    max_tool_calls: int = 400
    max_retries_per_call: int = 2
    max_duration_ms: int = 14_400_000
    max_single_artifact_bytes: int = 1_048_576
    max_total_artifact_bytes: int = 8_388_608
    max_repeated_proposals: int = 2
    max_consecutive_errors: int = 3
    max_idle_turns: int = 3

    def to_payload(self) -> dict[str, int]:
        return {
            "max_steps": self.max_steps,
            "max_model_calls": self.max_model_calls,
            "max_tool_calls": self.max_tool_calls,
            "max_retries_per_call": self.max_retries_per_call,
            "max_duration_ms": self.max_duration_ms,
            "max_single_artifact_bytes": self.max_single_artifact_bytes,
            "max_total_artifact_bytes": self.max_total_artifact_bytes,
            "max_repeated_proposals": self.max_repeated_proposals,
            "max_consecutive_errors": self.max_consecutive_errors,
            "max_idle_turns": self.max_idle_turns,
        }

    @classmethod
    def from_payload(cls, raw: dict[str, Any] | None) -> "TaskBudgetPolicy":
        if not raw:
            return cls()
        defaults = cls()  # one source of truth for omitted fields (ADR-0014)
        return cls(
            max_steps=int(raw.get("max_steps", defaults.max_steps)),
            max_model_calls=int(raw.get("max_model_calls", defaults.max_model_calls)),
            max_tool_calls=int(raw.get("max_tool_calls", defaults.max_tool_calls)),
            max_retries_per_call=int(
                raw.get("max_retries_per_call", defaults.max_retries_per_call)
            ),
            max_duration_ms=int(raw.get("max_duration_ms", defaults.max_duration_ms)),
            max_single_artifact_bytes=int(
                raw.get("max_single_artifact_bytes", defaults.max_single_artifact_bytes)
            ),
            max_total_artifact_bytes=int(
                raw.get("max_total_artifact_bytes", defaults.max_total_artifact_bytes)
            ),
            max_repeated_proposals=int(
                raw.get("max_repeated_proposals", defaults.max_repeated_proposals)
            ),
            max_consecutive_errors=int(
                raw.get("max_consecutive_errors", defaults.max_consecutive_errors)
            ),
            max_idle_turns=int(raw.get("max_idle_turns", defaults.max_idle_turns)),
        )


@dataclass(frozen=True, slots=True)
class TokenEstimate:
    """Separates local pre-call token estimate from conservative reservation and provider usage."""

    model: str
    encoding_name: str
    vocab_sha256: str | None
    estimated_tokens: int
    conservative_reserved_tokens: int
    exact_billing_guaranteed: Literal[False] = False


class OfflineVocabularyEstimator:
    """Offline-only token estimator. Never downloads vocabularies or claims universal exactness."""

    def __init__(self, model_encodings: dict[str, tuple[str, Path, str]] | None = None) -> None:
        self._encodings = dict(model_encodings or {})

    def estimate(
        self,
        model: str,
        text: str,
        *,
        tool_count: int = 0,
        completion_reserve_tokens: int = 64,
    ) -> TokenEstimate:
        utf8_len = len(text.encode("utf-8"))
        framing_overhead = 16 + max(0, tool_count) * 32
        conservative_base = max(1, utf8_len) + framing_overhead * 2
        conservative = conservative_base + max(32, completion_reserve_tokens)
        if model in self._encodings:
            enc_name, vocab_path, expected_sha256 = self._encodings[model]
            if not vocab_path.is_file() or vocab_path.is_symlink():
                raise ValueError(
                    f"CAPABILITY_UNAVAILABLE: offline vocabulary missing for {model} ({enc_name})"
                )
            actual_sha256 = hashlib.sha256(vocab_path.read_bytes()).hexdigest()
            if actual_sha256 != expected_sha256:
                raise ValueError(
                    f"CAPABILITY_UNAVAILABLE: vocabulary sha256 mismatch for {model} ({enc_name})"
                )
            # Asset integrity does not make this heuristic a tokenizer or an upper bound.
            base_tokens = max(1, (utf8_len + 3) // 4) + framing_overhead
            return TokenEstimate(
                model=model,
                encoding_name=enc_name,
                vocab_sha256=actual_sha256,
                estimated_tokens=base_tokens,
                conservative_reserved_tokens=conservative,
                exact_billing_guaranteed=False,
            )
        # Unknown / non-mapped model: never apply OpenAI vocabulary as exact count
        return TokenEstimate(
            model=model,
            encoding_name="conservative_utf8_bound",
            vocab_sha256=None,
            estimated_tokens=conservative_base,
            conservative_reserved_tokens=conservative,
            exact_billing_guaranteed=False,
        )


class BudgetService:
    """Pre-call reservation, post-call settlement, unknown retention, and circuit breaker."""

    def __init__(self, writer: Writer) -> None:
        self._writer = writer

    def _task_and_budget(
        self, db: sqlite3.Connection, context: InboundContext, task_id: str
    ) -> tuple[str, int, str, int, int, dict[str, Any]]:
        authorize(db, context)
        row = db.execute(
            "SELECT owner_id,session_id,state,version,budget_id,cancel_revision,"
            "created_at,checkpoint_json FROM tasks WHERE task_id=?",
            (task_id,),
        ).fetchone()
        if not row or row[:2] != (context.principal_id, context.session_id):
            raise PermissionError("Task does not belong to this owner or session")
        checkpoint = {} if row[7] is None else dict(strict_json(str(row[7])))
        return (
            str(row[2]),
            int(row[3]),
            str(row[4]),
            int(row[5]),
            int(row[6]),
            checkpoint,
        )

    def _lookup(
        self, db: sqlite3.Connection, context: InboundContext, task_id: str, request_id: str
    ) -> LookupResult | None:
        self._task_and_budget(db, context, task_id)
        row = db.execute(
            "SELECT payload_json FROM events WHERE task_id=? "
            "AND json_extract(payload_json,'$.request_id')=?",
            (task_id, request_id),
        ).fetchone()
        if row is None:
            return None
        val = strict_json(str(row[0]))
        return LookupResult(str(val["command_hash"]), canonicalize(val["receipt"]))

    def _append_budget_event(
        self,
        db: sqlite3.Connection,
        context: InboundContext,
        budget_id: str,
        budget_version: int,
        task_id: str,
        event_type: str,
        request_id: str,
        fingerprint: str,
        receipt: dict[str, Any],
        now: int,
        operation_id: str | None = None,
    ) -> None:
        payload = canonicalize(
            {"request_id": request_id, "command_hash": fingerprint, "receipt": receipt}
        ).decode()
        db.execute(
            "INSERT INTO events(event_id,aggregate_kind,aggregate_id,aggregate_version,task_id,"
            "operation_id,actor_principal_id,event_type,schema_version,trace_id,payload_json,"
            "created_at) VALUES(?,'Budget',?,?,?,?,?,?,1,?,?,?)",
            (
                "evt_" + secrets.token_hex(16),
                budget_id,
                budget_version,
                task_id,
                operation_id,
                context.principal_id,
                event_type,
                "trc_" + hashlib.sha256(request_id.encode()).hexdigest()[:32],
                payload,
                now,
            ),
        )

    def configure_limits(
        self,
        context: InboundContext,
        task_id: str,
        *,
        amount_limit_micros: int,
        token_limit: int,
        policy: TaskBudgetPolicy,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        if amount_limit_micros < 0 or token_limit < 0:
            raise ValueError("Budget limits must be non-negative")
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "budget_configure",
                    "task": task_id,
                    "amount": amount_limit_micros,
                    "tokens": token_limit,
                    "policy": policy.to_payload(),
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
            state, t_ver, budget_id, _, _, checkpoint = self._task_and_budget(db, context, task_id)
            now = time.time_ns() // 1_000_000
            b_row = db.execute(
                "SELECT version FROM budgets WHERE budget_id=?", (budget_id,)
            ).fetchone()
            if not b_row:
                raise PermissionError("Budget record missing")
            b_ver = int(b_row[0])
            db.execute(
                "UPDATE budgets SET amount_limit_micros=?,token_limit=?,version=?,updated_at=? "
                "WHERE budget_id=? AND version=?",
                (amount_limit_micros, token_limit, b_ver + 1, now, budget_id, b_ver),
            )
            checkpoint["budget_policy"] = policy.to_payload()
            db.execute(
                "UPDATE tasks SET checkpoint_json=?,version=version+1,updated_at=? "
                "WHERE task_id=? AND version=?",
                (canonicalize(checkpoint).decode(), now, task_id, t_ver),
            )
            receipt: dict[str, Any] = {
                "task_id": task_id,
                "budget_id": budget_id,
                "state": state,
                "version": t_ver + 1,
            }
            self._append_budget_event(
                db,
                context,
                budget_id,
                b_ver + 1,
                task_id,
                "BUDGET_CONFIGURED",
                request_id,
                fingerprint,
                receipt,
                now,
            )
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "normal", deadline_monotonic_ms, apply, lookup
        )

    def reserve(
        self,
        context: InboundContext,
        task_id: str,
        *,
        call_ref: str,
        kind: ReservationKind,
        reserved_amount_micros: int,
        reserved_tokens: int,
        estimated_tokens: int | None = None,
        operation_id: str | None = None,
        attempt_index: int = 1,
        artifact_bytes: int = 0,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        if not call_ref.strip() or reserved_amount_micros < 0 or reserved_tokens < 0:
            raise ValueError("Invalid budget reservation arguments")
        if attempt_index < 1 or artifact_bytes < 0:
            raise ValueError("Invalid attempt_index or artifact_bytes")
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "budget_reserve",
                    "task": task_id,
                    "call_ref": call_ref,
                    "res_kind": kind,
                    "amount": reserved_amount_micros,
                    "tokens": reserved_tokens,
                    "estimated": estimated_tokens,
                    "operation": operation_id,
                    "attempt_index": attempt_index,
                    "artifact_bytes": artifact_bytes,
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
            state, t_ver, budget_id, cancel_rev, created_at, checkpoint = self._task_and_budget(
                db, context, task_id
            )
            if cancel_rev > 0 or state != "RUNNING":
                raise PermissionError(
                    "Task is cancelled or not RUNNING; new budget reservations refused"
                )
            now = time.time_ns() // 1_000_000
            policy = TaskBudgetPolicy.from_payload(checkpoint.get("budget_policy"))
            counters = dict(checkpoint.get("budget_counters", {}))
            steps = int(counters.get("steps", 0)) + 1
            model_calls = int(counters.get("model_calls", 0)) + (1 if kind == "MODEL" else 0)
            tool_calls = int(counters.get("tool_calls", 0)) + (1 if kind == "TOOL" else 0)
            total_art_bytes = int(counters.get("artifact_bytes", 0)) + artifact_bytes

            b_row = db.execute(
                "SELECT amount_limit_micros,amount_spent_micros,amount_reserved_micros,"
                "token_limit,tokens_spent,tokens_reserved,version "
                "FROM budgets WHERE budget_id=?",
                (budget_id,),
            ).fetchone()
            if not b_row:
                raise PermissionError("Budget record missing")
            amt_lim, amt_spent, amt_res, tok_lim, tok_spent, tok_res, b_ver = (
                int(b_row[0]),
                int(b_row[1]),
                int(b_row[2]),
                int(b_row[3]),
                int(b_row[4]),
                int(b_row[5]),
                int(b_row[6]),
            )

            exhausted_reason: str | None = None
            if attempt_index > policy.max_retries_per_call + 1:
                exhausted_reason = "BUDGET_EXHAUSTED:MAX_RETRIES_PER_CALL"
            elif steps > policy.max_steps:
                exhausted_reason = "BUDGET_EXHAUSTED:MAX_STEPS"
            elif kind == "MODEL" and model_calls > policy.max_model_calls:
                exhausted_reason = "BUDGET_EXHAUSTED:MAX_MODEL_CALLS"
            elif kind == "TOOL" and tool_calls > policy.max_tool_calls:
                exhausted_reason = "BUDGET_EXHAUSTED:MAX_TOOL_CALLS"
            elif now - created_at > policy.max_duration_ms:
                exhausted_reason = "BUDGET_EXHAUSTED:MAX_DURATION_MS"
            elif (
                artifact_bytes > policy.max_single_artifact_bytes
                or total_art_bytes > policy.max_total_artifact_bytes
            ):
                exhausted_reason = "BUDGET_EXHAUSTED:ARTIFACT_BYTES_LIMIT"
            elif reserved_amount_micros > amt_lim - amt_spent - amt_res:
                exhausted_reason = "BUDGET_EXHAUSTED:AMOUNT_LIMIT"
            elif reserved_tokens > tok_lim - tok_spent - tok_res:
                exhausted_reason = "BUDGET_EXHAUSTED:TOKEN_LIMIT"

            if exhausted_reason is not None:
                checkpoint["paused_reason"] = exhausted_reason
                db.execute(
                    "UPDATE tasks SET state='PAUSED',checkpoint_json=?,version=version+1,"
                    "updated_at=? WHERE task_id=? AND version=?",
                    (canonicalize(checkpoint).decode(), now, task_id, t_ver),
                )
                pause_receipt: dict[str, Any] = {
                    "task_id": task_id,
                    "state": "PAUSED",
                    "task_state": "PAUSED",
                    "version": t_ver + 1,
                    "admitted": False,
                    "reason": exhausted_reason,
                }
                emit_state(
                    db, context, pause_receipt, request_id, fingerprint, "TASK_STATE_CHANGED", now
                )
                return canonicalize(pause_receipt)

            upd = db.execute(
                "UPDATE budgets SET amount_reserved_micros=amount_reserved_micros+?,"
                "tokens_reserved=tokens_reserved+?,version=?,updated_at=? "
                "WHERE budget_id=? AND version=? "
                "AND ?<=amount_limit_micros-amount_spent_micros-amount_reserved_micros "
                "AND ?<=token_limit-tokens_spent-tokens_reserved",
                (
                    reserved_amount_micros,
                    reserved_tokens,
                    b_ver + 1,
                    now,
                    budget_id,
                    b_ver,
                    reserved_amount_micros,
                    reserved_tokens,
                ),
            )
            if upd.rowcount != 1:
                raise RequestConflict("Concurrent budget reservation conflict")

            res_id = "brs_" + secrets.token_hex(16)
            ev_meta = (
                None
                if estimated_tokens is None
                else canonicalize({"estimated_tokens": estimated_tokens}).decode()
            )
            db.execute(
                "INSERT INTO budget_reservations("
                "reservation_id,budget_id,operation_id,call_ref,kind,status,"
                "reserved_amount_micros,reserved_tokens,evidence_ref,created_at) "
                "VALUES(?,?,?,?,?,'RESERVED',?,?,?,?)",
                (
                    res_id,
                    budget_id,
                    operation_id,
                    call_ref,
                    kind,
                    reserved_amount_micros,
                    reserved_tokens,
                    ev_meta,
                    now,
                ),
            )
            counters.update(
                {
                    "steps": steps,
                    "model_calls": model_calls,
                    "tool_calls": tool_calls,
                    "artifact_bytes": total_art_bytes,
                }
            )
            checkpoint["budget_counters"] = counters
            db.execute(
                "UPDATE tasks SET checkpoint_json=?,version=version+1,updated_at=? "
                "WHERE task_id=? AND version=?",
                (canonicalize(checkpoint).decode(), now, task_id, t_ver),
            )
            receipt: dict[str, Any] = {
                "task_id": task_id,
                "state": state,
                "version": t_ver + 1,
                "admitted": True,
                "reservation_id": res_id,
                "call_ref": call_ref,
            }
            self._append_budget_event(
                db,
                context,
                budget_id,
                b_ver + 1,
                task_id,
                "BUDGET_RESERVED",
                request_id,
                fingerprint,
                receipt,
                now,
                operation_id,
            )
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "normal", deadline_monotonic_ms, apply, lookup
        )

    def settle(
        self,
        context: InboundContext,
        task_id: str,
        *,
        call_ref: str,
        actual_amount_micros: int,
        actual_tokens: int,
        estimated_tokens: int | None = None,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        if actual_amount_micros < 0 or actual_tokens < 0:
            raise ValueError("Actual usage must be non-negative")
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "budget_settle",
                    "task": task_id,
                    "call_ref": call_ref,
                    "actual_amount": actual_amount_micros,
                    "actual_tokens": actual_tokens,
                    "estimated_tokens": estimated_tokens,
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
            state, t_ver, budget_id, _, _, _ = self._task_and_budget(db, context, task_id)
            r_row = db.execute(
                "SELECT reservation_id,status,reserved_amount_micros,reserved_tokens "
                "FROM budget_reservations WHERE budget_id=? AND call_ref=?",
                (budget_id, call_ref),
            ).fetchone()
            if not r_row or r_row[1] != "RESERVED":
                raise RequestConflict("Reservation is not in RESERVED state")
            res_id, res_amt, res_tok = str(r_row[0]), int(r_row[2]), int(r_row[3])
            b_row = db.execute(
                "SELECT version FROM budgets WHERE budget_id=?", (budget_id,)
            ).fetchone()
            assert b_row is not None
            b_ver = int(b_row[0])
            now = time.time_ns() // 1_000_000
            delta = None if estimated_tokens is None else actual_tokens - estimated_tokens
            evidence = canonicalize(
                {
                    "estimated_tokens": estimated_tokens,
                    "actual_tokens": actual_tokens,
                    "usage_delta_tokens": delta,
                }
            ).decode()
            db.execute(
                "UPDATE budget_reservations SET status='SETTLED',actual_amount_micros=?,"
                "actual_tokens=?,evidence_ref=?,settled_at=? WHERE reservation_id=?",
                (actual_amount_micros, actual_tokens, evidence, now, res_id),
            )
            db.execute(
                "UPDATE budgets SET amount_reserved_micros=amount_reserved_micros-?,"
                "amount_spent_micros=amount_spent_micros+?,"
                "tokens_reserved=tokens_reserved-?,tokens_spent=tokens_spent+?,"
                "version=?,updated_at=? WHERE budget_id=? AND version=?",
                (
                    res_amt,
                    actual_amount_micros,
                    res_tok,
                    actual_tokens,
                    b_ver + 1,
                    now,
                    budget_id,
                    b_ver,
                ),
            )
            receipt: dict[str, Any] = {
                "task_id": task_id,
                "state": state,
                "version": t_ver,
                "call_ref": call_ref,
                "status": "SETTLED",
                "usage_delta_tokens": delta,
            }
            self._append_budget_event(
                db,
                context,
                budget_id,
                b_ver + 1,
                task_id,
                "BUDGET_SETTLED",
                request_id,
                fingerprint,
                receipt,
                now,
            )
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "result", deadline_monotonic_ms, apply, lookup
        )

    def mark_unknown(
        self,
        context: InboundContext,
        task_id: str,
        *,
        call_ref: str,
        reason: str,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        if not reason.strip():
            raise ValueError("Unknown budget reason required")
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "budget_unknown",
                    "task": task_id,
                    "call_ref": call_ref,
                    "reason": reason,
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
            state, t_ver, budget_id, _, _, _ = self._task_and_budget(db, context, task_id)
            r_row = db.execute(
                "SELECT reservation_id,status FROM budget_reservations "
                "WHERE budget_id=? AND call_ref=?",
                (budget_id, call_ref),
            ).fetchone()
            if not r_row or r_row[1] != "RESERVED":
                raise RequestConflict("Reservation is not in RESERVED state")
            now = time.time_ns() // 1_000_000
            # Keep reserved_amount_micros and tokens_reserved held in budgets table!
            db.execute(
                "UPDATE budget_reservations SET status='UNKNOWN',evidence_ref=?,settled_at=NULL "
                "WHERE reservation_id=?",
                (reason, str(r_row[0])),
            )
            receipt: dict[str, Any] = {
                "task_id": task_id,
                "state": state,
                "version": t_ver,
                "call_ref": call_ref,
                "status": "UNKNOWN",
                "reason": reason,
            }
            self._append_budget_event(
                db,
                context,
                budget_id,
                0,
                task_id,
                "BUDGET_UNKNOWN",
                request_id,
                fingerprint,
                receipt,
                now,
            )
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "result", deadline_monotonic_ms, apply, lookup
        )

    def record_turn_activity(
        self,
        context: InboundContext,
        task_id: str,
        *,
        proposal_fingerprint: str | None = None,
        had_error: bool = False,
        was_idle: bool = False,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "budget_turn_activity",
                    "task": task_id,
                    "proposal_fp": proposal_fingerprint,
                    "had_error": had_error,
                    "was_idle": was_idle,
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
            state, t_ver, _, _, _, checkpoint = self._task_and_budget(db, context, task_id)
            if state != "RUNNING":
                raise RequestConflict("Task must be RUNNING to record turn activity")
            policy = TaskBudgetPolicy.from_payload(checkpoint.get("budget_policy"))
            cb = dict(checkpoint.get("circuit_breaker", {}))
            history = list(cb.get("proposal_fingerprints", []))
            if proposal_fingerprint is not None:
                history.append(proposal_fingerprint)
            errors = int(cb.get("consecutive_errors", 0)) + 1 if had_error else 0
            idle = int(cb.get("idle_turns", 0)) + 1 if was_idle else 0

            repeated = (
                history.count(proposal_fingerprint) if proposal_fingerprint is not None else 0
            )
            trip_reason: str | None = None
            if repeated >= policy.max_repeated_proposals:
                trip_reason = "CIRCUIT_BREAKER:REPEATED_PROPOSAL"
            elif errors >= policy.max_consecutive_errors:
                trip_reason = "CIRCUIT_BREAKER:CONSECUTIVE_ERRORS"
            elif idle >= policy.max_idle_turns:
                trip_reason = "CIRCUIT_BREAKER:IDLE_SPIN"

            cb.update(
                {
                    "proposal_fingerprints": history[-32:],
                    "consecutive_errors": errors,
                    "idle_turns": idle,
                }
            )
            checkpoint["circuit_breaker"] = cb
            now = time.time_ns() // 1_000_000
            target_state = "PAUSED" if trip_reason is not None else state
            if trip_reason is not None:
                checkpoint["paused_reason"] = trip_reason
            db.execute(
                "UPDATE tasks SET state=?,checkpoint_json=?,version=version+1,updated_at=? "
                "WHERE task_id=? AND version=?",
                (target_state, canonicalize(checkpoint).decode(), now, task_id, t_ver),
            )
            receipt: dict[str, Any] = {
                "task_id": task_id,
                "state": target_state,
                "task_state": target_state,
                "version": t_ver + 1,
                "tripped": trip_reason is not None,
                "reason": trip_reason,
            }
            emit_state(db, context, receipt, request_id, fingerprint, "TASK_STATE_CHANGED", now)
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "normal", deadline_monotonic_ms, apply, lookup
        )

    def resume_paused(
        self,
        context: InboundContext,
        task_id: str,
        *,
        expected_version: int,
        additional_amount_micros: int = 0,
        additional_tokens: int = 0,
        reset_circuit_breaker: bool = False,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> WriterCommand:
        if additional_amount_micros < 0 or additional_tokens < 0:
            raise ValueError("Additional budget must be non-negative")
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "budget_resume_paused",
                    "task": task_id,
                    "expected": expected_version,
                    "add_amount": additional_amount_micros,
                    "add_tokens": additional_tokens,
                    "reset_cb": reset_circuit_breaker,
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
            state, t_ver, budget_id, cancel_rev, _, checkpoint = self._task_and_budget(
                db, context, task_id
            )
            if state != "PAUSED" or t_ver != expected_version:
                raise RequestConflict("Task is not in PAUSED at expected_version")
            if cancel_rev > 0:
                raise PermissionError("Cancelled task cannot be resumed from PAUSED")
            now = time.time_ns() // 1_000_000
            if additional_amount_micros > 0 or additional_tokens > 0:
                b_row = db.execute(
                    "SELECT version FROM budgets WHERE budget_id=?", (budget_id,)
                ).fetchone()
                assert b_row is not None
                b_ver = int(b_row[0])
                db.execute(
                    "UPDATE budgets SET amount_limit_micros=amount_limit_micros+?,"
                    "token_limit=token_limit+?,version=?,updated_at=? "
                    "WHERE budget_id=? AND version=?",
                    (
                        additional_amount_micros,
                        additional_tokens,
                        b_ver + 1,
                        now,
                        budget_id,
                        b_ver,
                    ),
                )
            if reset_circuit_breaker:
                checkpoint["circuit_breaker"] = {
                    "proposal_fingerprints": [],
                    "consecutive_errors": 0,
                    "idle_turns": 0,
                }
            checkpoint.pop("paused_reason", None)
            db.execute(
                "UPDATE tasks SET state='QUEUED',checkpoint_json=?,version=version+1,"
                "updated_at=? WHERE task_id=? AND version=? AND state='PAUSED'",
                (canonicalize(checkpoint).decode(), now, task_id, expected_version),
            )
            receipt: dict[str, Any] = {
                "task_id": task_id,
                "state": "QUEUED",
                "version": t_ver + 1,
            }
            emit_state(db, context, receipt, request_id, fingerprint, "TASK_STATE_CHANGED", now)
            return canonicalize(receipt)

        return WriterCommand(
            request_id, fingerprint, "normal", deadline_monotonic_ms, apply, lookup
        )

    def snapshot(self, context: InboundContext, task_id: str) -> dict[str, Any]:
        def query(db: sqlite3.Connection) -> dict[str, Any]:
            _, _, budget_id, _, _, checkpoint = self._task_and_budget(db, context, task_id)
            row = db.execute(
                "SELECT amount_limit_micros,amount_spent_micros,amount_reserved_micros,"
                "token_limit,tokens_spent,tokens_reserved,version "
                "FROM budgets WHERE budget_id=?",
                (budget_id,),
            ).fetchone()
            assert row is not None
            return {
                "budget_id": budget_id,
                "amount_limit_micros": int(row[0]),
                "amount_spent_micros": int(row[1]),
                "amount_reserved_micros": int(row[2]),
                "token_limit": int(row[3]),
                "tokens_spent": int(row[4]),
                "tokens_reserved": int(row[5]),
                "version": int(row[6]),
                "paused_reason": checkpoint.get("paused_reason"),
            }

        return self._writer.read(query)
