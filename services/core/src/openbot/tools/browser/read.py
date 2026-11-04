"""Bounded browser.open/extract tool with TAINTED_EXTERNAL and revision binding (OB-059)."""

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class BrowserReadLimits:
    max_nodes: int = 128
    max_text_chars: int = 512


@dataclass(frozen=True, slots=True)
class BrowserDomNodeSpec:
    element_index: int
    tag: str
    text: str
    attributes: dict[str, str]


@dataclass(frozen=True, slots=True)
class BoundElementRef:
    page_id: str
    frame_id: str
    snapshot_revision: int
    final_origin: str
    element_index: int
    tag: str
    text_digest: str


@dataclass(frozen=True, slots=True)
class ExtractedBrowserElement:
    ref: BoundElementRef
    tag: str
    text: str
    attributes: dict[str, str]
    provenance_kind: Literal["TAINTED_EXTERNAL"] = "TAINTED_EXTERNAL"


@dataclass(frozen=True, slots=True)
class BrowserPageSnapshot:
    page_id: str
    frame_id: str
    snapshot_revision: int
    final_url: str
    final_origin: str
    elements: tuple[ExtractedBrowserElement, ...]
    truncated: bool
    provenance_kind: Literal["TAINTED_EXTERNAL"] = "TAINTED_EXTERNAL"
    grants_policy_or_owner_authority: Literal[False] = False


class BrowserReadTool:
    """Extract bounded read-only DOM snapshots and invalidate element refs across navigations."""

    def __init__(self, *, limits: BrowserReadLimits | None = None) -> None:
        self._limits = limits or BrowserReadLimits()
        self._rev_by_page: dict[str, int] = {}

    def extract_snapshot(
        self,
        *,
        page_id: str,
        frame_id: str,
        final_url: str,
        nodes: tuple[BrowserDomNodeSpec, ...],
    ) -> BrowserPageSnapshot:
        parsed = urlparse(final_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        rev = self._rev_by_page.get(page_id, 0) + 1
        self._rev_by_page[page_id] = rev

        truncated = len(nodes) > self._limits.max_nodes
        extracted: list[ExtractedBrowserElement] = []
        for node in nodes[: self._limits.max_nodes]:
            if len(node.text) > self._limits.max_text_chars:
                text = node.text[: self._limits.max_text_chars]
                truncated = True
            else:
                text = node.text
            ref = BoundElementRef(
                page_id=page_id,
                frame_id=frame_id,
                snapshot_revision=rev,
                final_origin=origin,
                element_index=node.element_index,
                tag=node.tag,
                text_digest=text[:64],
            )
            extracted.append(
                ExtractedBrowserElement(
                    ref=ref,
                    tag=node.tag,
                    text=text,
                    attributes=dict(node.attributes),
                )
            )
        return BrowserPageSnapshot(
            page_id=page_id,
            frame_id=frame_id,
            snapshot_revision=rev,
            final_url=final_url,
            final_origin=origin,
            elements=tuple(extracted),
            truncated=truncated,
        )

    def resolve_element_ref(
        self, ref: BoundElementRef, *, current_snapshot: BrowserPageSnapshot
    ) -> ExtractedBrowserElement:
        if (
            ref.page_id != current_snapshot.page_id
            or ref.frame_id != current_snapshot.frame_id
            or ref.snapshot_revision != current_snapshot.snapshot_revision
            or ref.final_origin != current_snapshot.final_origin
        ):
            raise PermissionError("STALE_BROWSER_ELEMENT_REF")
        for el in current_snapshot.elements:
            if el.ref.element_index == ref.element_index and el.tag == ref.tag:
                return el
        raise PermissionError("STALE_BROWSER_ELEMENT_REF")
