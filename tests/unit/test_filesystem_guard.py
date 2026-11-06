import hashlib
import os

import pytest
from openbot.tools.filesystem_guard import (
    WorkspaceFileGuard,
    build_safe_git_worktree_env_and_argv,
    build_safe_ripgrep_argv,
    validate_relative_workspace_path,
)


@pytest.mark.parametrize(
    "bad_path",
    [
        "",
        "/etc/passwd",
        "../outside.txt",
        "a/../../outside.txt",
        "\\server\\share\\file.txt",
        "//server/share/file.txt",
        "\\\\?\\C:\\Windows\\System32",
        "\\\\.\\PhysicalDrive0",
        "C:\\Users\\admin\\secret.txt",
        "dir/file.txt:secret:$DATA",
        "CON",
        "sub/NUL.txt",
        "sub/COM1",
        "sub/trailingdot.",
        "sub/trailingspace ",
        "file\x00.txt",
        ".git/hooks/post-checkout",
        ".git/config",
        ".env",
        "keys/id_ed25519",
    ],
)
def test_native_os_attack_corpus_and_sensitive_paths_are_rejected(bad_path: str):
    with pytest.raises(PermissionError):
        validate_relative_workspace_path(bad_path)


def test_handle_guard_blocks_symlink_escape_and_parent_swap_race_and_verifies_old_hash(tmp_path):
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()
    outside = tmp_path / "outside_secret.txt"
    outside.write_text("top-secret", encoding="utf-8")

    guard = WorkspaceFileGuard(ws_root)

    # 1. Symlink inside workspace pointing outside is rejected by O_NOFOLLOW / lstat step walk
    (ws_root / "link_out.txt").symlink_to(outside)
    with pytest.raises(PermissionError, match="Symlink"):
        guard.read_bytes("link_out.txt")
    # 2. Create new file verifies parent inode and non-existence, then writes atomically
    snap_new = guard.observe("sub/hello.txt")
    assert snap_new.exists is False
    written_snap = guard.write_atomic("sub/hello.txt", b"v1", snap_new)
    assert written_snap.exists is True
    assert written_snap.sha256 == hashlib.sha256(b"v1").hexdigest()
    assert guard.read_bytes("sub/hello.txt") == b"v1"

    # 3. Stale old_sha256 is rejected on replacement
    with pytest.raises(PermissionError, match="hash|exists"):
        guard.write_atomic("sub/hello.txt", b"v2-stale", snap_new)

    # 4. Parent directory swapped with a symlink to outside directory between observe and write
    snap_v1 = guard.observe("sub/hello.txt")
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    (outside_dir / "hello.txt").write_bytes(b"v1")
    os.unlink(ws_root / "sub/hello.txt")
    os.rmdir(ws_root / "sub")
    (ws_root / "sub").symlink_to(outside_dir)

    with pytest.raises(PermissionError, match="Symlink|inode"):
        guard.write_atomic("sub/hello.txt", b"pwned", snap_v1)
    assert (outside_dir / "hello.txt").read_bytes() == b"v1"


def test_git_worktree_and_ripgrep_guards_block_hooks_filters_and_user_config(tmp_path):
    repo = tmp_path / "repo"
    git_dir = repo / ".git"
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True)
    canary = tmp_path / "hook_executed.canary"
    hook = hooks_dir / "post-checkout"
    hook.write_text(f"#!/bin/sh\ntouch {canary}\n", encoding="utf-8")
    hook.chmod(0o755)

    # 1. Malicious filter or fsmonitor in .git/config is rejected BEFORE any git invocation
    (git_dir / "config").write_text(
        '[core]\n\tfsmonitor = "touch /tmp/pwn"\n[filter "evil"]\n\tclean = "sh -c evil"\n',
        encoding="utf-8",
    )
    with pytest.raises(PermissionError, match="Unsafe Git config"):
        build_safe_git_worktree_env_and_argv(repo, tmp_path / "wt_out", "HEAD")

    # 2. Clean .git/config produces isolated env + argv with core.hooksPath=/dev/null
    (git_dir / "config").write_text("[core]\n\trepositoryformatversion = 0\n", encoding="utf-8")
    env, argv = build_safe_git_worktree_env_and_argv(repo, tmp_path / "wt_out", "HEAD")
    assert "core.hooksPath=/dev/null" in argv
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert not canary.exists()

    # 3. Ripgrep builder strips RIPGREP_CONFIG_PATH, forces --no-config/--no-pre, and rejects --pre
    rg_env, rg_argv = build_safe_ripgrep_argv(
        repo, "--pre=sh", ambient_env={"RIPGREP_CONFIG_PATH": "/tmp/evil.rgrc", "PATH": "/usr/bin"}
    )
    assert "RIPGREP_CONFIG_PATH" not in rg_env
    assert "--no-config" in rg_argv
    assert "--no-pre" in rg_argv
    # Pattern is placed after '--' so leading-dash patterns cannot inject flags like --pre
    dash_idx = rg_argv.index("--")
    assert rg_argv[dash_idx + 1] == "--pre=sh"


def test_reads_stop_at_the_bound_instead_of_draining_to_eof(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    guard = WorkspaceFileGuard(ws)
    (ws / "exact.bin").write_bytes(b"a" * 4096)

    assert guard.read_bytes("exact.bin", max_bytes=4096) == b"a" * 4096
    with pytest.raises(PermissionError, match="FILE_READ_BOUND_EXCEEDED"):
        guard.read_bytes("exact.bin", max_bytes=4095)

    # A sparse gigabyte must never be materialised by a bounded read or a metadata call.
    sparse = ws / "sparse.bin"
    sparse.write_bytes(b"")
    os.truncate(sparse, 1 << 30)
    with pytest.raises(PermissionError, match="FILE_READ_BOUND_EXCEEDED"):
        guard.read_bytes("sparse.bin", max_bytes=1 << 20)
    meta = guard.metadata("sparse.bin")
    assert (meta.exists, meta.sha256, meta.size_bytes) == (True, None, 1 << 30)


def test_observe_is_pure_and_write_creates_the_approved_parent(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    guard = WorkspaceFileGuard(ws)

    snap = guard.observe("new_dir/dir.txt")
    assert snap.exists is False
    assert not (ws / "new_dir").exists(), "read-only observation must not create directories"

    written = guard.write_atomic("new_dir/dir.txt", b"v1", snap)
    assert written.exists is True
    assert (ws / "new_dir" / "dir.txt").read_bytes() == b"v1"
