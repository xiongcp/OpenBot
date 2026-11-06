from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Text:
    text: str


@dataclass(frozen=True, slots=True)
class ImageRef:
    artifact_id: str


@dataclass(frozen=True, slots=True)
class ToolCall:
    call_id: str
    tool_name: str
    arguments: bytes


@dataclass(frozen=True, slots=True)
class ToolResult:
    call_id: str
    result: bytes


type Block = Text | ImageRef | ToolCall | ToolResult


@dataclass(frozen=True, slots=True)
class ModelRequest:
    request_id: str
    model: str
    blocks: tuple[Block, ...]
    deadline_monotonic_ms: int
    reserved_cost_units: int
    system: str = ""


@dataclass(frozen=True, slots=True)
class ModelResponse:
    blocks: tuple[Block, ...]
    input_tokens: int | None
    output_tokens: int | None
    usage_estimated: bool


class ModelTransport(Protocol):
    def capabilities(self) -> frozenset[str]: ...

    async def generate(self, request: ModelRequest) -> ModelResponse: ...

    async def cancel(self, request_id: str) -> None: ...

    async def close(self) -> None: ...


class RequestBudget(Protocol):
    def reserve(self, request_id: str, units: int) -> None: ...

    def settle(self, request_id: str, input_tokens: int, output_tokens: int) -> None: ...

    def unknown(self, request_id: str) -> None: ...
