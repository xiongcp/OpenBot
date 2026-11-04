"""Explicit syntax/static validation in bounded parser workers and operation-scoped rollback."""

import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openbot.storage.inbox import InboundContext
from openbot.tools.filesystem_guard import WorkspaceFileGuard
from openbot.tools.workspace.commit_journal import PatchCommitJournal
from openbot.tools.workspace.patch import PatchProposalBundle, WorkspacePatchTool


@dataclass(frozen=True, slots=True)
class PinnedGrammarAsset:
    language: str
    asset_path: Path
    expected_sha256: str
    allow_runtime_download: Literal[False] = False
    allow_workspace_binary: Literal[False] = False


class PinnedGrammarRegistry:
    """Verify pinned offline grammar assets and refuse workspace binaries or runtime downloads."""

    def __init__(self, *, workspace_root: Path, assets: dict[str, PinnedGrammarAsset]) -> None:
        ws_resolved = workspace_root.resolve()
        verified: dict[str, PinnedGrammarAsset] = {}
        for ext, asset in assets.items():
            if not asset.asset_path.is_file() or asset.asset_path.is_symlink():
                raise ValueError(f"CAPABILITY_UNAVAILABLE: offline grammar asset missing for {ext}")
            resolved_asset = asset.asset_path.resolve()
            if resolved_asset == ws_resolved or resolved_asset.is_relative_to(ws_resolved):
                raise PermissionError(
                    "Loading grammar binary from untrusted workspace is forbidden: "
                    f"{asset.asset_path}"
                )
            actual_sha = hashlib.sha256(resolved_asset.read_bytes()).hexdigest()
            if actual_sha != asset.expected_sha256:
                raise ValueError(
                    f"CAPABILITY_UNAVAILABLE: offline grammar sha256 mismatch for {ext}"
                )
            verified[ext] = asset
        self._assets = verified

    def require_for_path(self, relative_path: str) -> PinnedGrammarAsset:
        suffix = Path(relative_path).suffix.lower()
        if suffix not in self._assets:
            raise ValueError(
                f"CAPABILITY_UNAVAILABLE: language grammar for '{suffix}' is not installed offline"
            )
        return self._assets[suffix]


@dataclass(frozen=True, slots=True)
class SyntaxParseOutcome:
    relative_path: str
    language: str
    grammar_sha256: str
    valid: bool
    error_code: str | None
    functional_correctness_proven: Literal[False] = False


def _nesting_depth(source: str) -> int:
    depth = 0
    max_depth = 0
    for ch in source:
        if ch in "([{":
            depth += 1
            if depth > max_depth:
                max_depth = depth
        elif ch in ")]}":
            depth = max(0, depth - 1)
    return max_depth


class IsolatedParserWorker:
    """Run syntax parsing in a bounded subprocess so native parser faults never crash the daemon."""

    def __init__(
        self,
        registry: PinnedGrammarRegistry,
        *,
        max_input_bytes: int = 262_144,
        max_nesting_depth: int = 128,
        timeout_ms: int = 2_000,
    ) -> None:
        self._registry = registry
        self._max_bytes = max_input_bytes
        self._max_depth = max_nesting_depth
        self._timeout_ms = timeout_ms

    def parse(
        self,
        relative_path: str,
        raw_bytes: bytes,
        *,
        simulate_native_crash: bool = False,
    ) -> SyntaxParseOutcome:
        asset = self._registry.require_for_path(relative_path)
        if len(raw_bytes) > self._max_bytes:
            return SyntaxParseOutcome(
                relative_path=relative_path,
                language=asset.language,
                grammar_sha256=asset.expected_sha256,
                valid=False,
                error_code="MAX_INPUT_BYTES_EXCEEDED",
            )
        try:
            source = raw_bytes.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return SyntaxParseOutcome(
                relative_path=relative_path,
                language=asset.language,
                grammar_sha256=asset.expected_sha256,
                valid=False,
                error_code="NON_UTF8_INPUT",
            )
        if _nesting_depth(source) > self._max_depth:
            return SyntaxParseOutcome(
                relative_path=relative_path,
                language=asset.language,
                grammar_sha256=asset.expected_sha256,
                valid=False,
                error_code="MAX_NESTING_DEPTH_EXCEEDED",
            )

        worker_code = (
            "import os, sys; os._exit(139)"
            if simulate_native_crash
            else "import ast, sys; ast.parse(sys.stdin.read())"
        )
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", worker_code],
                input=source.encode("utf-8"),
                capture_output=True,
                timeout=max(0.05, self._timeout_ms / 1000),
                env={"LC_ALL": "C.UTF-8"},
            )
        except subprocess.TimeoutExpired:
            return SyntaxParseOutcome(
                relative_path=relative_path,
                language=asset.language,
                grammar_sha256=asset.expected_sha256,
                valid=False,
                error_code="PARSER_WORKER_TIMEOUT",
            )

        if proc.returncode == 0:
            return SyntaxParseOutcome(
                relative_path=relative_path,
                language=asset.language,
                grammar_sha256=asset.expected_sha256,
                valid=True,
                error_code=None,
            )
        if proc.returncode < 0 or proc.returncode >= 128:
            return SyntaxParseOutcome(
                relative_path=relative_path,
                language=asset.language,
                grammar_sha256=asset.expected_sha256,
                valid=False,
                error_code="PARSER_WORKER_CRASHED",
            )
        return SyntaxParseOutcome(
            relative_path=relative_path,
            language=asset.language,
            grammar_sha256=asset.expected_sha256,
            valid=False,
            error_code="SYNTAX_ERROR",
        )


@dataclass(frozen=True, slots=True)
class ValidatedPatchOutcome:
    bundle_id: str
    status: Literal["APPLIED_AND_VALIDATED", "REVERTED_ON_SYNTAX_ERROR"]
    parse_results: tuple[SyntaxParseOutcome, ...]
    recovery_actions: dict[str, str]
    functional_correctness_proven: Literal[False] = False


class WorkspaceValidationCoordinator:
    """Apply frozen patch bundle, run isolated syntax validation, and revert on failure."""

    def __init__(self, patch_tool: WorkspacePatchTool, parser_worker: IsolatedParserWorker) -> None:
        self._patch_tool = patch_tool
        self._parser = parser_worker

    def apply_and_validate(
        self, context: InboundContext, bundle: PatchProposalBundle
    ) -> ValidatedPatchOutcome:
        guard = WorkspaceFileGuard(self._patch_tool._root)
        # Record pre-apply snapshots for operation-scoped revert if post-apply validation fails
        pre_backups: dict[str, bytes] = {}
        for plan in bundle.files:
            pre_backups[plan.relative_path] = guard.read_bytes(plan.relative_path)

        apply_report = self._patch_tool.apply_patch(context, bundle)
        parse_outcomes: list[SyntaxParseOutcome] = []
        failed_any = False
        for plan in bundle.files:
            new_bytes = guard.read_bytes(plan.relative_path)
            res = self._parser.parse(plan.relative_path, new_bytes)
            parse_outcomes.append(res)
            if not res.valid:
                failed_any = True

        if not failed_any:
            return ValidatedPatchOutcome(
                bundle_id=bundle.bundle_id,
                status="APPLIED_AND_VALIDATED",
                parse_results=tuple(parse_outcomes),
                recovery_actions=apply_report.recovery_actions,
                functional_correctness_proven=False,
            )

        # Revert ONLY the files modified by THIS operation that still match new_sha256;
        # never touch unrelated user files in the workspace!
        journal = PatchCommitJournal(self._patch_tool._journal_root, bundle.bundle_id + "_val")
        for plan in bundle.files:
            journal.record_Backup(
                relative_path=plan.relative_path,
                old_bytes=pre_backups[plan.relative_path],
                old_sha256=plan.old_sha256,
                new_sha256=plan.new_sha256,
            )
            journal.mark_file_applied(plan.relative_path)
        actions = journal.recover_partial_failure(guard)
        return ValidatedPatchOutcome(
            bundle_id=bundle.bundle_id,
            status="REVERTED_ON_SYNTAX_ERROR",
            parse_results=tuple(parse_outcomes),
            recovery_actions=dict(actions),
            functional_correctness_proven=False,
        )
