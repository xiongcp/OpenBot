"""M1 security tool threat regression corpus verifying zero unauthorized side effects (OB-045)."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from openbot.contracts import ContractError, canonicalize, strict_json
from openbot.observability.redaction import RedactionPipeline
from openbot.policy.secrets.broker import SecretBroker, build_minimal_child_spawn_spec
from openbot.tools.executors.process import (
    ControlledProcessExecutor,
    ProcessExecutionPlan,
    ProcessResourceLimits,
    RawWorkerOutcome,
)
from openbot.tools.executors.supervision_port import ProcessSupervisorService
from openbot.tools.filesystem_guard import WorkspaceFileGuard
from openbot.tools.workspace.read import build_pinned_ripgrep_command
from openbot.tools.workspace.validation import (
    IsolatedParserWorker,
    PinnedGrammarAsset,
    PinnedGrammarRegistry,
)


@dataclass(frozen=True, slots=True)
class ThreatRegressionReport:
    cases_verified: tuple[str, ...]
    total_unauthorized_side_effects: int
    all_blocked: bool


class _FloodWorker:
    def run_isolated(self, plan: ProcessExecutionPlan) -> RawWorkerOutcome:
        del plan
        return RawWorkerOutcome(
            client_pid=1001,
            container_id="cnt_flood_1",
            exit_code=0,
            signal=None,
            timed_out=False,
            cancelled=False,
            container_confirmed_stopped=True,
            stdout_chunks=(b"A" * 2048, b"B" * 2048),
            stderr_chunks=(),
        )


class _KeychainMemBackend:
    backend_id: str = "macos.Keychain"

    def __init__(self, initial: dict[str, bytes]) -> None:
        self._store = dict(initial)

    def get_secret(self, secret_ref: str) -> bytes:
        return self._store[secret_ref]

    def set_secret(self, secret_ref: str, value: bytes) -> None:
        self._store[secret_ref] = value

    def delete_secret(self, secret_ref: str) -> None:
        self._store.pop(secret_ref, None)


class M1ThreatRegressionSuite:
    """Execute the M1 security and recovery threat regression corpus against real guards."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def run_all(self) -> ThreatRegressionReport:
        unauthorized_effects = 0
        verified: list[str] = []

        # 1. JCS deep mutation & duplicate key rejection
        nested = {"outer": {"items": [1, 2, 3]}}
        frozen_bytes = canonicalize(nested)
        nested["outer"]["items"].append(999)
        if canonicalize(nested) == frozen_bytes:
            unauthorized_effects += 1
        dup_blocked = False
        try:
            strict_json('{"a":1,"a":2}')
        except ContractError:
            dup_blocked = True
        if not dup_blocked:
            unauthorized_effects += 1
        verified.append("jcs_deep_mutation_and_duplicate_key")

        # 2. Path traversal & symlink escape
        ws = self._base / "ws_threat"
        outside = self._base / "outside_secret.txt"
        ws.mkdir(parents=True, exist_ok=True)
        outside.write_text("TOP_SECRET", encoding="utf-8")
        (ws / "escape_link.txt").symlink_to(outside)
        guard = WorkspaceFileGuard(ws)
        for bad_path in ("../outside_secret.txt", "escape_link.txt", ".git/hooks/pre-commit"):
            escaped = False
            try:
                guard.read_bytes(bad_path)
                escaped = True
            except PermissionError:
                pass
            if escaped:
                unauthorized_effects += 1
        verified.append("path_traversal_and_symlink_escape")

        # 3. Ripgrep & Git malicious config/preprocessor injection
        rg_bin = self._base / "pinned_rg"
        rg_bin.write_bytes(b"#!/bin/sh\nexit 0\n")
        rg_sha = hashlib.sha256(rg_bin.read_bytes()).hexdigest()
        spec = build_pinned_ripgrep_command(
            rg_binary=rg_bin,
            expected_sha256=rg_sha,
            workspace_root=ws,
            pattern="--pre=/bin/sh",
            ambient_env={
                "RIPGREP_CONFIG_PATH": "/tmp/evil_rgrc",
                "GIT_CONFIG_GLOBAL": "/tmp/evil_gitconfig",
                "LD_PRELOAD": "/tmp/evil.so",
                "PATH": "/usr/bin",
            },
        )
        if "--no-config" not in spec.argv or "--no-pre" not in spec.argv:
            unauthorized_effects += 1
        if "RIPGREP_CONFIG_PATH" in spec.env or "LD_PRELOAD" in spec.env:
            unauthorized_effects += 1
        verified.append("rg_and_git_malicious_config_injection")

        # 4. Parser runtime download & workspace binary rejection
        ws_grammar = ws / "evil_grammar.wasm"
        ws_grammar.write_bytes(b"wasm")
        ws_grammar_blocked = False
        try:
            PinnedGrammarRegistry(
                workspace_root=ws,
                assets={
                    ".py": PinnedGrammarAsset(
                        language="python",
                        asset_path=ws_grammar,
                        expected_sha256=hashlib.sha256(b"wasm").hexdigest(),
                    )
                },
            )
        except PermissionError:
            ws_grammar_blocked = True
        if not ws_grammar_blocked:
            unauthorized_effects += 1

        safe_grammar = self._base / "safe_python.grammar"
        safe_grammar.write_bytes(b"pinned_grammar_v1")
        reg = PinnedGrammarRegistry(
            workspace_root=ws,
            assets={
                ".py": PinnedGrammarAsset(
                    language="python",
                    asset_path=safe_grammar,
                    expected_sha256=hashlib.sha256(b"pinned_grammar_v1").hexdigest(),
                )
            },
        )
        parser = IsolatedParserWorker(reg)
        missing_ext_blocked = False
        try:
            parser.parse("file.rs", b"fn main() {}")
        except ValueError:
            missing_ext_blocked = True
        if not missing_ext_blocked:
            unauthorized_effects += 1
        verified.append("parser_runtime_download_and_crash_isolation")

        # 5. Secret leak & offline scanner enforcement
        secret_val = "sk-live-supersecretvalue999999"
        broker = SecretBroker(
            _KeychainMemBackend({"keychain:provider:openai:key1": secret_val.encode("utf-8")})
        )
        broker.resolve_for_model_provider("keychain:provider:openai:key1", "openai")
        cross_compartment_blocked = False
        try:
            broker.resolve_for_feishu_gateway("keychain:provider:openai:key1")
        except PermissionError:
            cross_compartment_blocked = True
        argv_leak_blocked = False
        try:
            build_minimal_child_spawn_spec(
                argv=("/usr/bin/python3", f"--key={secret_val}"),
                isolated_workdir=ws,
                host_home=self._base / "fake_home",
                mounts=(),
                broker=broker,
            )
        except PermissionError:
            argv_leak_blocked = True
        if not cross_compartment_blocked or not argv_leak_blocked:
            unauthorized_effects += 1
        redactor = RedactionPipeline(registered_secrets=(secret_val,))
        red_res = redactor.sanitize_sink(
            sink="stdout", text=f" leaked {secret_val} ", data_class="WORKSPACE"
        )
        if secret_val in red_res.sanitized_text or redactor.contract().network_verification_enabled:
            unauthorized_effects += 1
        verified.append("secret_leak_and_offline_scanner_enforcement")

        # 6. Output flood truncation & shell metacharacter / wrapper rejection
        shell_blocked = False
        try:
            ProcessExecutionPlan(
                operation_id="op_1",
                attempt_id="att_1",
                dispatch_id="dsp_1",
                action_label="test",
                executable="/bin/sh",
                argv=("/bin/sh", "-c", "echo pwned"),
                workspace_snapshot_digest="a" * 64,
                execution_backend="ISOLATED_CONTAINER",
                image_digest="sha256:" + "b" * 64,
                network_mode="NONE",
                isolated_home="/tmp/h",
                isolated_tmpdir="/tmp/t",
                env={},
                limits=ProcessResourceLimits(max_output_bytes=512),
            ).validate()
        except PermissionError:
            shell_blocked = True
        if not shell_blocked:
            unauthorized_effects += 1

        exec_engine = ControlledProcessExecutor(
            worker=_FloodWorker(),
            isolation_backend_qualified=True,
            redactor=redactor,
        )
        flood_plan = ProcessExecutionPlan(
            operation_id="op_1",
            attempt_id="att_1",
            dispatch_id="dsp_1",
            action_label="test",
            executable="/usr/bin/python3",
            argv=("/usr/bin/python3", "-m", "pytest"),
            workspace_snapshot_digest="a" * 64,
            execution_backend="ISOLATED_CONTAINER",
            image_digest="sha256:" + "b" * 64,
            network_mode="NONE",
            isolated_home="/tmp/h",
            isolated_tmpdir="/tmp/t",
            env={},
            limits=ProcessResourceLimits(max_output_bytes=512),
        )
        flood_res = exec_engine.execute(flood_plan)
        if not flood_res.output_truncated or len(flood_res.stdout.encode("utf-8")) > 512:
            unauthorized_effects += 1
        verified.append("output_flood_truncation_and_shell_metachar_rejection")

        # 7. Unisolated worker residual blocks new dispatch
        sup = ProcessSupervisorService(runtime_epoch="ep_1")
        sup.register_worker(
            worker_id="wrk_res_1",
            operation_id="op_1",
            attempt_id="att_1",
            pid=999991,
            pgid=999991,
            process_start_token="tok_res_1",
        )
        reclaim = sup.reclaim_worker(
            "wrk_res_1",
            current_start_token="tok_res_1",
            simulated_residual_pids=(999992,),
        )
        if not reclaim.quarantine_required or reclaim.new_dispatch_allowed:
            unauthorized_effects += 1
        verified.append("unisolated_worker_residual_blocks_new_dispatch")

        return ThreatRegressionReport(
            cases_verified=tuple(verified),
            total_unauthorized_side_effects=unauthorized_effects,
            all_blocked=(unauthorized_effects == 0),
        )
