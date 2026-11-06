"""Bounded workspace.list, workspace.read, and workspace.search tools with UTF-8 and FileGuard."""

import hashlib
import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openbot.tools.filesystem_guard import (
    WorkspaceFileGuard,
    validate_relative_workspace_path,
)


@dataclass(frozen=True, slots=True)
class WorkspaceReadLimits:
    max_depth: int = 8
    max_files_scanned: int = 200
    max_single_file_bytes: int = 262_144
    max_global_matches: int = 100
    max_global_output_bytes: int = 65_536
    max_line_chars: int = 1_024
    timeout_ms: int = 2_000


@dataclass(frozen=True, slots=True)
class RipgrepCommandSpec:
    rg_binary: Path
    binary_sha256: str
    argv: tuple[str, ...]
    env: dict[str, str]


@dataclass(frozen=True, slots=True)
class WorkspaceListEntry:
    relative_path: str
    kind: Literal["FILE", "DIR"]
    size_bytes: int
    sha256: str | None
    provenance_kind: Literal["UNTRUSTED_WORKSPACE_FILE"] = "UNTRUSTED_WORKSPACE_FILE"
    executable_instructions: Literal[False] = False


@dataclass(frozen=True, slots=True)
class FileReadResult:
    relative_path: str
    sha256: str
    size_bytes: int
    lines: tuple[tuple[int, str], ...]
    truncated: bool
    provenance_kind: Literal["UNTRUSTED_WORKSPACE_FILE"] = "UNTRUSTED_WORKSPACE_FILE"
    executable_instructions: Literal[False] = False


@dataclass(frozen=True, slots=True)
class SearchMatch:
    relative_path: str
    line_number: int
    line_text: str
    file_sha256: str
    provenance_kind: Literal["UNTRUSTED_WORKSPACE_FILE"] = "UNTRUSTED_WORKSPACE_FILE"
    executable_instructions: Literal[False] = False


@dataclass(frozen=True, slots=True)
class SearchResult:
    matches: tuple[SearchMatch, ...]
    files_scanned: int
    truncated: bool
    truncation_reason: str | None


def build_pinned_ripgrep_command(
    *,
    rg_binary: Path,
    expected_sha256: str,
    workspace_root: Path,
    pattern: str,
    relative_subpath: str = ".",
    limits: WorkspaceReadLimits | None = None,
    ambient_env: dict[str, str] | None = None,
) -> RipgrepCommandSpec:
    """Verify pinned rg binary hash, strip config/proxy env, and bind pattern with -e and --."""
    if not rg_binary.is_file() or rg_binary.is_symlink():
        raise PermissionError("Pinned ripgrep binary missing or is a symlink")
    actual_sha = hashlib.sha256(rg_binary.read_bytes()).hexdigest()
    if actual_sha != expected_sha256:
        raise PermissionError("Pinned ripgrep binary sha256 mismatch")
    if workspace_root.is_symlink() or not workspace_root.is_dir():
        raise PermissionError("Workspace root must be a real directory")
    if not pattern:
        raise ValueError("Search pattern must be non-empty")
    if relative_subpath != ".":
        validate_relative_workspace_path(relative_subpath)

    lim = limits or WorkspaceReadLimits()
    clean_env = {k: v for k, v in (ambient_env or {}).items() if k in {"PATH", "LANG", "LC_ALL"}}
    argv = (
        str(rg_binary.resolve()),
        "--json",
        "--no-config",
        "--no-pre",
        "--no-follow",
        "--color=never",
        f"--max-depth={lim.max_depth}",
        f"--max-filesize={lim.max_single_file_bytes}",
        "-e",
        pattern,
        "--",
        relative_subpath,
    )
    return RipgrepCommandSpec(
        rg_binary=rg_binary.resolve(),
        binary_sha256=actual_sha,
        argv=argv,
        env=clean_env,
    )


class WorkspaceReadTools:
    """Bounded workspace list/read/search guarded by WorkspaceFileGuard and UTF-8 rules."""

    def __init__(self, workspace_root: Path, *, limits: WorkspaceReadLimits | None = None) -> None:
        self._root = workspace_root.resolve()
        self._guard = WorkspaceFileGuard(self._root)
        self._limits = limits or WorkspaceReadLimits()

    def _iter_safe_relative_files(self, subpath: str = ".") -> list[str]:
        if subpath != ".":
            validate_relative_workspace_path(subpath)
            start_dir = (self._root / subpath).resolve()
        else:
            start_dir = self._root
        if not start_dir.is_relative_to(self._root):
            raise PermissionError("Subpath escapes workspace root")

        collected: list[str] = []
        for cur_root, dirs, files in os.walk(start_dir, followlinks=False):
            cur_path = Path(cur_root)
            rel_dir = cur_path.relative_to(self._root)
            depth = 0 if rel_dir == Path(".") else len(rel_dir.parts)
            if depth >= self._limits.max_depth:
                dirs.clear()
            else:
                safe_dirs: list[str] = []
                for d in sorted(dirs):
                    if d == ".git":
                        continue
                    dp = cur_path / d
                    try:
                        st = os.lstat(dp)
                    except OSError:
                        continue
                    if not stat.S_ISLNK(st.st_mode) and stat.S_ISDIR(st.st_mode):
                        safe_dirs.append(d)
                dirs[:] = safe_dirs

            for fname in sorted(files):
                rel_file = (cur_path / fname).relative_to(self._root).as_posix()
                try:
                    validate_relative_workspace_path(rel_file)
                    st = os.lstat(cur_path / fname)
                except (PermissionError, OSError):
                    continue
                if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
                    continue
                collected.append(rel_file)
                if len(collected) >= self._limits.max_files_scanned:
                    return collected
        return collected

    def list_entries(self, subpath: str = ".") -> tuple[WorkspaceListEntry, ...]:
        files = self._iter_safe_relative_files(subpath)
        entries: list[WorkspaceListEntry] = []
        for rel in files:
            # Listing is a metadata read: content is neither drained nor hashed here.
            meta = self._guard.metadata(rel)
            entries.append(
                WorkspaceListEntry(
                    relative_path=rel,
                    kind="FILE",
                    size_bytes=meta.size_bytes,
                    sha256=None,
                )
            )
        return tuple(entries)

    def read(
        self,
        rel_path: str,
        *,
        start_line: int = 1,
        end_line: int | None = None,
    ) -> FileReadResult:
        if start_line < 1 or (end_line is not None and end_line < start_line):
            raise ValueError("Invalid line range")
        raw = self._bounded_text_bytes(rel_path)
        if b"\x00" in raw:
            raise ValueError(f"BINARY_FILE_UNSUPPORTED: {rel_path} contains NUL bytes")
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError(f"NON_UTF8_TEXT_UNSUPPORTED: {rel_path} is not valid UTF-8") from exc

        all_lines = text.splitlines()
        hi = len(all_lines) if end_line is None else min(len(all_lines), end_line)
        selected: list[tuple[int, str]] = []
        truncated = False
        for lineno in range(start_line, hi + 1):
            line_str = all_lines[lineno - 1]
            if len(line_str) > self._limits.max_line_chars:
                line_str = line_str[: self._limits.max_line_chars]
                truncated = True
            selected.append((lineno, line_str))
        return FileReadResult(
            relative_path=rel_path,
            sha256=hashlib.sha256(raw).hexdigest(),
            size_bytes=len(raw),
            lines=tuple(selected),
            truncated=truncated,
        )

    def _bounded_text_bytes(self, rel_path: str) -> bytes:
        """Read at most max_single_file_bytes; a larger file is refused, never drained."""
        try:
            return self._guard.read_bytes(rel_path, self._limits.max_single_file_bytes)
        except PermissionError as exc:
            if "FILE_READ_BOUND_EXCEEDED" in str(exc):
                raise ValueError(
                    f"FILE_TOO_LARGE: {rel_path} exceeds max_single_file_bytes"
                ) from exc
            raise

    def search(self, pattern: str, *, subpath: str = ".") -> SearchResult:
        if not pattern:
            raise ValueError("Search pattern must be non-empty")
        start_ms = time.monotonic() * 1000
        files = self._iter_safe_relative_files(subpath)
        matches: list[SearchMatch] = []
        total_bytes = 0
        scanned = 0
        truncated = False
        reason: str | None = None

        for rel in files:
            if (time.monotonic() * 1000 - start_ms) >= self._limits.timeout_ms:
                truncated = True
                reason = "TIMEOUT_EXCEEDED"
                break
            try:
                raw = self._guard.read_bytes(rel, self._limits.max_single_file_bytes)
            except (PermissionError, OSError):
                continue
            scanned += 1
            if b"\x00" in raw:
                continue
            try:
                text = raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                continue
            f_sha = hashlib.sha256(raw).hexdigest()
            for idx, line in enumerate(text.splitlines(), start=1):
                if pattern in line:
                    clipped = line[: self._limits.max_line_chars]
                    entry_bytes = len(clipped.encode("utf-8")) + len(rel.encode("utf-8"))
                    if total_bytes + entry_bytes > self._limits.max_global_output_bytes:
                        truncated = True
                        reason = "MAX_GLOBAL_OUTPUT_BYTES"
                        return SearchResult(
                            matches=tuple(matches),
                            files_scanned=scanned,
                            truncated=True,
                            truncation_reason=reason,
                        )
                    matches.append(
                        SearchMatch(
                            relative_path=rel,
                            line_number=idx,
                            line_text=clipped,
                            file_sha256=f_sha,
                        )
                    )
                    total_bytes += entry_bytes
                    if len(matches) >= self._limits.max_global_matches:
                        truncated = True
                        reason = "MAX_GLOBAL_MATCHES"
                        return SearchResult(
                            matches=tuple(matches),
                            files_scanned=scanned,
                            truncated=True,
                            truncation_reason=reason,
                        )
        return SearchResult(
            matches=tuple(matches),
            files_scanned=scanned,
            truncated=truncated,
            truncation_reason=reason,
        )
