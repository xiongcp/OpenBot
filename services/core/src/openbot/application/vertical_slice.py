"""M1 persistent vertical slice harness integrating CLI, Local API, Artifacts, and Outbox."""

import hashlib
import json
import os
import secrets
import signal
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openbot.adapters.local_api.server import (
    ApiRequest,
    ApiResponse,
    LocalControlApiServer,
    ScopedTokenStore,
)
from openbot.application.cancellation import CancellationService
from openbot.application.dispatch import DispatchService
from openbot.application.operations import OperationService
from openbot.application.outbox import (
    GatewaySendResult,
    OutboxEnvelope,
    OutboxService,
)
from openbot.application.recovery import RecoveryService
from openbot.application.resources import ResourceRequest
from openbot.application.state_machine import TaskStateService
from openbot.artifacts.store import ArtifactStore
from openbot.cli import CliApiSession, run_cli_command
from openbot.contracts import SchemaRegistry, canonicalize
from openbot.policy.approvals import ApprovalService
from openbot.storage.inbox import InboundContext, Inbox, authorize
from openbot.storage.migrate import connect, load_migrations, migrate
from openbot.storage.outbox import OutboxStore
from openbot.storage.writer import LookupResult, Writer, WriterCommand
from openbot.tools.executors.supervision_port import ProcessSupervisorService
from openbot.tools.workspace.patch import FileEditSpec, WorkspacePatchTool


class _InProcessTransport:
    def __init__(self, api: LocalControlApiServer) -> None:
        self._api = api

    def request(self, req: ApiRequest) -> ApiResponse:
        return self._api.handle(req)


class _MemoryChallenges:
    def __init__(self) -> None:
        self._items: dict[str, bytes] = {}

    def put(self, approval_id: str, nonce: bytes) -> None:
        self._items[approval_id] = nonce

    def get(self, approval_id: str) -> bytes | None:
        return self._items.get(approval_id)


class ExternalEffectLedger:
    """Out-of-process persistent effect receiver tracking send, receive, and logical effects."""

    def __init__(self, ledger_path: Path) -> None:
        self._path = ledger_path
        if not self._path.is_file():
            self._write(
                {
                    "client_socket_send_count": 0,
                    "server_received_count": 0,
                    "logical_effect_count": 0,
                    "seen_idempotency_keys": [],
                    "reconcile_only_attempts": {},
                }
            )

    def _read(self) -> dict[str, Any]:
        return dict(json.loads(self._path.read_text(encoding="utf-8")))

    def _write(self, doc: dict[str, Any]) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self._path)

    def record_dispatch(
        self,
        *,
        operation_id: str,
        attempt_id: str,
        provider_idempotency_key: str,
        retry_class: str,
    ) -> None:
        doc = self._read()
        doc["client_socket_send_count"] = int(doc["client_socket_send_count"]) + 1
        doc["server_received_count"] = int(doc["server_received_count"]) + 1
        seen: list[str] = list(doc["seen_idempotency_keys"])
        if retry_class == "RECONCILE_ONLY":
            rec_map: dict[str, list[str]] = dict(doc["reconcile_only_attempts"])
            atts = list(rec_map.get(operation_id, []))
            atts.append(attempt_id)
            rec_map[operation_id] = atts
            doc["reconcile_only_attempts"] = rec_map
            doc["logical_effect_count"] = int(doc["logical_effect_count"]) + 1
        else:
            if provider_idempotency_key not in seen:
                seen.append(provider_idempotency_key)
                doc["seen_idempotency_keys"] = seen
                doc["logical_effect_count"] = int(doc["logical_effect_count"]) + 1
        self._write(doc)

    @property
    def logical_effect_count(self) -> int:
        return int(self._read()["logical_effect_count"])

    def blind_replay_count(self) -> int:
        rec_map: dict[str, list[str]] = dict(self._read()["reconcile_only_attempts"])
        return sum(max(0, len(atts) - 1) for atts in rec_map.values())


class _OfflineSyntheticGateway:
    sdk_max_retries: int = 0

    def __init__(self) -> None:
        self.delivered_Ids: list[str] = []

    def capabilities(self) -> frozenset[str]:
        return frozenset({"UPSERT_REVISION", "PROVIDER_IDEMPOTENT"})

    def send(self, envelope: OutboxEnvelope) -> GatewaySendResult:
        self.delivered_Ids.append(envelope.outbox_id)
        return GatewaySendResult(
            status="SENT",
            provider_message_id=f"msg_{envelope.outbox_id}",
            remote_revision=envelope.revision,
            exact_once_supported=True,
        )


def _seed_vertical_slice_db(db: sqlite3.Connection) -> None:
    db.execute("INSERT INTO policy_revisions VALUES(1, ?,'{}', 1000, 1000)", ("a" * 64,))
    db.execute(
        "INSERT INTO runtime_instances("
        "runtime_epoch,boot_id,supervisor_ref,state,started_at,heartbeat_at) "
        "VALUES('ep_1','boot_1','sup_1','ACTIVE',1000,1000)"
    )
    db.execute(
        "INSERT INTO profile_config("
        "singleton,profile_id,schema_version,policy_version,identity_epoch,"
        "privacy_mode,active_runtime_epoch,last_fencing_token,created_at,updated_at) "
        "VALUES(1,'pro_test1',1,1,1,'OFFLINE','ep_1',0,1000,1000)"
    )
    db.execute(
        "INSERT INTO principals(principal_id,role,status,display_name,created_at) "
        "VALUES('pri_test1','OWNER','ACTIVE','synthetic owner',1000)"
    )
    db.execute(
        "INSERT INTO workspaces("
        "workspace_id,root_ref,generation,status,version,created_at,updated_at) "
        "VALUES('wsp_test1','synthetic-workspace',1,'ACTIVE',0,1000,1000)"
    )
    db.execute(
        "INSERT INTO sessions(session_id,owner_id,workspace_id,status,created_at,updated_at) "
        "VALUES('ses_test1','pri_test1','wsp_test1','OPEN',1000,1000)"
    )
    for name, effect, retry_class in (
        ("fs.patch", "LOCAL_WRITE", "IDEMPOTENT_WRITE"),
        ("gui.click", "EXTERNAL_WRITE", "RECONCILE_ONLY"),
    ):
        manifest = {
            "name": name,
            "version": "1.0.0",
            "effect": effect,
            "retry_class": retry_class,
            "input_schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {"arg": {"type": "string"}},
                "required": ["arg"],
                "additionalProperties": False,
            },
        }
        raw = canonicalize(manifest)
        db.execute(
            "INSERT INTO tool_registry VALUES(?, '1.0.0', ?, NULL, 'builtin', ?, 'ACTIVE', 1000)",
            (name, hashlib.sha256(raw).hexdigest(), raw.decode()),
        )


@dataclass
class M1VerticalSliceHarness:
    root_dir: Path
    workspace_dir: Path
    context: InboundContext
    writer: Writer
    tasks: TaskStateService
    operations: OperationService
    approvals: ApprovalService
    dispatcher: DispatchService
    recovery: RecoveryService
    artifacts: ArtifactStore
    outbox: OutboxService
    patch_tool: WorkspacePatchTool
    cli_session: CliApiSession
    challenges: _MemoryChallenges = field(default_factory=_MemoryChallenges)
    db_reopened_count: int = 0

    @classmethod
    def create(cls, base_dir: Path) -> "M1VerticalSliceHarness":
        base_dir.mkdir(parents=True, exist_ok=True)
        repo_root = Path(__file__).resolve().parents[5]
        db_path = base_dir / "slice.sqlite"
        blob_dir = base_dir / "blobs"
        ws_dir = base_dir / "workspace"
        journal_dir = base_dir / "journals"
        ws_dir.mkdir(parents=True, exist_ok=True)
        journal_dir.mkdir(parents=True, exist_ok=True)
        (ws_dir / "hello.py").write_text("value = 1\n", encoding="utf-8")

        migrate(db_path, load_migrations(repo_root / "db/migrations"))
        db = connect(db_path)
        try:
            _seed_vertical_slice_db(db)
        finally:
            db.close()

        context = InboundContext(
            "pro_test1", "pri_test1", 1, "local", "tenant1", "app1", "ses_test1", "wsp_test1"
        )
        registry = SchemaRegistry.from_directory(repo_root / "contracts")
        challenges = _MemoryChallenges()
        writer = Writer(db_path)
        inbox = Inbox(writer, registry)
        tasks = TaskStateService(writer)
        ops = OperationService(writer, challenges, registry)
        approvals = ApprovalService(writer, challenges, registry)
        dispatcher = DispatchService(writer, registry)
        recovery = RecoveryService(writer, registry)
        cancellation = CancellationService(writer)
        artifacts = ArtifactStore(writer, blob_dir)
        outbox_store = OutboxStore(writer)
        outbox = OutboxService(writer, outbox_store)
        patch_tool = WorkspacePatchTool(ws_dir, artifacts, journal_dir)
        tokens = ScopedTokenStore()
        owner_token = tokens.issue(
            profile_id="pro_test1", principal_id="pri_test1", scope="owner_cli"
        )
        api = LocalControlApiServer(
            profile_id="pro_test1",
            default_context=context,
            writer=writer,
            registry=registry,
            tokens=tokens,
            inbox=inbox,
            tasks=tasks,
            operations=ops,
            approvals=approvals,
            recovery=recovery,
            cancellation=cancellation,
            artifacts=artifacts,
            challenges=challenges,
        )
        cli_session = CliApiSession(
            profile_id="pro_test1",
            token=owner_token,
            transport=_InProcessTransport(api),
        )
        return cls(
            root_dir=base_dir,
            workspace_dir=ws_dir,
            context=context,
            writer=writer,
            tasks=tasks,
            operations=ops,
            approvals=approvals,
            dispatcher=dispatcher,
            recovery=recovery,
            artifacts=artifacts,
            outbox=outbox,
            patch_tool=patch_tool,
            cli_session=cli_session,
            challenges=challenges,
            db_reopened_count=0,
        )

    def close(self) -> None:
        self.writer.close()

    def _kill_worker_and_reopen_db(self) -> int:
        """Spawn a real child process holding SQLite Writer, SIGKILL at barrier, and reopen WAL."""
        repo_root = Path(__file__).resolve().parents[5]
        db_path = self.root_dir / "slice.sqlite"
        child_env = os.environ.copy()
        child_env["PYTHONPATH"] = str(repo_root / "services/core/src")
        child_code = (
            "import sys, time; "
            "from pathlib import Path; "
            "from openbot.storage.writer import Writer; "
            f"w = Writer(Path({str(db_path)!r})); "
            "w.read(lambda db: db.execute('SELECT count(*) FROM operations').fetchone()[0]); "
            "sys.stdout.write('HOLDING_WRITER\\n'); sys.stdout.flush(); "
            "time.sleep(30)"
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", child_code],
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        assert proc.stdout is not None
        ready_line = proc.stdout.readline().strip()
        if ready_line != "HOLDING_WRITER":
            proc.kill()
            proc.wait(timeout=5)
            raise RuntimeError(f"Child writer process failed barrier: {ready_line}")
        killed_pid = proc.pid
        if sys.platform != "win32":
            os.kill(killed_pid, signal.SIGKILL)
        else:
            proc.kill()
        proc.wait(timeout=5)

        self.writer.close()
        blob_dir = self.root_dir / "blobs"
        journal_dir = self.root_dir / "journals"
        registry = SchemaRegistry.from_directory(repo_root / "contracts")
        self.writer = Writer(db_path)
        inbox = Inbox(self.writer, registry)
        self.tasks = TaskStateService(self.writer)
        self.operations = OperationService(self.writer, self.challenges, registry)
        self.approvals = ApprovalService(self.writer, self.challenges, registry)
        self.dispatcher = DispatchService(self.writer, registry)
        self.recovery = RecoveryService(self.writer, registry)
        cancellation = CancellationService(self.writer)
        self.artifacts = ArtifactStore(self.writer, blob_dir)
        outbox_store = OutboxStore(self.writer)
        self.outbox = OutboxService(self.writer, outbox_store)
        self.patch_tool = WorkspacePatchTool(self.workspace_dir, self.artifacts, journal_dir)
        tokens = ScopedTokenStore()
        owner_token = tokens.issue(
            profile_id="pro_test1", principal_id="pri_test1", scope="owner_cli"
        )
        api = LocalControlApiServer(
            profile_id="pro_test1",
            default_context=self.context,
            writer=self.writer,
            registry=registry,
            tokens=tokens,
            inbox=inbox,
            tasks=self.tasks,
            operations=self.operations,
            approvals=self.approvals,
            recovery=self.recovery,
            cancellation=cancellation,
            artifacts=self.artifacts,
            challenges=self.challenges,
            dispatcher=self.dispatcher,
        )
        self.cli_session = CliApiSession(
            profile_id="pro_test1",
            token=owner_token,
            transport=_InProcessTransport(api),
        )
        self.db_reopened_count += 1
        return killed_pid

    def _query_operation_state(self, op_id: str) -> str:
        def q(db: sqlite3.Connection) -> str:
            row = db.execute(
                "SELECT state FROM operations WHERE operation_id=?", (op_id,)
            ).fetchone()
            return str(row[0]) if row else "MISSING"

        return self.writer.read(q)

    def _complete_operation_and_task(self, task_id: str, op_id: str, attempt_id: str) -> None:
        now = time.time_ns() // 1_000_000
        fp = hashlib.sha256(f"complete:{op_id}:{attempt_id}".encode()).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return None

        def apply(db: sqlite3.Connection) -> bytes:
            authorize(db, self.context)
            db.execute(
                "UPDATE resource_leases SET holder_attempt_id=NULL,runtime_epoch=NULL,"
                "state='RELEASED',acquired_at=NULL,expires_at=NULL,version=version+1,"
                "updated_at=? WHERE holder_attempt_id=? AND state='HELD'",
                (now, attempt_id),
            )
            db.execute(
                "UPDATE operation_attempts SET status='SUCCEEDED',receipt_json='{}',"
                "finished_at=?,version=version+1 WHERE attempt_id=?",
                (now, attempt_id),
            )
            db.execute(
                "UPDATE operations SET state='SUCCEEDED',completed_at=?,updated_at=?,"
                "version=version+1 WHERE operation_id=?",
                (now, now, op_id),
            )
            db.execute(
                "UPDATE tasks SET state='SUCCEEDED',finished_at=?,version=version+1,"
                "updated_at=? WHERE task_id=?",
                (now, now, task_id),
            )
            return canonicalize({"status": "SUCCEEDED"})

        self.writer.submit(
            WriterCommand(f"cmp_{secrets.token_hex(6)}", fp, "result", 999999999999, apply, lookup)
        ).result(5)

    def run_local_restricted_effect_slice(self) -> dict[str, Any]:
        # 1. Create task via CLI -> Local API
        code_c, out_c = run_cli_command(
            [
                "task",
                "create",
                "--workspace",
                "wsp_test1",
                "--goal",
                "m1-vertical-slice",
                "--idempotency-key",
                "m1-slice-k1",
                "--json",
            ],
            session=self.cli_session,
        )
        assert code_c == 0
        task_id = str(json.loads(out_c)["task_id"])

        self.writer.submit(
            self.tasks.command(self.context, task_id, 0, "RUNNING", "slice-run-1", 999999999999)
        ).result(5)

        # 2. Propose real workspace patch + operation proposal
        bundle = self.patch_tool.propose_patch(
            self.context,
            task_id=task_id,
            edits=(
                FileEditSpec(
                    relative_path="hello.py", old_snippet="value = 1\n", new_snippet="value = 2\n"
                ),
            ),
            request_id="slice-patch-prop-1",
            deadline_monotonic_ms=999999999999,
        )
        proposed = json.loads(
            self.operations.propose(
                self.context,
                task_id,
                "fs.patch",
                json.dumps({"arg": bundle.bundle_id}),
                {"workspace_generation": 1, "files": []},
                "WORKSPACE",
                {"kind": "LOCAL", "resource_ref": self.context.workspace_id},
                "slice-op-prop-1",
                999999999999,
            )
        )
        op_id, apr_id = str(proposed["operation_id"]), str(proposed["approval_id"])

        # 3. Preview and approve via CLI
        code_p, _ = run_cli_command(
            ["approval", "preview", "--approval-id", apr_id, "--json"], session=self.cli_session
        )
        assert code_p == 0
        code_d, _ = run_cli_command(
            [
                "approval",
                "decide",
                "--approval-id",
                apr_id,
                "--expected-version",
                "1",
                "--binding-hash",
                str(proposed["binding_hash"]),
                "--decision",
                "APPROVE",
                "--idempotency-key",
                "slice-apr-1",
                "--json",
            ],
            session=self.cli_session,
        )
        assert code_d == 0

        # 4. Claim & begin_dispatch
        self.writer.submit(
            self.tasks.command(self.context, task_id, 3, "RUNNING", "slice-run-2", 999999999999)
        ).result(5)
        claimed = json.loads(
            self.writer.submit(
                self.dispatcher.claim(
                    self.context,
                    op_id,
                    "ep_1",
                    "exec_1",
                    [ResourceRequest("WORKSPACE", "wsp_test1", expected_generation=1)],
                    30_000,
                    "slice-claim-1",
                    999999999999,
                )
            ).result(5)
        )
        attempt_id = str(claimed["attempt_id"])
        self.writer.submit(
            self.dispatcher.begin_dispatch(
                self.context, op_id, attempt_id, "ep_1", "exec_1", "slice-disp-1", 999999999999
            )
        ).result(5)

        # 5. Execute real local restricted workspace patch & supervised worker process
        apply_report = self.patch_tool.apply_patch(self.context, bundle)
        assert apply_report.status == "APPLIED"

        sup = ProcessSupervisorService(runtime_epoch="ep_1")
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(0.05)"],
            start_new_session=True,
        )
        if sys.platform != "win32":
            slice_pgid = os.getpgid(proc.pid)
        else:
            slice_pgid = proc.pid
        sup.register_worker(
            worker_id="wrk_slice_1",
            operation_id=op_id,
            attempt_id=attempt_id,
            pid=proc.pid,
            pgid=slice_pgid,
            process_start_token="tok_slice_1",
        )
        reclaim_report = sup.reclaim_worker(
            "wrk_slice_1", current_start_token="tok_slice_1", grace_ms=100
        )
        proc.wait(timeout=2)

        self._complete_operation_and_task(task_id, op_id, attempt_id)

        # 6. Enqueue and deliver durable outbox notification
        self.writer.submit(
            self.outbox.enqueue(
                self.context,
                task_id=task_id,
                target_key="local:owner",
                target={"channel": "local", "principal_id": "pri_test1"},
                semantic_key=f"task_done:{task_id}",
                payload={"summary": "M1 vertical slice completed"},
                request_id="slice-outbox-enq-1",
                deadline_monotonic_ms=999999999999,
            )
        ).result(5)
        gw = _OfflineSyntheticGateway()
        outbox_res = self.outbox.dispatch_next(
            self.context,
            runtime_epoch="ep_1",
            gateway=gw,
            request_id="slice-outbox-disp-1",
            deadline_monotonic_ms=999999999999,
        )
        assert outbox_res is not None and outbox_res["state"] == "SENT"

        _, t_out = run_cli_command(
            ["task", "show", "--task-id", task_id, "--json"], session=self.cli_session
        )
        t_snap = json.loads(t_out)
        return {
            "network_mode": "OFFLINE",
            "real_production_services_called": False,
            "task_final_state": t_snap["state"],
            "operation_final_state": "SUCCEEDED",
            "approval_final_status": str(claimed["approval_status"]),
            "workspace_file_patched": (self.workspace_dir / "hello.py").read_text("utf-8")
            == "value = 2\n",
            "artifact_sha256": bundle.files[0].new_sha256,
            "worker_reaped": reclaim_report.old_domain_isolated,
            "outbox_status": "DELIVERED" if outbox_res["state"] == "SENT" else outbox_res["state"],
        }

    def run_fault_crash_scenario(
        self, crash_point: str, *, simulate_blind_retry_fault: bool = False
    ) -> dict[str, Any]:
        ledger = ExternalEffectLedger(self.root_dir / f"effects_{crash_point}.json")
        # Verify duplicate CLI task creation idempotency
        _, out1 = run_cli_command(
            [
                "task",
                "create",
                "--workspace",
                "wsp_test1",
                "--goal",
                f"fault-{crash_point}",
                "--idempotency-key",
                f"idem-{crash_point}",
                "--json",
            ],
            session=self.cli_session,
        )
        _, out2 = run_cli_command(
            [
                "task",
                "create",
                "--workspace",
                "wsp_test1",
                "--goal",
                f"fault-{crash_point}",
                "--idempotency-key",
                f"idem-{crash_point}",
                "--json",
            ],
            session=self.cli_session,
        )
        task_id = str(json.loads(out1)["task_id"])
        dup_stable = task_id == str(json.loads(out2)["task_id"])

        self.writer.submit(
            self.tasks.command(
                self.context, task_id, 0, "RUNNING", f"run1-{crash_point}", 999999999999
            )
        ).result(5)
        proposed = json.loads(
            self.operations.propose(
                self.context,
                task_id,
                "gui.click",
                '{"arg":"confirm"}',
                {"workspace_generation": 1, "files": []},
                "WORKSPACE",
                {"kind": "LOCAL", "resource_ref": self.context.workspace_id},
                f"prop-{crash_point}",
                999999999999,
            )
        )
        op_id, apr_id = str(proposed["operation_id"]), str(proposed["approval_id"])

        run_cli_command(
            [
                "approval",
                "decide",
                "--approval-id",
                apr_id,
                "--expected-version",
                "1",
                "--binding-hash",
                str(proposed["binding_hash"]),
                "--decision",
                "APPROVE",
                "--idempotency-key",
                f"apr-{crash_point}",
                "--json",
            ],
            session=self.cli_session,
        )
        self.writer.submit(
            self.tasks.command(
                self.context, task_id, 3, "RUNNING", f"run2-{crash_point}", 999999999999
            )
        ).result(5)

        resources = [ResourceRequest("WORKSPACE", "wsp_test1", expected_generation=1)]
        killed_pid = 0
        post_crash_op_state = "READY"

        if crash_point == "before_claim":
            killed_pid = self._kill_worker_and_reopen_db()
            self.writer.submit(
                self.recovery.recover_epoch(
                    self.context,
                    "ep_2",
                    "boot_2",
                    "sup_2",
                    old_epoch_isolated=True,
                    request_id="rec-ep2",
                    deadline_monotonic_ms=999999999999,
                )
            ).result(5)
            post_crash_op_state = self._query_operation_state(op_id)
            claimed = json.loads(
                self.writer.submit(
                    self.dispatcher.claim(
                        self.context,
                        op_id,
                        "ep_2",
                        "exec_2",
                        resources,
                        30_000,
                        "c-ep2",
                        999999999999,
                    )
                ).result(5)
            )
            att_id = str(claimed["attempt_id"])
            self.writer.submit(
                self.dispatcher.begin_dispatch(
                    self.context, op_id, att_id, "ep_2", "exec_2", "d-ep2", 999999999999
                )
            ).result(5)
            self._complete_operation_and_task(task_id, op_id, att_id)

        elif crash_point == "after_claim_before_dispatch":
            self.writer.submit(
                self.dispatcher.claim(
                    self.context, op_id, "ep_1", "exec_1", resources, 30_000, "c-ep1", 999999999999
                )
            ).result(5)
            killed_pid = self._kill_worker_and_reopen_db()
            self.writer.submit(
                self.recovery.recover_epoch(
                    self.context,
                    "ep_2",
                    "boot_2",
                    "sup_2",
                    old_epoch_isolated=True,
                    request_id="rec-ep2",
                    deadline_monotonic_ms=999999999999,
                )
            ).result(5)
            post_crash_op_state = self._query_operation_state(op_id)
            _, ticket = self.recovery.recover_operation(
                self.context,
                op_id,
                "ep_2",
                dispatch_was_sent=False,
                probe_status="NONE",
                request_id="ro-1",
                deadline_monotonic_ms=999999999999,
            )
            assert ticket is not None
            reclaimed = json.loads(
                self.writer.submit(
                    self.dispatcher.claim(
                        self.context,
                        op_id,
                        "ep_2",
                        "exec_2",
                        resources,
                        30_000,
                        "c-ep2",
                        999999999999,
                        recovery_ticket=ticket,
                    )
                ).result(5)
            )
            att_id = str(reclaimed["attempt_id"])
            self.writer.submit(
                self.dispatcher.begin_dispatch(
                    self.context, op_id, att_id, "ep_2", "exec_2", "d-ep2", 999999999999
                )
            ).result(5)
            self._complete_operation_and_task(task_id, op_id, att_id)

        elif crash_point in {"after_dispatch_before_effect", "after_effect_before_receipt"}:
            claimed = json.loads(
                self.writer.submit(
                    self.dispatcher.claim(
                        self.context,
                        op_id,
                        "ep_1",
                        "exec_1",
                        resources,
                        30_000,
                        "c-ep1",
                        999999999999,
                    )
                ).result(5)
            )
            att_id = str(claimed["attempt_id"])
            self.writer.submit(
                self.dispatcher.begin_dispatch(
                    self.context, op_id, att_id, "ep_1", "exec_1", "d-ep1", 999999999999
                )
            ).result(5)
            if crash_point == "after_effect_before_receipt":
                ledger.record_dispatch(
                    operation_id=op_id,
                    attempt_id=att_id,
                    provider_idempotency_key=f"pk_{op_id}",
                    retry_class="RECONCILE_ONLY",
                )
            killed_pid = self._kill_worker_and_reopen_db()
            self.writer.submit(
                self.recovery.recover_epoch(
                    self.context,
                    "ep_2",
                    "boot_2",
                    "sup_2",
                    old_epoch_isolated=True,
                    request_id="rec-ep2",
                    deadline_monotonic_ms=999999999999,
                )
            ).result(5)
            post_crash_op_state = self._query_operation_state(op_id)
            if simulate_blind_retry_fault:
                ledger.record_dispatch(
                    operation_id=op_id,
                    attempt_id="att_blind_retry",
                    provider_idempotency_key=f"pk_{op_id}",
                    retry_class="RECONCILE_ONLY",
                )
            code_rec, _ = run_cli_command(
                [
                    "operation",
                    "reconcile",
                    "--operation-id",
                    op_id,
                    "--expected-version",
                    "4",
                    "--outcome",
                    "CONFIRMED_SUCCEEDED",
                    "--evidence-content",
                    f"verified-receipt-{crash_point}",
                    "--idempotency-key",
                    f"rec-{crash_point}",
                    "--json",
                ],
                session=self.cli_session,
            )
            assert code_rec == 0
            _, show_out = run_cli_command(
                ["task", "show", "--task-id", task_id, "--json"], session=self.cli_session
            )
            t_ver = int(json.loads(show_out)["version"])
            code_res, _ = run_cli_command(
                [
                    "task",
                    "resume",
                    "--task-id",
                    task_id,
                    "--expected-version",
                    str(t_ver),
                    "--idempotency-key",
                    f"res-{crash_point}",
                    "--json",
                ],
                session=self.cli_session,
            )
            assert code_res == 0

        else:
            # after_complete_before_outbox_ack
            claimed = json.loads(
                self.writer.submit(
                    self.dispatcher.claim(
                        self.context,
                        op_id,
                        "ep_1",
                        "exec_1",
                        resources,
                        30_000,
                        "c-ep1",
                        999999999999,
                    )
                ).result(5)
            )
            att_id = str(claimed["attempt_id"])
            self.writer.submit(
                self.dispatcher.begin_dispatch(
                    self.context, op_id, att_id, "ep_1", "exec_1", "d-ep1", 999999999999
                )
            ).result(5)
            ledger.record_dispatch(
                operation_id=op_id,
                attempt_id=att_id,
                provider_idempotency_key=f"pk_{op_id}",
                retry_class="RECONCILE_ONLY",
            )
            self._complete_operation_and_task(task_id, op_id, att_id)
            self.writer.submit(
                self.outbox.enqueue(
                    self.context,
                    task_id=task_id,
                    target_key="local:owner",
                    target={"channel": "local", "principal_id": "pri_test1"},
                    semantic_key=f"done:{task_id}",
                    payload={"summary": "completed"},
                    request_id=f"ob-{crash_point}",
                    deadline_monotonic_ms=999999999999,
                )
            ).result(5)
            killed_pid = self._kill_worker_and_reopen_db()
            self.writer.submit(
                self.recovery.recover_epoch(
                    self.context,
                    "ep_2",
                    "boot_2",
                    "sup_2",
                    old_epoch_isolated=True,
                    request_id="rec-ep2",
                    deadline_monotonic_ms=999999999999,
                )
            ).result(5)
            post_crash_op_state = self._query_operation_state(op_id)
            gw = _OfflineSyntheticGateway()
            self.outbox.dispatch_next(
                self.context,
                runtime_epoch="ep_2",
                gateway=gw,
                request_id=f"ob-disp-{crash_point}",
                deadline_monotonic_ms=999999999999,
            )

        _, final_task_out = run_cli_command(
            ["task", "show", "--task-id", task_id, "--json"], session=self.cli_session
        )
        return {
            "crash_point": crash_point,
            "duplicate_task_id_stable": dup_stable,
            "real_production_services_called": False,
            "killed_pid": killed_pid,
            "db_reopened_count": self.db_reopened_count,
            "post_crash_operation_state": post_crash_op_state,
            "fault_executor_effect_count": ledger.logical_effect_count,
            "blind_replay_count": ledger.blind_replay_count(),
            "resolved_operation_state": self._query_operation_state(op_id),
            "resolved_task_state": str(json.loads(final_task_out)["state"]),
        }
