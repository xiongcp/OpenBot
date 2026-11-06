"""OS handle-backed workspace path guard, atomic file verification, and Git/rg isolation."""

import hashlib
import os
import re
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_READ_BYTES = 8 * 1024 * 1024
_READ_CHUNK_BYTES = 65_536

_WIN_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
)
_SENSITIVE_LEAF_NAMES = frozenset({"id_rsa", "id_ed25519", "id_ecdsa", "id_dsa", ".env"})
_SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
_UNSAFE_GIT_CONFIG_PATTERN = re.compile(
    r"(?im)^\s*(fsmonitor|hookspath|sshcommand|gitproxy|askpass|editor|pager)\s*=|"
    r"^\s*\[\s*filter\s+",
)


def validate_relative_workspace_path(
    raw_path: str, *, allow_sensitive: bool = False
) -> tuple[str, ...]:
    """Reject absolute, traversal, UNC, Win32 device/ADS, and sensitive workspace paths."""
    if not raw_path or not isinstance(raw_path, str):
        raise PermissionError("Workspace path must be a non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw_path):
        raise PermissionError("Workspace path contains control or NUL characters")
    if raw_path.startswith(("/", "\\")) or "\\" in raw_path:
        raise PermissionError("Absolute, UNC, or backslash paths are forbidden")
    if re.match(r"^[A-Za-z]:", raw_path):
        raise PermissionError("Windows drive-letter paths are forbidden")

    parts = tuple(raw_path.split("/"))
    if any(p in {"", ".", ".."} for p in parts):
        raise PermissionError("Empty, current-dir, or parent-traversal segments are forbidden")

    for part in parts:
        if ":" in part:
            raise PermissionError("Windows Alternate Data Stream (ADS) syntax is forbidden")
        if part.endswith((".", " ")):
            raise PermissionError("Trailing dot or space in path segment is forbidden")
        stem = part.split(".", 1)[0].upper()
        if stem in _WIN_RESERVED_NAMES:
            raise PermissionError(f"Windows reserved device name forbidden: {part}")

    lowered = tuple(p.lower() for p in parts)
    if lowered[0] == ".git":
        raise PermissionError("Direct access to .git metadata/hooks is forbidden")
    if not allow_sensitive:
        leaf = lowered[-1]
        if (
            leaf in _SENSITIVE_LEAF_NAMES
            or leaf.startswith(".env.")
            or leaf.endswith(_SENSITIVE_SUFFIXES)
        ):
            raise PermissionError(f"Sensitive credential path refused: {raw_path}")
    return parts


@dataclass(frozen=True, slots=True)
class ObservedFileSnapshot:
    relative_path: str
    exists: bool
    sha256: str | None
    size_bytes: int
    parent_dev: int
    parent_ino: int
    file_ino: int | None


class WorkspaceFileGuard:
    """Step-by-step directory descriptor walker using O_NOFOLLOW and inode verification."""

    def __init__(self, workspace_root: Path) -> None:
        if workspace_root.is_symlink() or not workspace_root.is_dir():
            raise PermissionError("Workspace root must be a real directory, not a symlink")
        self._root = workspace_root.resolve()
        st = os.lstat(self._root)
        if not stat.S_ISDIR(st.st_mode):
            raise PermissionError("Workspace root is not a directory")
        self._root_dev = st.st_dev
        self._root_ino = st.st_ino

    def _open_root_fd(self) -> int:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self._root, flags)
        try:
            st = os.fstat(fd)
            if st.st_dev != self._root_dev or st.st_ino != self._root_ino:
                raise PermissionError("Workspace root inode/device changed unexpectedly")
            return fd
        except BaseException:
            os.close(fd)
            raise

    def _walk_parent_fd(
        self, parts: tuple[str, ...], *, create_dirs: bool
    ) -> tuple[int, os.stat_result]:
        cur_fd = self._open_root_fd()
        dir_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            for seg in parts[:-1]:
                try:
                    st = os.lstat(seg, dir_fd=cur_fd)
                except FileNotFoundError:
                    if not create_dirs:
                        raise
                    os.mkdir(seg, 0o755, dir_fd=cur_fd)
                    st = os.lstat(seg, dir_fd=cur_fd)
                if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
                    raise PermissionError(f"Symlink or non-directory intermediate segment: {seg}")
                if st.st_dev != self._root_dev:
                    raise PermissionError("Cross-device mount inside workspace is forbidden")
                next_fd = os.open(seg, dir_flags, dir_fd=cur_fd)
                next_st = os.fstat(next_fd)
                if next_st.st_ino != st.st_ino or next_st.st_dev != self._root_dev:
                    os.close(next_fd)
                    raise PermissionError("Directory race detected during walk")
                os.close(cur_fd)
                cur_fd = next_fd
            parent_st = os.fstat(cur_fd)
            return cur_fd, parent_st
        except BaseException:
            os.close(cur_fd)
            raise

    def _read_from_parent_fd(
        self, parent_fd: int, leaf: str, max_bytes: int = DEFAULT_MAX_READ_BYTES
    ) -> tuple[bytes, os.stat_result]:
        lst = os.lstat(leaf, dir_fd=parent_fd)
        if stat.S_ISLNK(lst.st_mode) or not stat.S_ISREG(lst.st_mode):
            raise PermissionError(f"Symlink or non-regular file refused: {leaf}")
        if lst.st_dev != self._root_dev:
            raise PermissionError("Cross-device file refused")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(leaf, flags, dir_fd=parent_fd)
        try:
            fst = os.fstat(fd)
            if (
                not stat.S_ISREG(fst.st_mode)
                or fst.st_ino != lst.st_ino
                or fst.st_dev != self._root_dev
            ):
                raise PermissionError("File inode changed between lstat and open")
            chunks: list[bytes] = []
            total = 0
            while total <= max_bytes:
                buf = os.read(fd, min(_READ_CHUNK_BYTES, max_bytes + 1 - total))
                if not buf:
                    break
                chunks.append(buf)
                total += len(buf)
            if total > max_bytes:
                raise PermissionError(f"FILE_READ_BOUND_EXCEEDED: {leaf} is over {max_bytes} bytes")
            return b"".join(chunks), fst
        finally:
            os.close(fd)

    def read_bytes(self, rel_path: str, max_bytes: int = DEFAULT_MAX_READ_BYTES) -> bytes:
        parts = validate_relative_workspace_path(rel_path)
        parent_fd, _ = self._walk_parent_fd(parts, create_dirs=False)
        try:
            data, _ = self._read_from_parent_fd(parent_fd, parts[-1], max_bytes)
            return data
        finally:
            os.close(parent_fd)

    def metadata(self, rel_path: str) -> ObservedFileSnapshot:
        """Pure stat of one leaf: identity and size, without reading or creating anything."""
        parts = validate_relative_workspace_path(rel_path)
        parent_fd, parent_st = self._walk_parent_fd(parts, create_dirs=False)
        try:
            lst = os.lstat(parts[-1], dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
        if stat.S_ISLNK(lst.st_mode) or not stat.S_ISREG(lst.st_mode):
            raise PermissionError(f"Symlink or non-regular file refused: {parts[-1]}")
        if lst.st_dev != self._root_dev:
            raise PermissionError("Cross-device file refused")
        return ObservedFileSnapshot(
            relative_path=rel_path,
            exists=True,
            sha256=None,
            size_bytes=lst.st_size,
            parent_dev=parent_st.st_dev,
            parent_ino=parent_st.st_ino,
            file_ino=lst.st_ino,
        )

    def observe(
        self, rel_path: str, max_bytes: int = DEFAULT_MAX_READ_BYTES
    ) -> ObservedFileSnapshot:
        parts = validate_relative_workspace_path(rel_path)
        try:
            parent_fd, parent_st = self._walk_parent_fd(parts, create_dirs=False)
        except (FileNotFoundError, NotADirectoryError):
            # A missing parent is reported, never created: observation has no side effects.
            return ObservedFileSnapshot(
                relative_path=rel_path,
                exists=False,
                sha256=None,
                size_bytes=0,
                parent_dev=0,
                parent_ino=0,
                file_ino=None,
            )
        try:
            try:
                data, fst = self._read_from_parent_fd(parent_fd, parts[-1], max_bytes)
            except FileNotFoundError:
                return ObservedFileSnapshot(
                    relative_path=rel_path,
                    exists=False,
                    sha256=None,
                    size_bytes=0,
                    parent_dev=parent_st.st_dev,
                    parent_ino=parent_st.st_ino,
                    file_ino=None,
                )
            return ObservedFileSnapshot(
                relative_path=rel_path,
                exists=True,
                sha256=hashlib.sha256(data).hexdigest(),
                size_bytes=len(data),
                parent_dev=parent_st.st_dev,
                parent_ino=parent_st.st_ino,
                file_ino=fst.st_ino,
            )
        finally:
            os.close(parent_fd)

    def unlink_verified(self, rel_path: str, expected: ObservedFileSnapshot) -> None:
        """Remove a file only when its identity still matches the observed snapshot."""
        parts = validate_relative_workspace_path(rel_path)
        if expected.relative_path != rel_path or not expected.exists or expected.file_ino is None:
            raise PermissionError("Unlink snapshot does not identify an existing file")
        parent_fd, parent_st = self._walk_parent_fd(parts, create_dirs=False)
        try:
            if parent_st.st_dev != expected.parent_dev or parent_st.st_ino != expected.parent_ino:
                raise PermissionError("Parent directory inode changed since observation")
            leaf = parts[-1]
            lst = os.lstat(leaf, dir_fd=parent_fd)
            if (
                stat.S_ISLNK(lst.st_mode)
                or not stat.S_ISREG(lst.st_mode)
                or lst.st_ino != expected.file_ino
                or lst.st_dev != self._root_dev
                or lst.st_nlink > 1
            ):
                raise PermissionError("Refusing to unlink changed, linked, or non-regular file")
            os.unlink(leaf, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)

    def write_atomic(
        self, rel_path: str, data: bytes, expected: ObservedFileSnapshot
    ) -> ObservedFileSnapshot:
        parts = validate_relative_workspace_path(rel_path)
        if expected.relative_path != rel_path:
            raise PermissionError("Snapshot relative_path mismatch")
        # Only an approved write may create a missing parent; observation never does.
        create_parent = not expected.exists and not expected.parent_ino
        parent_fd, parent_st = self._walk_parent_fd(parts, create_dirs=create_parent)
        leaf = parts[-1]
        try:
            if not create_parent and (
                parent_st.st_dev != expected.parent_dev or parent_st.st_ino != expected.parent_ino
            ):
                raise PermissionError("Parent directory inode changed since observation")
            if expected.exists:
                try:
                    cur_bytes, cur_st = self._read_from_parent_fd(parent_fd, leaf)
                except FileNotFoundError as exc:
                    raise PermissionError("Expected existing file disappeared") from exc
                if cur_st.st_nlink > 1:
                    raise PermissionError("Refusing to overwrite multi-hardlinked file")
                if (
                    cur_st.st_ino != expected.file_ino
                    or hashlib.sha256(cur_bytes).hexdigest() != expected.sha256
                ):
                    raise PermissionError("Target file hash or inode changed since observation")
            else:
                try:
                    os.lstat(leaf, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
                else:
                    raise PermissionError("Target file already exists; expected new file")

            tmp_name = f".openbot_tmp_{secrets.token_hex(12)}"
            tmp_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            tmp_fd = os.open(tmp_name, tmp_flags, 0o600, dir_fd=parent_fd)
            try:
                view = memoryview(data)
                written = 0
                while written < len(view):
                    n = os.write(tmp_fd, view[written:])
                    if n <= 0:
                        raise OSError("Short write to temporary workspace file")
                    written += n
                os.fsync(tmp_fd)
            except BaseException:
                os.close(tmp_fd)
                try:
                    os.unlink(tmp_name, dir_fd=parent_fd)
                except OSError:
                    pass
                raise
            os.close(tmp_fd)
            os.replace(tmp_name, leaf, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            new_st = os.lstat(leaf, dir_fd=parent_fd)
            return ObservedFileSnapshot(
                relative_path=rel_path,
                exists=True,
                sha256=hashlib.sha256(data).hexdigest(),
                size_bytes=len(data),
                parent_dev=parent_st.st_dev,
                parent_ino=parent_st.st_ino,
                file_ino=new_st.st_ino,
            )
        finally:
            os.close(parent_fd)


def build_safe_git_worktree_env_and_argv(
    repo_root: Path, worktree_dest: Path, commit_ref: str
) -> tuple[dict[str, str], tuple[str, ...]]:
    """Audit .git/config and construct a hook/filter-disabled git worktree command."""
    if repo_root.is_symlink() or not repo_root.is_dir():
        raise PermissionError("Repository root must be a real directory")
    git_config = repo_root / ".git/config"
    if git_config.exists():
        if git_config.is_symlink():
            raise PermissionError("Symlink .git/config refused")
        cfg_text = git_config.read_text(encoding="utf-8", errors="replace")
        if _UNSAFE_GIT_CONFIG_PATTERN.search(cfg_text):
            raise PermissionError(
                "Unsafe Git config directive (hook/fsmonitor/filter/sshCommand) refused"
            )
    gitattributes = repo_root / ".gitattributes"
    if gitattributes.exists():
        attr_text = gitattributes.read_text(encoding="utf-8", errors="replace")
        if "filter=" in attr_text:
            raise PermissionError("Git filter attributes in .gitattributes refused")

    env = {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ATTR_NOSYSTEM": "1",
        "LC_ALL": "C",
    }
    argv = (
        "git",
        "-C",
        str(repo_root.resolve()),
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "protocol.allow=never",
        "worktree",
        "add",
        "--detach",
        str(worktree_dest),
        commit_ref,
    )
    return env, argv


def build_safe_ripgrep_argv(
    workspace_root: Path,
    pattern: str,
    *,
    relative_subpath: str = ".",
    max_filesize: str = "1M",
    ambient_env: dict[str, str] | None = None,
) -> tuple[dict[str, str], tuple[str, ...]]:
    """Strip RIPGREP_CONFIG_PATH and force --no-config / --no-pre for safe search."""
    if workspace_root.is_symlink() or not workspace_root.is_dir():
        raise PermissionError("Workspace root must be a real directory")
    if not pattern:
        raise ValueError("Search pattern must be non-empty")
    if relative_subpath != ".":
        validate_relative_workspace_path(relative_subpath)
    clean_env = {
        k: v
        for k, v in (ambient_env or {}).items()
        if k in {"PATH", "LANG", "LC_ALL"} and k != "RIPGREP_CONFIG_PATH"
    }
    argv = (
        "rg",
        "--no-config",
        "--no-pre",
        "--no-follow",
        "--color=never",
        "--line-number",
        f"--max-filesize={max_filesize}",
        "--",
        pattern,
        relative_subpath,
    )
    return clean_env, argv
