"""Durable artifact store with atomic staging-to-rename, classification guards, and GC pins."""

import hashlib
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openbot.contracts import canonicalize, strict_json
from openbot.storage.inbox import InboundContext, authorize
from openbot.storage.outbox import event_lookup
from openbot.storage.writer import LookupResult, Writer, WriterCommand

CLASSIFICATIONS = frozenset({"PUBLIC", "WORKSPACE", "SENSITIVE", "SECRET"})
SCOPE_KINDS = frozenset({"PRINCIPAL", "SESSION", "TASK", "OPERATION"})


@dataclass(frozen=True, slots=True)
class ArtifactLimits:
    max_single_artifact_bytes: int = 1_048_576
    max_task_artifact_bytes: int = 8_388_608
    max_preview_bytes: int = 4_096
    default_ttl_ms: int = 86_400_000


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    object_id: str
    object_key: str
    sha256: str
    mime: str
    bytes_len: int
    classification: str
    state: str
    created_at: int
    expires_at: int | None
    ref_id: str


@dataclass(frozen=True, slots=True)
class ArtifactDownload:
    """Safe download envelope: forces attachment/sandbox CSP and never exposes host paths."""

    object_id: str
    sha256: str
    mime: str
    bytes_len: int
    classification: str
    data: bytes
    content_disposition: str = "attachment"
    content_security_policy: str = "default-src 'none'; sandbox"
    x_content_type_options: str = "nosniff"

    def public_metadata(self) -> dict[str, str | int]:
        return {
            "object_id": self.object_id,
            "sha256": self.sha256,
            "mime": self.mime,
            "bytes": self.bytes_len,
            "classification": self.classification,
            "content_disposition": self.content_disposition,
            "content_security_policy": self.content_security_policy,
            "x_content_type_options": self.x_content_type_options,
        }


def _append_artifact_event(
    db: sqlite3.Connection,
    context: InboundContext,
    object_id: str,
    task_id: str | None,
    operation_id: str | None,
    event_type: str,
    request_id: str,
    fingerprint: str,
    receipt: dict[str, Any],
    now: int,
) -> None:
    payload = canonicalize(
        {
            "request_id": request_id,
            "command_hash": fingerprint,
            "source_scope": context.source_scope,
            "receipt": receipt,
        }
    ).decode()
    db.execute(
        "INSERT INTO events(event_id,aggregate_kind,aggregate_id,aggregate_version,task_id,"
        "operation_id,actor_principal_id,event_type,schema_version,trace_id,payload_json,"
        "created_at) VALUES(?,'Artifact',?,1,?,?,?,?,1,?,?,?)",
        (
            "evt_" + secrets.token_hex(16),
            object_id,
            task_id,
            operation_id,
            context.principal_id,
            event_type,
            "trc_" + hashlib.sha256(request_id.encode()).hexdigest()[:32],
            payload,
            now,
        ),
    )


class ArtifactStore:
    """Content-addressed artifact persistence with atomic staging and reference-safe GC."""

    def __init__(
        self,
        writer: Writer,
        blob_root: Path,
        *,
        limits: ArtifactLimits | None = None,
    ) -> None:
        if blob_root.is_symlink():
            raise PermissionError("Artifact blob_root must not be a symlink")
        blob_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        (blob_root / "staging").mkdir(parents=True, exist_ok=True, mode=0o700)
        (blob_root / "objects").mkdir(parents=True, exist_ok=True, mode=0o700)
        self._writer = writer
        self._root = blob_root.resolve()
        self._limits = limits or ArtifactLimits()
        self._backup_pins: dict[str, frozenset[str]] = {}

    def pin_for_backup(self, object_ids: list[str] | tuple[str, ...]) -> str:
        pin_id = "pin_" + secrets.token_hex(16)
        self._backup_pins[pin_id] = frozenset(object_ids)
        return pin_id

    def unpin_backup(self, pin_id: str) -> None:
        self._backup_pins.pop(pin_id, None)

    def _pinned_ids(self) -> set[str]:
        pinned: set[str] = set()
        for ids in self._backup_pins.values():
            pinned.update(ids)
        return pinned

    def _resolve_object_key(self, object_key: str) -> Path:
        if not object_key.startswith("objects/") or ".." in object_key.split("/"):
            raise PermissionError("Invalid artifact object_key")
        target = (self._root / object_key).resolve()
        if not target.is_relative_to(self._root / "objects"):
            raise PermissionError("Artifact object_key escapes objects directory")
        return target

    def put(
        self,
        context: InboundContext,
        *,
        data: bytes,
        mime: str,
        classification: str,
        scope_kind: str,
        purpose: str,
        session_id: str | None = None,
        task_id: str | None = None,
        operation_id: str | None = None,
        ttl_ms: int | None = None,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> ArtifactRecord:
        if classification not in CLASSIFICATIONS:
            raise ValueError(f"Invalid classification: {classification}")
        if scope_kind not in SCOPE_KINDS or not mime.strip() or not purpose.strip():
            raise ValueError("Invalid artifact scope_kind, mime, or purpose")
        size_bytes = len(data)
        if size_bytes > self._limits.max_single_artifact_bytes:
            raise ValueError("Artifact exceeds max_single_artifact_bytes")

        sha256_hex = hashlib.sha256(data).hexdigest()
        object_id = "art_" + secrets.token_hex(16)
        object_key = f"objects/{sha256_hex[:2]}/{object_id}.bin"
        final_path = self._resolve_object_key(object_key)
        final_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        # 1. Write to staging temp file, fsync, and atomically rename before DB registration
        staging_path = self._root / "staging" / f".tmp_{secrets.token_hex(16)}"
        fd = os.open(staging_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            view = memoryview(data)
            written = 0
            while written < size_bytes:
                n = os.write(fd, view[written:])
                if n <= 0:
                    raise OSError("Short write to staging artifact")
                written += n
            os.fsync(fd)
        except BaseException:
            os.close(fd)
            staging_path.unlink(missing_ok=True)
            raise
        os.close(fd)
        os.replace(staging_path, final_path)

        effective_ttl = self._limits.default_ttl_ms if ttl_ms is None else int(ttl_ms)
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "artifact_put",
                    "sha256": sha256_hex,
                    "mime": mime,
                    "bytes": size_bytes,
                    "classification": classification,
                    "scope_kind": scope_kind,
                    "session_id": session_id,
                    "task_id": task_id,
                    "operation_id": operation_id,
                    "purpose": purpose,
                    "ttl_ms": effective_ttl,
                    "actor": context.principal_id,
                    "profile": context.profile_id,
                    "session": context.session_id,
                    "identity": context.identity_epoch,
                    "surface": context.source_scope,
                }
            )
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return event_lookup(db, context, request_id)

        def apply(db: sqlite3.Connection) -> bytes:
            authorize(db, context)
            check_task_id = task_id
            if scope_kind == "OPERATION":
                if operation_id is None:
                    raise ValueError("OPERATION scope requires operation_id")
                op_row = db.execute(
                    "SELECT task_id,requested_by FROM operations WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()
                if not op_row or op_row[1] != context.principal_id:
                    raise PermissionError("Operation scope mismatch for artifact")
                check_task_id = str(op_row[0])
            elif scope_kind == "TASK":
                if task_id is None:
                    raise ValueError("TASK scope requires task_id")
                t_row = db.execute(
                    "SELECT owner_id FROM tasks WHERE task_id=?", (task_id,)
                ).fetchone()
                if not t_row or t_row[0] != context.principal_id:
                    raise PermissionError("Task scope mismatch for artifact")

            if check_task_id is not None:
                used_row = db.execute(
                    "SELECT coalesce(sum(a.bytes),0) FROM artifacts a "
                    "JOIN artifact_refs r ON r.object_id=a.object_id "
                    "WHERE a.state='AVAILABLE' AND (r.task_id=? OR r.operation_id IN ("
                    "  SELECT operation_id FROM operations WHERE task_id=?))",
                    (check_task_id, check_task_id),
                ).fetchone()
                used_bytes = int(used_row[0]) if used_row else 0
                if used_bytes + size_bytes > self._limits.max_task_artifact_bytes:
                    raise ValueError("Task total artifact quota exceeded")

            now = time.time_ns() // 1_000_000
            expires_at = now + max(0, effective_ttl)
            ref_id = "ref_" + secrets.token_hex(16)
            db.execute(
                "INSERT INTO artifacts("
                "object_id,object_key,sha256,mime,bytes,classification,state,created_at,"
                "expires_at) "
                "VALUES(?,?,?,?,?,?,'AVAILABLE',?,?)",
                (
                    object_id,
                    object_key,
                    sha256_hex,
                    mime,
                    size_bytes,
                    classification,
                    now,
                    expires_at,
                ),
            )
            db.execute(
                "INSERT INTO artifact_refs("
                "ref_id,object_id,owner_id,scope_kind,session_id,task_id,operation_id,"
                "purpose,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    ref_id,
                    object_id,
                    context.principal_id,
                    scope_kind,
                    session_id if scope_kind == "SESSION" else None,
                    task_id if scope_kind == "TASK" else None,
                    operation_id if scope_kind == "OPERATION" else None,
                    purpose,
                    now,
                ),
            )
            receipt: dict[str, Any] = {
                "object_id": object_id,
                "object_key": object_key,
                "sha256": sha256_hex,
                "mime": mime,
                "bytes": size_bytes,
                "classification": classification,
                "state": "AVAILABLE",
                "created_at": now,
                "expires_at": expires_at,
                "ref_id": ref_id,
            }
            _append_artifact_event(
                db,
                context,
                object_id,
                check_task_id,
                operation_id,
                "ARTIFACT_REGISTERED",
                request_id,
                fingerprint,
                receipt,
                now,
            )
            return canonicalize(receipt)

        try:
            raw = self._writer.submit(
                WriterCommand(
                    request_id, fingerprint, "normal", deadline_monotonic_ms, apply, lookup
                )
            ).result(
                timeout=max(0.001, (deadline_monotonic_ms - time.monotonic() * 1000) / 1000 + 0.05)
            )
        except BaseException:
            final_path.unlink(missing_ok=True)
            raise
        parsed = strict_json(raw)
        return ArtifactRecord(
            object_id=str(parsed["object_id"]),
            object_key=str(parsed["object_key"]),
            sha256=str(parsed["sha256"]),
            mime=str(parsed["mime"]),
            bytes_len=int(parsed["bytes"]),
            classification=str(parsed["classification"]),
            state=str(parsed["state"]),
            created_at=int(parsed["created_at"]),
            expires_at=None if parsed["expires_at"] is None else int(parsed["expires_at"]),
            ref_id=str(parsed["ref_id"]),
        )

    def _quarantine_missing_or_corrupt(self, context: InboundContext, object_id: str) -> None:
        req_id = f"quarantine:{object_id}:{secrets.token_hex(8)}"
        fp = hashlib.sha256(req_id.encode()).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return None

        def apply(db: sqlite3.Connection) -> bytes:
            authorize(db, context)
            db.execute(
                "UPDATE artifacts SET state='QUARANTINED' WHERE object_id=? AND state='AVAILABLE'",
                (object_id,),
            )
            return b"{}"

        self._writer.submit(
            WriterCommand(req_id, fp, "result", int(time.monotonic() * 1000) + 5000, apply, lookup)
        ).result(timeout=5)

    def download(self, context: InboundContext, object_id: str) -> ArtifactDownload:
        def query(db: sqlite3.Connection) -> tuple[str, str, str, int, str, str]:
            authorize(db, context)
            row = db.execute(
                "SELECT a.object_key,a.sha256,a.mime,a.bytes,a.classification,a.state "
                "FROM artifacts a JOIN artifact_refs r ON r.object_id=a.object_id "
                "WHERE a.object_id=? AND r.owner_id=? LIMIT 1",
                (object_id, context.principal_id),
            ).fetchone()
            if row is None:
                raise PermissionError(f"Artifact not found or unauthorized: {object_id}")
            return (
                str(row[0]),
                str(row[1]),
                str(row[2]),
                int(row[3]),
                str(row[4]),
                str(row[5]),
            )

        obj_key, expected_sha, mime, size_bytes, classification, state = self._writer.read(query)
        if state != "AVAILABLE":
            raise FileNotFoundError(f"Artifact {object_id} is in state {state}")
        blob_path = self._resolve_object_key(obj_key)
        if not blob_path.is_file() or blob_path.is_symlink():
            self._quarantine_missing_or_corrupt(context, object_id)
            raise FileNotFoundError(
                f"Artifact {object_id} blob missing on disk; marked QUARANTINED"
            )
        data = blob_path.read_bytes()
        if len(data) != size_bytes or hashlib.sha256(data).hexdigest() != expected_sha:
            self._quarantine_missing_or_corrupt(context, object_id)
            raise FileNotFoundError(
                f"Artifact {object_id} blob corrupted on disk; marked QUARANTINED"
            )
        return ArtifactDownload(
            object_id=object_id,
            sha256=expected_sha,
            mime=mime,
            bytes_len=size_bytes,
            classification=classification,
            data=data,
        )

    def preview(self, context: InboundContext, object_id: str) -> dict[str, Any]:
        dl = self.download(context, object_id)
        if dl.classification == "SECRET":
            raise PermissionError("SECRET artifacts cannot be accessed via preview")
        limit = self._limits.max_preview_bytes
        snippet = dl.data[:limit]
        return {
            "object_id": dl.object_id,
            "sha256": dl.sha256,
            "mime": dl.mime,
            "classification": dl.classification,
            "preview_bytes": snippet.decode("utf-8", errors="replace"),
            "truncated": len(dl.data) > limit,
            "content_disposition": "attachment",
        }

    def verify_approved_digest(
        self, context: InboundContext, object_id: str, expected_sha256: str
    ) -> bool:
        dl = self.download(context, object_id)
        if dl.sha256 != expected_sha256:
            raise PermissionError("Approved artifact sha256 digest mismatch")
        return True

    def collect_garbage(
        self,
        context: InboundContext,
        *,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> dict[str, Any]:
        pinned = sorted(self._pinned_ids())
        fingerprint = hashlib.sha256(
            canonicalize(
                {
                    "kind": "artifact_gc",
                    "pinned": pinned,
                    "actor": context.principal_id,
                    "profile": context.profile_id,
                    "session": context.session_id,
                    "identity": context.identity_epoch,
                    "surface": context.source_scope,
                }
            )
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return event_lookup(db, context, request_id)

        def apply(db: sqlite3.Connection) -> bytes:
            authorize(db, context)
            now = time.time_ns() // 1_000_000
            rows = db.execute(
                "SELECT object_id,object_key FROM artifacts "
                "WHERE state='AVAILABLE' AND expires_at IS NOT NULL AND expires_at<=? "
                "ORDER BY created_at,object_id",
                (now,),
            ).fetchall()

            pinned_set = set(pinned)
            tombstoned: list[str] = []
            tombstoned_keys: list[str] = []
            for obj_id_raw, obj_key_raw in rows:
                oid = str(obj_id_raw)
                okey = str(obj_key_raw)
                if oid in pinned_set:
                    continue
                active_ref = db.execute(
                    "SELECT 1 FROM artifact_refs r "
                    "LEFT JOIN tasks t ON t.task_id=r.task_id "
                    "LEFT JOIN operations o ON o.operation_id=r.operation_id "
                    "WHERE r.object_id=? AND ("
                    "  (r.task_id IS NOT NULL "
                    "   AND t.state NOT IN ('SUCCEEDED','PARTIAL','FAILED','CANCELLED')) "
                    "  OR (r.operation_id IS NOT NULL AND o.state IN ("
                    "      'PROPOSED','AWAITING_APPROVAL','READY','CLAIMED',"
                    "      'DISPATCHING','UNKNOWN'))"
                    ")",
                    (oid,),
                ).fetchone()
                if active_ref is not None:
                    continue
                db.execute(
                    "UPDATE artifacts SET state='TOMBSTONED' "
                    "WHERE object_id=? AND state='AVAILABLE'",
                    (oid,),
                )
                tombstoned.append(oid)
                tombstoned_keys.append(okey)

            registered_keys = [
                str(r[0])
                for r in db.execute(
                    "SELECT object_key FROM artifacts "
                    "WHERE state IN ('AVAILABLE','STAGING','QUARANTINED')"
                ).fetchall()
            ]
            receipt: dict[str, Any] = {
                "tombstoned_object_ids": tombstoned,
                "tombstoned_keys": tombstoned_keys,
                "registered_keys": registered_keys,
            }
            _append_artifact_event(
                db,
                context,
                "art_gc_batch",
                None,
                None,
                "ARTIFACT_GC_COMPLETED",
                request_id,
                fingerprint,
                receipt,
                now,
            )
            return canonicalize(receipt)

        raw = self._writer.submit(
            WriterCommand(request_id, fingerprint, "normal", deadline_monotonic_ms, apply, lookup)
        ).result(
            timeout=max(0.001, (deadline_monotonic_ms - time.monotonic() * 1000) / 1000 + 0.05)
        )
        res = dict(strict_json(raw))
        for key in res.get("tombstoned_keys", []):
            self._resolve_object_key(str(key)).unlink(missing_ok=True)

        # Clean up unregistered staging and orphan object files
        orphan_removed = 0
        for st_file in (self._root / "staging").iterdir():
            if st_file.is_file() or st_file.is_symlink():
                st_file.unlink(missing_ok=True)
                orphan_removed += 1
        reg_set = set(str(k) for k in res.get("registered_keys", []))
        for obj_file in (self._root / "objects").rglob("*.bin"):
            rel = obj_file.relative_to(self._root).as_posix()
            if rel not in reg_set:
                obj_file.unlink(missing_ok=True)
                orphan_removed += 1
        return {
            "tombstoned_object_ids": list(res["tombstoned_object_ids"]),
            "orphan_files_removed": orphan_removed,
        }
