"""Convert untrusted wire input to immutable values, without granting authority."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from openbot.contracts import CanonicalDocument, ContractError, SchemaRegistry, strict_json
from openbot.domain.events import InboundEvent, TrustedSource
from openbot.domain.providers import ToolCall
from openbot.domain.tools import ToolManifest

type Id = Annotated[str, Field(pattern=r"^[a-z][a-z0-9]*_[A-Za-z0-9][A-Za-z0-9_-]{3,95}$")]


class InboundDto(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: Literal["1.1"]
    event_id: Id
    trace_id: Id
    correlation_id: Id
    payload: dict[str, Any]


class ModelCallDto(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    tool_name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,127}$")
    args: dict[str, Any]


def normalize_inbound(raw: str | bytes, source: TrustedSource, received_at_ms: int) -> InboundEvent:
    try:
        dto = InboundDto.model_validate(strict_json(raw))
    except ValidationError as exc:
        raise ContractError("Invalid inbound event") from exc
    return InboundEvent(
        dto.schema_version,
        dto.event_id,
        dto.trace_id,
        dto.correlation_id,
        received_at_ms,
        source,
        CanonicalDocument.create(dto.payload).canonical,
    )


def accept_model_call(raw: str | bytes, manifest: ToolManifest, call_id: str) -> ToolCall:
    try:
        dto = ModelCallDto.model_validate(strict_json(raw))
    except ValidationError as exc:
        raise ContractError("Invalid model tool proposal") from exc
    if dto.tool_name != manifest.name:
        raise ContractError("Tool not in the selected manifest")
    registry = SchemaRegistry({"args.json": strict_json(manifest.input_schema)})
    args = registry.validate("args.json", CanonicalDocument.create(dto.args).canonical)
    return ToolCall(call_id, dto.tool_name, args.canonical)
