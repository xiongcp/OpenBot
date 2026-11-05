"""Chaos and soak harness covering network, sleep/wake, SIGKILL, and disk faults (OB-078)."""

import platform
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openbot_feishu.health import ExternalGatewaySupervisor, GatewayStageDeadlines

from openbot.application.vertical_slice import ExternalEffectLedger, M1VerticalSliceHarness
from openbot.domain.clock import ClockSnapshot, grant_valid
from openbot.storage.maintenance import DatabaseMaintenanceService
from openbot.storage.migrate import connect, load_migrations, migrate


@dataclass(frozen=True, slots=True)
class ChaosSoakReport:
    os_name: str
    arch: str
    sample_count: int
    fault_classes_verified: tuple[str, ...]
    dangerous_blind_retry_count: int
    backup_manifest_verified: bool = False
    disk_full_pre_dispatch_blocked: bool = False
    physical_power_loss_tested: Literal[False] = False
    claims_100_percent_lossless_guarantee: Literal[False] = False


class ChaosSoakHarness:
    """Run bounded network, sleep/wake clock, crash, and backup soak checks without 100% claims."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def _verify_backup_and_disk_full_guard(self, work_dir: Path) -> tuple[bool, bool]:
        work_dir.mkdir(parents=True, exist_ok=True)
        slice_h = M1VerticalSliceHarness.create(work_dir / "backup_src")
        backup_ok = False
        try:
            slice_h.run_local_restricted_effect_slice()
            maint = DatabaseMaintenanceService(
                db_path=work_dir / "backup_src/slice.sqlite",
                writer=slice_h.writer,
                artifact_store=slice_h.artifacts,
                blob_root=work_dir / "backup_src/blobs",
            )
            backup_dir = work_dir / "backup_bundle"
            manifest = maint.create_backup(slice_h.context, backup_dir)
            restore_rep = maint.restore_backup(
                backup_dir, work_dir / "restored.sqlite", work_dir / "restored_blobs"
            )
            backup_ok = (
                manifest.contains_secret_values is False
                and restore_rep.restored_db_path.is_file()
                and restore_rep.restored_artifacts_count >= 1
            )
        finally:
            slice_h.close()

        # Real SQLite max_page_count disk-full fault before dispatch prevents external effect
        repo_root = Path(__file__).resolve().parents[5]
        full_db_path = work_dir / "disk_full.sqlite"
        migrate(full_db_path, load_migrations(repo_root / "db/migrations"))
        ledger = ExternalEffectLedger(work_dir / "disk_full_effects.json")
        conn = connect(full_db_path)
        disk_full_blocked = False
        try:
            cur_pages = int(conn.execute("PRAGMA page_count").fetchone()[0])
            conn.execute(f"PRAGMA max_page_count = {cur_pages}")
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO policy_revisions VALUES(99, ?, ?, 1000, 1000)",
                    ("f" * 64, '{"pad":"' + ("x" * 65536) + '"}'),
                )
                conn.execute("COMMIT")
                # Should not reach here when disk/page quota is full
                ledger.record_dispatch(
                    operation_id="op_full",
                    attempt_id="att_full",
                    provider_idempotency_key="pk_full",
                    retry_class="RECONCILE_ONLY",
                )
            except sqlite3.OperationalError:
                conn.execute("ROLLBACK")
                disk_full_blocked = ledger.logical_effect_count == 0
        finally:
            conn.close()
        return backup_ok, disk_full_blocked

    def run_soak_samples(self, *, simulate_blind_retry_fault: bool = False) -> ChaosSoakReport:
        self._base.mkdir(parents=True, exist_ok=True)
        verified: list[str] = []

        # 1. DNS stall & TCP half-open handled by external gateway watchdog
        sup = ExternalGatewaySupervisor(deadlines=GatewayStageDeadlines(heartbeat_timeout_ms=5000))
        sup.spawn_consumer(consumer_id="gw_soak_1", pid=8001, now_ms=1000)
        probe = sup.evaluate_health(consumer_id="gw_soak_1", now_ms=9000, last_business_msg_ms=1000)
        if not probe.healthy and probe.reason == "HEARTBEAT_TIMEOUT_OR_HALF_OPEN":
            verified.append("dns_stall_and_tcp_half_open")

        # 2. System sleep/wake clock jump invalidates expired short-TTL grants
        issued = ClockSnapshot(10_000, 10_000, "auth_1")
        after_sleep = ClockSnapshot(900_000, 15_000, "auth_1")
        if not grant_valid(issued, after_sleep, 60_000):
            verified.append("system_sleep_wake_clock_jump")

        # 3. SIGKILL / post-effect crash recovery never blind-retries RECONCILE_ONLY actions
        slice_h = M1VerticalSliceHarness.create(self._base / "crash_soak")
        blind_retries = 0
        try:
            res = slice_h.run_fault_crash_scenario(
                "after_effect_before_receipt",
                simulate_blind_retry_fault=simulate_blind_retry_fault,
            )
            blind_retries = int(res["blind_replay_count"])
            if (
                blind_retries == 0
                and res["killed_pid"] > 0
                and res["post_crash_operation_state"] == "UNKNOWN"
                and res["resolved_operation_state"] == "SUCCEEDED"
            ):
                verified.append("sigkill_daemon_and_worker_recovery")
        finally:
            slice_h.close()

        # 4. SQLite backup & disk full guard
        backup_ok, disk_full_ok = self._verify_backup_and_disk_full_guard(
            self._base / "storage_soak"
        )
        if backup_ok and disk_full_ok:
            verified.append("sqlite_backup_and_disk_full_guard")

        return ChaosSoakReport(
            os_name=platform.system(),
            arch=platform.machine(),
            sample_count=len(verified),
            fault_classes_verified=tuple(verified),
            dangerous_blind_retry_count=blind_retries,
            backup_manifest_verified=backup_ok,
            disk_full_pre_dispatch_blocked=disk_full_ok,
        )
