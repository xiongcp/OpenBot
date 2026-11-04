"""workspace.propose_patch and workspace.apply_patch with frozen old/new hashes and journal."""

import difflib
import hashlib
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openbot.artifacts.store import ArtifactStore
from openbot.storage.inbox import InboundContext
from openbot.tools.filesystem_guard import ObservedFileSnapshot, WorkspaceFileGuard
from openbot.tools.workspace.commit_journal import PatchCommitJournal


@dataclass(frozen=True, slots=True)
class FileEditSpec:
    relative_path: str
    old_snippet: str
    new_snippet: str


@dataclass(frozen=True, slots=True)
class FrozenFilePatchPlan:
    relative_path: str
    old_exists: bool
    old_sha256: str | None
    new_artifact_id: str
    new_artifact_key: str
    new_sha256: str
    new_bytes_len: int
    observed_snapshot: ObservedFileSnapshot
    diff_preview: str


@dataclass(frozen=True, slots=True)
class PatchProposalBundle:
    bundle_id: str
    task_id: str
    files: tuple[FrozenFilePatchPlan, ...]


@dataclass(frozen=True, slots=True)
class PatchApplyReport:
    bundle_id: str
    status: Literal["APPLIED", "ROLLED_BACK_AFTER_PARTIAL_FAILURE"]
    journal_path: Path
    recovery_actions: dict[str, str]
    claims_cross_file_atomicity: Literal[False] = False


class WorkspacePatchTool:
    """Freeze exact old/new hashes and new-content Artifacts before approval; apply atomically."""

    def __init__(
        self,
        workspace_root: Path,
        artifact_store: ArtifactStore,
        journal_root: Path,
    ) -> None:
        self._root = workspace_root.resolve()
        self._guard = WorkspaceFileGuard(self._root)
        self._artifacts = artifact_store
        self._journal_root = journal_root.resolve()

    def propose_patch(
        self,
        context: InboundContext,
        *,
        task_id: str,
        edits: tuple[FileEditSpec, ...],
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> PatchProposalBundle:
        if not edits:
            raise ValueError("edits must be non-empty")
        seen_paths: set[str] = set()
        plans: list[FrozenFilePatchPlan] = []

        for idx, edit in enumerate(edits):
            if edit.relative_path in seen_paths:
                raise ValueError(f"Duplicate path in patch proposal: {edit.relative_path}")
            seen_paths.add(edit.relative_path)

            snap = self._guard.observe(edit.relative_path)
            if not snap.exists:
                raise ValueError(f"TARGET_FILE_NOT_FOUND: {edit.relative_path}")
            old_raw = self._guard.read_bytes(edit.relative_path)
            if b"\x00" in old_raw:
                raise ValueError(f"BINARY_FILE_UNSUPPORTED: {edit.relative_path}")
            try:
                old_text = old_raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise ValueError(f"NON_UTF8_TEXT_UNSUPPORTED: {edit.relative_path}") from exc

            # Exact match count check: never guess on multiple matches or normalize CRLF
            occurrences = old_text.count(edit.old_snippet)
            if occurrences == 0:
                raise ValueError(f"HUNK_NOT_FOUND in {edit.relative_path}")
            if occurrences > 1:
                raise ValueError(
                    f"AMBIGUOUS_MULTIPLE_MATCHES ({occurrences}) in {edit.relative_path}"
                )

            new_text = old_text.replace(edit.old_snippet, edit.new_snippet, 1)
            new_raw = new_text.encode("utf-8")
            new_sha = hashlib.sha256(new_raw).hexdigest()
            diff_lines = difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"a/{edit.relative_path}",
                tofile=f"b/{edit.relative_path}",
            )
            diff_preview = "".join(diff_lines)

            art_rec = self._artifacts.put(
                context,
                data=new_raw,
                mime="text/plain; charset=utf-8",
                classification="WORKSPACE",
                scope_kind="TASK",
                task_id=task_id,
                purpose=f"patch_new_bytes:{edit.relative_path}",
                request_id=f"{request_id}:art:{idx}",
                deadline_monotonic_ms=deadline_monotonic_ms,
            )
            plans.append(
                FrozenFilePatchPlan(
                    relative_path=edit.relative_path,
                    old_exists=True,
                    old_sha256=snap.sha256,
                    new_artifact_id=art_rec.object_id,
                    new_artifact_key=art_rec.object_key,
                    new_sha256=new_sha,
                    new_bytes_len=len(new_raw),
                    observed_snapshot=snap,
                    diff_preview=diff_preview,
                )
            )

        return PatchProposalBundle(
            bundle_id="pbd_" + secrets.token_hex(12),
            task_id=task_id,
            files=tuple(plans),
        )

    def apply_patch(
        self,
        context: InboundContext,
        bundle: PatchProposalBundle,
        *,
        inject_failure_on_path: str | None = None,
    ) -> PatchApplyReport:
        # Phase 1: Re-verify ALL old file hashes, parent inodes, and approved new-byte Artifacts
        # before modifying any file in the workspace. Never fuzz or normalize line endings!
        prepared: list[tuple[FrozenFilePatchPlan, ObservedFileSnapshot, bytes, bytes]] = []
        for plan in bundle.files:
            self._artifacts.verify_approved_digest(context, plan.new_artifact_id, plan.new_sha256)
            dl = self._artifacts.download(context, plan.new_artifact_id)
            if dl.sha256 != plan.new_sha256 or len(dl.data) != plan.new_bytes_len:
                raise PermissionError("Approved new-content artifact digest or size changed")

            cur_snap = self._guard.observe(plan.relative_path)
            if cur_snap.exists != plan.old_exists or cur_snap.sha256 != plan.old_sha256:
                raise PermissionError(
                    f"Target file old_sha256 changed since proposal: {plan.relative_path}"
                )
            if cur_snap.parent_ino != plan.observed_snapshot.parent_ino:
                raise PermissionError(
                    f"Parent directory inode changed since proposal: {plan.relative_path}"
                )
            old_bytes = self._guard.read_bytes(plan.relative_path)
            prepared.append((plan, cur_snap, old_bytes, dl.data))

        # Phase 2: Write durable commit journal with exact pre-patch backups, then apply per-file
        journal = PatchCommitJournal(self._journal_root, bundle.bundle_id)
        for plan, _, old_bytes, _ in prepared:
            journal.record_Backup(
                relative_path=plan.relative_path,
                old_bytes=old_bytes,
                old_sha256=plan.old_sha256,
                new_sha256=plan.new_sha256,
            )

        for plan, cur_snap, _, new_bytes in prepared:
            if inject_failure_on_path == plan.relative_path:
                journal.mark_file_failed(plan.relative_path)
                actions = journal.recover_partial_failure(self._guard)
                return PatchApplyReport(
                    bundle_id=bundle.bundle_id,
                    status="ROLLED_BACK_AFTER_PARTIAL_FAILURE",
                    journal_path=journal.journal_path,
                    recovery_actions=dict(actions),
                    claims_cross_file_atomicity=False,
                )
            try:
                self._guard.write_atomic(plan.relative_path, new_bytes, cur_snap)
                journal.mark_file_applied(plan.relative_path)
            except BaseException:
                journal.mark_file_failed(plan.relative_path)
                journal.recover_partial_failure(self._guard)
                raise

        journal.complete()
        return PatchApplyReport(
            bundle_id=bundle.bundle_id,
            status="APPLIED",
            journal_path=journal.journal_path,
            recovery_actions={p.relative_path: "APPLIED" for p in bundle.files},
            claims_cross_file_atomicity=False,
        )
