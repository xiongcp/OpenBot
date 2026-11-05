"""Per-file commit journal and partial-failure rollback without claiming cross-file atomicity."""

import hashlib
import os
import secrets
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from openbot.contracts import canonicalize, strict_json
from openbot.tools.filesystem_guard import WorkspaceFileGuard


def _write_and_fsync(target: Path, data: bytes) -> None:
    tmp = target.with_name(f".{target.name}.{secrets.token_hex(6)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, target)
    if sys.platform != "win32":
        dir_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)


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

    def __init__(
        self,
        journal_root: Path,
        bundle_id: str,
        *,
        _existing_dir: Path | None = None,
        _loaded_entries: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._bundle_id = bundle_id
        if _existing_dir is not None:
            self._dir = _existing_dir.resolve()
            self._manifest_path = self._dir / "journal.json"
            self._entries = dict(_loaded_entries or {})
            return
        if journal_root.is_symlink():
            raise PermissionError("Journal root must not be a symlink")
        journal_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._dir = (journal_root / f"jnl_{bundle_id}_{secrets.token_hex(8)}").resolve()
        self._dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        self._manifest_path = self._dir / "journal.json"
        self._entries = {}

    @classmethod
    def load(cls, journal_path: Path) -> "PatchCommitJournal":
        """Reload a durable journal across processes after a daemon crash (V1-020)."""
        if journal_path.is_symlink() or not journal_path.is_file():
            raise PermissionError("JOURNAL_MISSING_OR_SYMLINK")
        try:
            doc = dict(strict_json(journal_path.read_bytes()))
        except Exception as exc:
            raise PermissionError("JOURNAL_CORRUPTED_OR_TRUNCATED") from exc
        if doc.get("schema_version") != 1 or not isinstance(doc.get("entries"), list):
            raise PermissionError("JOURNAL_SCHEMA_INVALID")
        entries_list = list(doc["entries"])
        expected_digest = hashlib.sha256(canonicalize(entries_list)).hexdigest()
        if doc.get("entries_sha256") != expected_digest:
            raise PermissionError("JOURNAL_ENTRIES_DIGEST_MISMATCH")
        entries_map: dict[str, dict[str, Any]] = {}
        for item in entries_list:
            if not isinstance(item, dict) or "relative_path" not in item:
                raise PermissionError("JOURNAL_ENTRY_INVALID")
            entries_map[str(item["relative_path"])] = dict(item)
        return cls(
            journal_path.parent.parent,
            str(doc.get("bundle_id", "reloaded")),
            _existing_dir=journal_path.parent,
            _loaded_entries=entries_map,
        )

    @property
    def journal_path(self) -> Path:
        return self._manifest_path

    def _flush(self, status: str) -> None:
        entries_list = list(self._entries.values())
        entries_digest = hashlib.sha256(canonicalize(entries_list)).hexdigest()
        doc = {
            "schema_version": 1,
            "bundle_id": self._bundle_id,
            "status": status,
            "claims_cross_file_atomicity": False,
            "updated_at_ms": time.time_ns() // 1_000_000,
            "entries_sha256": entries_digest,
            "entries": entries_list,
        }
        _write_and_fsync(self._manifest_path, canonicalize(doc))

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
            _write_and_fsync(self._dir / backup_name, old_bytes)
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
