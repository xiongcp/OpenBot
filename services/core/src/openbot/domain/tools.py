"""Tool metadata describes capabilities; only the Broker may authorize dispatch."""

from dataclasses import dataclass
from enum import StrEnum


class Effect(StrEnum):
    READ = "READ"
    LOCAL_WRITE = "LOCAL_WRITE"
    EXTERNAL_WRITE = "EXTERNAL_WRITE"
    CODE_EXECUTION = "CODE_EXECUTION"


class RetryClass(StrEnum):
    SAFE_READ = "SAFE_READ"
    IDEMPOTENT_WRITE = "IDEMPOTENT_WRITE"
    PROVIDER_IDEMPOTENT = "PROVIDER_IDEMPOTENT"
    RECONCILE_ONLY = "RECONCILE_ONLY"
    NON_RETRYABLE = "NON_RETRYABLE"


@dataclass(frozen=True, slots=True)
class ToolManifest:
    name: str
    version: str
    input_schema: bytes
    output_schema: bytes
    effect: Effect
    retry_class: RetryClass
    resources: tuple[str, ...]
    cancellation: str
    reconciliation: str
    timeout_ms: int
    max_output_bytes: int
