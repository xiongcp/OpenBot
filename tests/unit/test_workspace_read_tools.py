import hashlib

import pytest
from openbot.tools.workspace.read import (
    WorkspaceReadLimits,
    WorkspaceReadTools,
    build_pinned_ripgrep_command,
)


def test_pinned_ripgrep_command_binds_pattern_with_e_and_strips_pre_and_config(tmp_path):
    fake_rg = tmp_path / "rg"
    fake_rg.write_bytes(b"#!/bin/sh\nexit 0\n")
    rg_sha = hashlib.sha256(fake_rg.read_bytes()).hexdigest()

    # 1. Tampered binary hash is rejected
    with pytest.raises(PermissionError, match="sha256"):
        build_pinned_ripgrep_command(
            rg_binary=fake_rg,
            expected_sha256="0" * 64,
            workspace_root=tmp_path,
            pattern="todo",
        )

    # 2. Pattern starting with '--pre=' is bound after '-e' and cannot inject a preprocessor flag
    spec = build_pinned_ripgrep_command(
        rg_binary=fake_rg,
        expected_sha256=rg_sha,
        workspace_root=tmp_path,
        pattern="--pre=/bin/sh",
        ambient_env={"RIPGREP_CONFIG_PATH": "/tmp/evil.rgrc", "HTTP_PROXY": "http://evil:80"},
    )
    assert "RIPGREP_CONFIG_PATH" not in spec.env
    assert "HTTP_PROXY" not in spec.env
    assert "--json" in spec.argv
    assert "--no-config" in spec.argv
    assert "--no-pre" in spec.argv
    e_idx = spec.argv.index("-e")
    assert spec.argv[e_idx + 1] == "--pre=/bin/sh"


def test_list_read_utf8_boundary_binary_rejection_and_global_search_caps(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "good.py").write_text("line1\nmatch_token here\nline3\n", encoding="utf-8")
    (ws / "binary.bin").write_bytes(b"hello\x00world")
    (ws / "latin1.txt").write_bytes(b"\xff\xfeinvalid_utf8")
    (ws / "big.txt").write_bytes(b"a" * 1024)
    outside = tmp_path / "outside.txt"
    outside.write_text("match_token outside", encoding="utf-8")
    (ws / "symlink_out.txt").symlink_to(outside)

    limits = WorkspaceReadLimits(
        max_depth=3,
        max_files_scanned=50,
        max_single_file_bytes=512,
        max_global_matches=5,
        max_global_output_bytes=1024,
        max_line_chars=64,
    )
    tools = WorkspaceReadTools(ws, limits=limits)

    # 1. Read valid UTF-8 file returns sha256, line numbers, and untrusted provenance
    read_ok = tools.read("good.py", start_line=1, end_line=2)
    assert read_ok.sha256 == hashlib.sha256((ws / "good.py").read_bytes()).hexdigest()
    assert read_ok.lines == ((1, "line1"), (2, "match_token here"))
    assert read_ok.provenance_kind == "UNTRUSTED_WORKSPACE_FILE"
    assert read_ok.executable_instructions is False

    # 2. Binary, non-UTF-8, oversized, and out-of-root/symlink reads are rejected with clear codes
    with pytest.raises(ValueError, match="BINARY_FILE_UNSUPPORTED"):
        tools.read("binary.bin")
    with pytest.raises(ValueError, match="NON_UTF8_TEXT_UNSUPPORTED"):
        tools.read("latin1.txt")
    with pytest.raises(ValueError, match="FILE_TOO_LARGE"):
        tools.read("big.txt")
    with pytest.raises(PermissionError):
        tools.read("../outside.txt")
    with pytest.raises(PermissionError):
        tools.read("symlink_out.txt")

    # 3. Many small files hitting global match limit (5) and overlong line truncation (64 chars)
    many_dir = ws / "many"
    many_dir.mkdir()
    for i in range(12):
        (many_dir / f"f_{i:02d}.txt").write_text(
            f"match_token_{i}_" + ("X" * 100) + "\n", encoding="utf-8"
        )
    search_res = tools.search("match_token")
    assert len(search_res.matches) == 5
    assert search_res.truncated is True
    assert search_res.truncation_reason == "MAX_GLOBAL_MATCHES"
    assert all(len(m.line_text) <= 64 for m in search_res.matches)
    assert all(m.provenance_kind == "UNTRUSTED_WORKSPACE_FILE" for m in search_res.matches)
    assert all(m.executable_instructions is False for m in search_res.matches)


def test_listing_and_search_stay_inside_the_configured_byte_bound(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "huge.txt").write_bytes(b"x" * (1 << 20))
    (ws / "small.txt").write_bytes(b"needle here\n")
    tools = WorkspaceReadTools(ws, limits=WorkspaceReadLimits(max_single_file_bytes=4096))

    entries = tools.list_entries(".")
    assert [e.relative_path for e in entries] == ["huge.txt", "small.txt"]
    # Listing is metadata only: it must neither read nor hash the oversize file.
    assert (entries[0].size_bytes, entries[0].sha256) == (1 << 20, None)
    assert entries[1].size_bytes == len(b"needle here\n")

    with pytest.raises(ValueError, match="FILE_TOO_LARGE"):
        tools.read("huge.txt")

    search_res = tools.search("needle")
    assert [m.relative_path for m in search_res.matches] == ["small.txt"]
    assert search_res.files_scanned == 1, "the oversize file must be skipped, not drained"
