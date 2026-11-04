"""Per-file commit journal and partial-failure rollback without claiming cross-file atomicity."""

import hashlib
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from openbot.contracts import canonicalize, strict_json
from openbot.tools.filesystem_guard import WorkspaceFileGuard


@dataclass(frozen=True, slots=True)
class JournalEntry:
    relative_path: str
    old_exists: bool
    old_sha256: str | None
    new_sha256: str
    backup_file: str | None
    state: str


class PatchCommitJournal:
    """Durable file-level commit log for multi-file patch application and partial recovery."""

    def __init__(self, journal_root: Path, bundle_id: str) -> None:
        if journal_root.is_symlink():
            raise PermissionError("Journal root must not be a symlink")
        journal_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._dir = (journal_root / f"jnl_{bundle_id}_{secrets.token_hex(8)}").resolve()
        self._dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        self._manifest_path = self._dir / "journal.json"
        self._entries: dict[str, dict[str, Any]] = {}

    @property
    def journal_path(self) -> Path:
        return self._manifest_path

    def _flush(self, status: str) -> None:
        doc = {
            "status": status,
            "claims_cross_file_atomicity": False,
            "updated_at_ms": time.time_ns() // 1_000_000,
            "entries": list(self._entries.values()),
        }
        self._manifest_path.write_bytes(canonicalize(doc))

    def record_Backup(
        self,
        *,
        relative_path: str,
        old_bytes: bytes | None,
        old_sha256: str | None,
        new_sha256: str,
    ) -> None:
        backup_name: str | None = None
        if old_bytes is not None:
            backup_name = f"bak_{len(self._entries)}_{secrets.token_hex(6)}.bin"
            (self._dir / backup_name).write_bytes(old_bytes)
        self._entries[relative_path] = {
            "relative_path": relative_path,
            "old_exists": old_bytes is not None,
            "old_sha256": old_sha256,
            "new_sha256": new_sha256,
            "backup_file": backup_name,
            "state": "PREPARED",
        }
        self._flush("IN_PROGRESS")

    def mark_file_applied(self, relative_path: str) -> None:
        self._entries[relative_path]["state"] = "APPLIED"
        self._flush("IN_PROGRESS")

    def mark_file_failed(self, relative_path: str) -> None:
        self._entries[relative_path]["state"] = "FAILED_NOT_APPLIED"
        self._flush("PARTIAL_FAILURE")

    def complete(self) -> None:
        self._flush("COMPLETED")

    def recover_partial_failure(
        self, guard: WorkspaceFileGuard
    ) -> dict[str, Literal["RESTORED_ORIGINAL", "FAILED_NOT_APPLIED", "CONFLICT_USER_MODIFIED"]]:
        actions: dict[
            str, Literal["RESTORED_ORIGINAL", "FAILED_NOT_APPLIED", "CONFLICT_USER_MODIFIED"]
        ] = {}
        for rel_path, entry in reversed(list(self._entries.items())):
            if entry["state"] != "APPLIED":
                actions[rel_path] = "FAILED_NOT_APPLIED"
                entry["state"] = "FAILED_NOT_APPLIED"
                continue
            cur_snap = guard.observe(rel_path)
            if not cur_snap.exists or cur_snap.sha256 != entry["new_sha256"]:
                actions[rel_path] = "CONFLICT_USER_MODIFIED"
                entry["state"] = "CONFLICT_USER_MODIFIED"
                continue
            b_name = entry.get("backup_file")
            if b_name is not None:
                orig_bytes = (self._dir / str(b_name)).read_bytes()
                if hashlib.sha256(orig_bytes).hexdigest() != entry["old_sha256"]:
                    raise RuntimeError("Journal backup sha256 corrupted")
                guard.write_atomic(rel_path, orig_bytes, cur_snap)
            actions[rel_path] = "RESTORED_ORIGINAL"
            entry["state"] = "RESTORED_ORIGINAL"
        self._flush("ROLLED_BACK_AFTER_PARTIAL_FAILURE")
        return actions

    def read_manifest(self) -> dict[str, Any]:
        return dict(strict_json(self._manifest_path.read_bytes()))
