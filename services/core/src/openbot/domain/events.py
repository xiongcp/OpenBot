from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TrustedSource:
    profile_id: str
    principal_id: str
    source_scope: str
    identity_epoch: int


@dataclass(frozen=True, slots=True)
class InboundEvent:
    schema_version: str
    event_id: str
    trace_id: str
    correlation_id: str
    received_at_ms: int
    source: TrustedSource
    payload: bytes


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    event_id: str
    seq: int
    event_type: str
    trace_id: str
    occurred_at_ms: int
    payload: bytes
