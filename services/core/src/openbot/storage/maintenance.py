"""Online SQLite backup, artifact GC-pinned manifest verification, and safe restore."""

import hashlib
import os
import shutil
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from openbot.artifacts.store import ArtifactStore
from openbot.contracts import canonicalize, strict_json
from openbot.storage.inbox import InboundContext, authorize
from openbot.storage.migrate import connect
from openbot.storage.writer import Writer


@dataclass(frozen=True, slots=True)
class BackupManifest:
    schema_version: int
    db_sha256: str
    artifacts: tuple[dict[str, Any], ...]
    secret_refs: tuple[str, ...]
    status: str
    created_at_ms: int
    contains_secret_values: Literal[False] = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "db_sha256": self.db_sha256,
            "artifacts": list(self.artifacts),
            "secret_refs": list(self.secret_refs),
            "status": self.status,
            "created_at_ms": self.created_at_ms,
            "contains_secret_values": False,
        }


@dataclass(frozen=True, slots=True)
class RestoreVerificationReport:
    restored_db_path: Path
    restored_artifacts_count: int
    unknown_operations: tuple[str, ...]
    revoked_approvals: tuple[str, ...]
    missing_secret_refs: tuple[str, ...]
    reconfiguration_required: bool


class DiskWaterlineGuard:
    """Hard-block write dispatches when disk free space drops below 512MB (V1-070)."""

    MIN_FREE_BYTES: int = 512 * 1024 * 1024

    def __init__(self, target_path: Path, *, min_free_bytes: int = MIN_FREE_BYTES) -> None:
        self._path = target_path.resolve()
        self._min_free = min_free_bytes

    def check_writable(self, *, simulated_free_bytes: int | None = None) -> dict[str, int | bool]:
        free_bytes = (
            simulated_free_bytes
            if simulated_free_bytes is not None
            else shutil.disk_usage(self._path if self._path.exists() else self._path.parent).free
        )
        if free_bytes < self._min_free:
            raise PermissionError(
                f"DISK_LOW_WATERLINE_TRIPPED: free={free_bytes} < required={self._min_free}"
            )
        return {"writable": True, "free_bytes": free_bytes, "min_free_bytes": self._min_free}


@dataclass(frozen=True, slots=True)
class UpgradeTransactionReport:
    from_version: str
    to_version: str
    final_state: Literal["UPGRADED_ACTIVE", "ROLLED_BACK_TO_BACKUP"]
    backup_manifest_sha256: str
    preserved_unknown_operations: tuple[str, ...]
    exported_plaintext_secrets: Literal[False] = False
    replayed_unknown_actions: Literal[False] = False


class DatabaseMaintenanceService:
    """Coordinate SQLite online backup with Artifact GC pins and safe post-restore state."""

    def __init__(
        self,
        db_path: Path,
        writer: Writer,
        artifact_store: ArtifactStore,
        blob_root: Path,
    ) -> None:
        self._db_path = db_path
        self._writer = writer
        self._artifact_store = artifact_store
        self._blob_root = blob_root.resolve()

    def create_backup(
        self,
        context: InboundContext,
        backup_dir: Path,
        *,
        on_pinned_hook: Callable[[], None] | None = None,
    ) -> BackupManifest:
        if backup_dir.exists():
            raise ValueError("backup_dir must not already exist")
        backup_dir.mkdir(parents=True, exist_ok=False, mode=0o700)

        # 1. Read active artifact IDs and secret_refs, and pin artifacts against concurrent GC
        def inspect_live(db: sqlite3.Connection) -> tuple[int, list[dict[str, Any]], list[str]]:
            authorize(db, context)
            ver_row = db.execute(
                "SELECT coalesce(max(version),0) FROM schema_migrations"
            ).fetchone()
            schema_ver = int(ver_row[0]) if ver_row else 0
            art_rows = db.execute(
                "SELECT object_id,object_key,sha256,mime,bytes,classification "
                "FROM artifacts WHERE state='AVAILABLE' AND classification<>'SECRET' "
                "ORDER BY created_at,object_id"
            ).fetchall()
            arts = [
                {
                    "object_id": str(r[0]),
                    "object_key": str(r[1]),
                    "sha256": str(r[2]),
                    "mime": str(r[3]),
                    "bytes": int(r[4]),
                    "classification": str(r[5]),
                }
                for r in art_rows
            ]
            sec_rows = db.execute(
                "SELECT DISTINCT secret_ref FROM channel_accounts ORDER BY secret_ref"
            ).fetchall()
            s_refs = [str(r[0]) for r in sec_rows if r[0]]
            return schema_ver, arts, s_refs

        schema_ver, arts, s_refs = self._writer.read(inspect_live)
        pin_id = self._artifact_store.pin_for_backup([str(a["object_id"]) for a in arts])
        now = time.time_ns() // 1_000_000
        try:
            if on_pinned_hook is not None:
                on_pinned_hook()

            # 2. Consistent SQLite online backup (includes WAL state) + integrity/FK verification
            dst_db_path = backup_dir / "control.sqlite"
            fd = os.open(dst_db_path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
            os.close(fd)
            src_conn = connect(self._db_path, readonly=True)
            dst_conn = sqlite3.connect(dst_db_path)
            try:
                src_conn.backup(dst_conn)
                if dst_conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Backup database failed integrity_check")
                if dst_conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise RuntimeError("Backup database failed foreign_key_check")
            finally:
                dst_conn.close()
                src_conn.close()

            # 3. Copy and verify every referenced artifact blob on disk
            for art in arts:
                rel_key = str(art["object_key"])
                src_blob = (self._blob_root / rel_key).resolve()
                if not src_blob.is_file() or src_blob.is_symlink():
                    raise RuntimeError(f"Referenced artifact blob missing: {art['object_id']}")
                raw = src_blob.read_bytes()
                if len(raw) != int(art["bytes"]) or hashlib.sha256(raw).hexdigest() != str(
                    art["sha256"]
                ):
                    raise RuntimeError(
                        f"Referenced artifact blob hash/size mismatch: {art['object_id']}"
                    )
                dst_blob = backup_dir / rel_key
                dst_blob.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copyfile(src_blob, dst_blob)
                os.chmod(dst_blob, 0o600)

            db_sha = hashlib.sha256(dst_db_path.read_bytes()).hexdigest()
            manifest = BackupManifest(
                schema_version=schema_ver,
                db_sha256=db_sha,
                artifacts=tuple(arts),
                secret_refs=tuple(s_refs),
                status="VERIFIED",
                created_at_ms=now,
                contains_secret_values=False,
            )
            (backup_dir / "manifest.json").write_bytes(canonicalize(manifest.to_payload()))
            return manifest
        except BaseException:
            failed_doc = {"status": "FAILED", "created_at_ms": now}
            (backup_dir / "manifest.json").write_bytes(canonicalize(failed_doc))
            raise
        finally:
            self._artifact_store.unpin_backup(pin_id)

    def restore_backup(
        self,
        backup_dir: Path,
        target_db_path: Path,
        target_blob_root: Path,
        *,
        available_secret_refs: frozenset[str] = frozenset(),
    ) -> RestoreVerificationReport:
        manifest_path = backup_dir / "manifest.json"
        src_db_path = backup_dir / "control.sqlite"
        if not manifest_path.is_file() or not src_db_path.is_file():
            raise ValueError("Backup bundle is incomplete")
        manifest = dict(strict_json(manifest_path.read_bytes()))
        if manifest.get("status") != "VERIFIED":
            raise ValueError("Cannot restore an unverified or failed backup bundle")
        if hashlib.sha256(src_db_path.read_bytes()).hexdigest() != manifest.get("db_sha256"):
            raise ValueError("Backup database sha256 mismatch against manifest")

        # 1. Verify and restore artifact blobs before enabling the restored database
        target_blob_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        (target_blob_root / "staging").mkdir(parents=True, exist_ok=True, mode=0o700)
        (target_blob_root / "objects").mkdir(parents=True, exist_ok=True, mode=0o700)
        arts = list(manifest.get("artifacts", []))
        for art in arts:
            rel_key = str(art["object_key"])
            src_blob = backup_dir / rel_key
            if not src_blob.is_file() or src_blob.is_symlink():
                raise ValueError(f"Backup artifact blob missing: {art['object_id']}")
            raw = src_blob.read_bytes()
            if len(raw) != int(art["bytes"]) or hashlib.sha256(raw).hexdigest() != str(
                art["sha256"]
            ):
                raise ValueError(f"Backup artifact blob corrupted: {art['object_id']}")
            dst_blob = target_blob_root / rel_key
            dst_blob.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(src_blob, dst_blob)
            os.chmod(dst_blob, 0o600)

        # 2. Restore SQLite database via SQLite backup API and apply post-restore safety guards
        if target_db_path.exists():
            raise ValueError("target_db_path must not already exist")
        fd = os.open(target_db_path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        os.close(fd)
        b_conn = sqlite3.connect(src_db_path)
        t_conn = sqlite3.connect(target_db_path)
        try:
            b_conn.backup(t_conn)
        finally:
            t_conn.close()
            b_conn.close()

        db = connect(target_db_path)
        now = time.time_ns() // 1_000_000
        try:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Restored database failed integrity_check")
            if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise RuntimeError("Restored database failed foreign_key_check")

            db.execute("BEGIN IMMEDIATE")
            # Stop old runtime epochs so no stale epoch can dispatch
            db.execute(
                "UPDATE runtime_instances SET state='STOPPED',ended_at=? "
                "WHERE state IN ('STARTING','ACTIVE','DRAINING')",
                (now,),
            )
            # Revoke unconsumed approvals (PENDING/APPROVED -> REVOKED; CONSUMED never changes)
            revoked_aprs = [
                str(r[0])
                for r in db.execute(
                    "SELECT approval_id FROM approvals WHERE status IN ('PENDING','APPROVED')"
                ).fetchall()
            ]
            db.execute(
                "UPDATE approvals SET status='REVOKED',version=version+1 "
                "WHERE status IN ('PENDING','APPROVED')"
            )
            db.execute(
                "UPDATE operation_attempts SET status='ABANDONED',"
                "recovery_evidence_ref='ev_restored_backup_undispatched',finished_at=?,"
                "version=version+1 WHERE status='CLAIMED'",
                (now,),
            )
            db.execute(
                "UPDATE operations SET state='REVOKED',version=version+1,updated_at=?,"
                "completed_at=? WHERE state IN ('PROPOSED','AWAITING_APPROVAL','READY','CLAIMED')",
                (now, now),
            )

            # Convert any in-flight DISPATCHING operation to UNKNOWN and its Task to RECONCILING
            unknown_ops: list[str] = []
            for op_id, op_ver, task_id, att_id in db.execute(
                "SELECT operation_id,version,task_id,current_attempt_id FROM operations "
                "WHERE state='DISPATCHING'"
            ).fetchall():
                if att_id is not None:
                    db.execute(
                        "UPDATE operation_attempts SET status='UNKNOWN',version=version+1 "
                        "WHERE attempt_id=? AND status='DISPATCHING'",
                        (att_id,),
                    )
                db.execute(
                    "UPDATE operations SET state='UNKNOWN',unknown_reason='restored_from_backup',"
                    "version=version+1,updated_at=? WHERE operation_id=? AND version=?",
                    (now, op_id, int(op_ver)),
                )
                unknown_ops.append(str(op_id))
                t_row = db.execute(
                    "SELECT state,version FROM tasks WHERE task_id=?", (task_id,)
                ).fetchone()
                if t_row and t_row[0] in {"QUEUED", "RUNNING", "WAITING_APPROVAL", "PAUSED"}:
                    db.execute(
                        "UPDATE tasks SET state='RECONCILING',version=version+1,updated_at=? "
                        "WHERE task_id=? AND version=?",
                        (now, task_id, int(t_row[1])),
                    )

            for op_id_row in db.execute(
                "SELECT operation_id FROM operations WHERE state='UNKNOWN'"
            ).fetchall():
                if str(op_id_row[0]) not in unknown_ops:
                    unknown_ops.append(str(op_id_row[0]))

            # Verify secret_refs and disable channel_accounts whose secret_ref is unavailable
            missing_refs: list[str] = []
            for acc_id, sec_ref in db.execute(
                "SELECT account_id,secret_ref FROM channel_accounts"
            ).fetchall():
                s_ref = str(sec_ref)
                if s_ref not in available_secret_refs:
                    if s_ref not in missing_refs:
                        missing_refs.append(s_ref)
                    db.execute(
                        "UPDATE channel_accounts SET status='DISABLED' WHERE account_id=?",
                        (str(acc_id),),
                    )

            db.execute("COMMIT")
            return RestoreVerificationReport(
                restored_db_path=target_db_path,
                restored_artifacts_count=len(arts),
                unknown_operations=tuple(unknown_ops),
                revoked_approvals=tuple(revoked_aprs),
                missing_secret_refs=tuple(missing_refs),
                reconfiguration_required=bool(missing_refs),
            )
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def execute_upgrade_transaction(
        self,
        context: InboundContext,
        *,
        from_version: str,
        to_version: str,
        backup_dir: Path,
        rollback_target_db: Path,
        rollback_target_blobs: Path,
        candidate_health_ok: bool,
    ) -> UpgradeTransactionReport:
        self.create_backup(context, backup_dir)
        manifest_sha = hashlib.sha256((backup_dir / "manifest.json").read_bytes()).hexdigest()
        if not candidate_health_ok:
            restored = self.restore_backup(backup_dir, rollback_target_db, rollback_target_blobs)
            return UpgradeTransactionReport(
                from_version=from_version,
                to_version=to_version,
                final_state="ROLLED_BACK_TO_BACKUP",
                backup_manifest_sha256=manifest_sha,
                preserved_unknown_operations=restored.unknown_operations,
            )
        unknowns = self._writer.read(
            lambda db: tuple(
                str(r[0])
                for r in db.execute(
                    "SELECT operation_id FROM operations WHERE state='UNKNOWN'"
                ).fetchall()
            )
        )
        return UpgradeTransactionReport(
            from_version=from_version,
            to_version=to_version,
            final_state="UPGRADED_ACTIVE",
            backup_manifest_sha256=manifest_sha,
            preserved_unknown_operations=unknowns,
        )
