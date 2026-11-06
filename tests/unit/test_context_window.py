import hashlib
import json

import pytest
from openbot.application.context_window import compact_history
from openbot.domain.providers import Text, ToolCall, ToolResult


def chain(n, size):
    blocks = [Text("goal")]
    for i in range(n):
        blocks.append(ToolCall(f"c{i}", "workspace.read", json.dumps({"path": f"f{i}"}).encode()))
        blocks.append(ToolResult(f"c{i}", bytes([65 + i % 26]) * size))
    return blocks


def test_small_history_is_unchanged():
    blocks = chain(3, 10)
    assert compact_history(blocks) == tuple(blocks)


def test_old_results_are_elided_but_pairs_goal_and_recent_survive():
    blocks = chain(20, 60_000)
    view = compact_history(blocks, max_bytes=500_000, keep_recent_pairs=6)
    assert view[0] == Text("goal")
    calls = [b for b in view if isinstance(b, ToolCall)]
    results = [b for b in view if isinstance(b, ToolResult)]
    expected_ids = [f"c{i}" for i in range(20)]
    assert [c.call_id for c in calls] == [r.call_id for r in results] == expected_ids
    elided = [r.result.startswith(b"ELIDED_TOOL_RESULT ") for r in results]
    # Oldest-first and only as many as needed: elided results form a non-empty prefix.
    first_kept = elided.index(False)
    assert first_kept > 0 and not any(elided[first_kept:])
    assert not any(elided[14:])  # the 6 most recent pairs are never elided
    for old in results[:first_kept]:
        meta = json.loads(old.result.split(b" ", 1)[1])
        original = blocks[2 + 2 * int(old.call_id[1:])].result
        assert meta["sha256"] == hashlib.sha256(original).hexdigest()
    assert sum(len(r.result) for r in results) <= 500_000


def test_compaction_is_deterministic_and_does_not_mutate_input():
    blocks = chain(20, 60_000)
    before = list(blocks)
    assert compact_history(blocks, max_bytes=500_000) == compact_history(blocks, max_bytes=500_000)
    assert blocks == before


def test_exhausted_window_pauses_instead_of_dropping_recent_work():
    blocks = chain(8, 60_000)
    with pytest.raises(PermissionError, match="^CONTEXT_WINDOW_EXHAUSTED$"):
        compact_history(blocks, max_bytes=100_000, keep_recent_pairs=6)


def test_budget_counts_json_escaping_of_tool_results():
    blocks = [Text("goal")]
    for i in range(20):
        blocks.append(ToolCall(f"c{i}", "workspace.read", b'{"path":"f"}'))
        blocks.append(ToolResult(f"c{i}", b'"\n\\' * 10_000))  # 30 KB raw, ~60 KB escaped
    view = compact_history(blocks, max_bytes=500_000, keep_recent_pairs=6)
    escaped = sum(
        len(json.dumps(b.result.decode(), ensure_ascii=False).encode())
        for b in view
        if isinstance(b, ToolResult)
    )
    assert escaped <= 500_000
