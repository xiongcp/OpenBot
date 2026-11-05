"""Verifiable non-vector workspace memory ledger with source_ref and hard forget (V1-083)."""

import re
import secrets
from dataclasses import dataclass, replace
from typing import Literal

from openbot.observability.redaction import RedactionPipeline

_VALID_SOURCE_REF = re.compile(r"^(?:user_explicit:[A-Za-z0-9_-]{3,64}|file_sha256:[0-9a-f]{64})$")


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: str
    owner_id: str
    workspace_id: str
    key: str
    content: str
    source_ref: str
    data_class: Literal["PUBLIC", "WORKSPACE"]
    created_at_ms: int
    expires_at_ms: int
    provenance_kind: Literal["TAINTED_EXTERNAL"] = "TAINTED_EXTERNAL"
    authoritative_grants: Literal[False] = False


class VerifiableMemoryService:
    """Workspace-scoped structured memory with source provenance and zero-recall hard forget."""

    def __init__(self, redactor: RedactionPipeline | None = None) -> None:
        self._redactor = redactor or RedactionPipeline()
        self._records: dict[str, MemoryRecord] = {}
        self._summary_cache: dict[tuple[str, str], str] = {}

    def remember(
        self,
        *,
        owner_id: str,
        workspace_id: str,
        key: str,
        content: str,
        source_ref: str,
        data_class: str,
        now_ms: int,
        ttl_ms: int = 86_400_000,
    ) -> MemoryRecord:
        if data_class not in {"PUBLIC", "WORKSPACE"}:
            raise PermissionError(f"MEMORY_CLASSIFICATION_FORBIDDEN: {data_class}")
        if not _VALID_SOURCE_REF.fullmatch(source_ref):
            raise PermissionError(f"MEMORY_UNVERIFIED_SOURCE_REF: {source_ref}")
        if ttl_ms <= 0:
            raise ValueError("ttl_ms must be positive")
        sanitized = self._redactor.sanitize_sink(
            sink="model_input", text=content, data_class=data_class
        ).sanitized_text
        rec = MemoryRecord(
            memory_id="mem_" + secrets.token_hex(12),
            owner_id=owner_id,
            workspace_id=workspace_id,
            key=key,
            content=sanitized,
            source_ref=source_ref,
            data_class="PUBLIC" if data_class == "PUBLIC" else "WORKSPACE",
            created_at_ms=now_ms,
            expires_at_ms=now_ms + ttl_ms,
        )
        self._records[rec.memory_id] = rec
        self._rebuild_cache(owner_id, workspace_id, now_ms=now_ms)
        return rec

    def _rebuild_cache(self, owner_id: str, workspace_id: str, *, now_ms: int) -> None:
        active = self.recall_active(owner_id=owner_id, workspace_id=workspace_id, now_ms=now_ms)
        if active:
            self._summary_cache[(owner_id, workspace_id)] = "\n".join(
                f"{r.key}: {r.content} [{r.source_ref}]" for r in active
            )
        else:
            self._summary_cache.pop((owner_id, workspace_id), None)

    def recall_active(
        self, *, owner_id: str, workspace_id: str, now_ms: int
    ) -> tuple[MemoryRecord, ...]:
        items = [
            r
            for r in self._records.values()
            if r.owner_id == owner_id
            and r.workspace_id == workspace_id
            and now_ms < r.expires_at_ms
        ]
        return tuple(sorted(items, key=lambda x: (x.created_at_ms, x.memory_id)))

    def correct_memory(
        self, memory_id: str, *, owner_id: str, workspace_id: str, new_content: str, now_ms: int
    ) -> MemoryRecord:
        rec = self._records.get(memory_id)
        if rec is None or rec.owner_id != owner_id or rec.workspace_id != workspace_id:
            raise PermissionError("MEMORY_NOT_FOUND_OR_SCOPE_MISMATCH")
        sanitized = self._redactor.sanitize_sink(
            sink="model_input", text=new_content, data_class=rec.data_class
        ).sanitized_text
        updated = replace(rec, content=sanitized)
        self._records[memory_id] = updated
        self._rebuild_cache(owner_id, workspace_id, now_ms=now_ms)
        return updated

    def hard_forget(self, memory_id: str, *, owner_id: str, workspace_id: str, now_ms: int) -> bool:
        rec = self._records.get(memory_id)
        if rec is None or rec.owner_id != owner_id or rec.workspace_id != workspace_id:
            raise PermissionError("MEMORY_NOT_FOUND_OR_SCOPE_MISMATCH")
        del self._records[memory_id]
        self._rebuild_cache(owner_id, workspace_id, now_ms=now_ms)
        return True

    def cached_summary(self, *, owner_id: str, workspace_id: str) -> str:
        return self._summary_cache.get((owner_id, workspace_id), "")
