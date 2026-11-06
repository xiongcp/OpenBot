"""Deterministic model-view compaction; the authoritative ledger is never modified (ADR-0014)."""

import hashlib
import json
from collections.abc import Sequence

from openbot.contracts import canonicalize
from openbot.domain.providers import Block, Text, ToolCall, ToolResult

MAX_HISTORY_BLOCKS = 1024
MAX_TOOL_RESULT_BYTES = 65_536
MAX_HISTORY_BYTES = 1_048_576
KEEP_RECENT_PAIRS = 6
# Room under the adapter/canonical 1 MiB cap for the system message and per-message framing.
MODEL_VIEW_BYTES = MAX_HISTORY_BYTES - 65_536
_BLOCK_OVERHEAD = 128
_ELIDED = b"ELIDED_TOOL_RESULT "


def _json_len(text: str) -> int:
    return len(json.dumps(text, ensure_ascii=False).encode())


def _block_size(block: Block) -> int:
    """Upper-bound estimate of one serialized message: JSON-escaped strings plus envelope."""
    if isinstance(block, Text):
        return _BLOCK_OVERHEAD + _json_len(block.text)
    if isinstance(block, ToolCall):
        args = _json_len(block.arguments.decode("utf-8", "replace"))
        return _BLOCK_OVERHEAD + args + _json_len(block.tool_name) + _json_len(block.call_id)
    if isinstance(block, ToolResult):
        result = _json_len(block.result.decode("utf-8", "replace"))
        return _BLOCK_OVERHEAD + result + _json_len(block.call_id)
    return _BLOCK_OVERHEAD


def _stub(result: ToolResult) -> ToolResult:
    meta = canonicalize(
        {
            "bytes": len(result.result),
            "call_id": result.call_id,
            "sha256": hashlib.sha256(result.result).hexdigest(),
        }
    )
    return ToolResult(result.call_id, _ELIDED + meta)


def compact_history(
    history: Sequence[Block],
    *,
    max_bytes: int = MODEL_VIEW_BYTES,
    keep_recent_pairs: int = KEEP_RECENT_PAIRS,
) -> tuple[Block, ...]:
    """Elide the oldest tool results first; calls, pairing, goal and recent results survive.

    `_size` over-estimates the JSON-escaped payload; the adapter still measures the canonical
    messages and rejects any overflow, so a bad estimate can never send more than the cap.
    """
    view = list(history)
    sizes = [_block_size(block) for block in view]
    total = sum(sizes)
    if total <= max_bytes and len(view) <= MAX_HISTORY_BLOCKS:
        return tuple(view)
    result_positions = [i for i, b in enumerate(view) if isinstance(b, ToolResult)]
    protected = set(result_positions[-keep_recent_pairs:]) if keep_recent_pairs else set()
    for pos in result_positions:
        if total <= max_bytes:
            break
        block = view[pos]
        if pos in protected or not isinstance(block, ToolResult):
            continue
        if not block.result.startswith(_ELIDED):
            view[pos] = _stub(block)
            new_size = _block_size(view[pos])
            total += new_size - sizes[pos]
            sizes[pos] = new_size
    if total > max_bytes or len(view) > MAX_HISTORY_BLOCKS:
        raise PermissionError("CONTEXT_WINDOW_EXHAUSTED")
    return tuple(view)
