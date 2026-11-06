"""Structural guard for Tauri Rust sources when no cargo toolchain is available locally.

Not a substitute for `cargo test`; it catches gross corruption (e.g. a reversed or truncated
file) that would otherwise only surface in the desktop CI job.
"""

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "apps/desktop/src-tauri/src"
FIRST_ITEM = re.compile(r"^(use |mod |pub |fn |#|//|const |static |struct |enum |impl )")


def check_rust_source(text: str) -> None:
    first = next(line for line in text.splitlines() if line.strip())
    if not FIRST_ITEM.match(first):
        raise AssertionError(f"unexpected first line: {first[:60]!r}")
    stripped = re.sub(r'"(?:\\.|[^"\\])*"', '""', text)  # ignore braces inside strings
    if stripped.count("{") != stripped.count("}"):
        raise AssertionError("unbalanced braces")
    if not text.endswith("\n"):
        raise AssertionError("missing trailing newline")


@pytest.mark.parametrize("path", sorted(SRC.glob("*.rs")), ids=lambda p: p.name)
def test_rust_sources_are_structurally_sane(path):
    check_rust_source(path.read_text())


def test_guard_rejects_a_reversed_file():
    text = (SRC / "control.rs").read_text()
    with pytest.raises(AssertionError):
        check_rust_source(text[::-1])
