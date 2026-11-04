"""Streaming offline secret redaction across arbitrary chunk boundaries without allowlist bypass."""

import base64
import json
import re
import urllib.parse
from dataclasses import dataclass
from typing import Literal

_OFFLINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bfs_sec_[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bcli_[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(api_key|secret|token|password)\s*[=:]\s*['\"]?[A-Za-z0-9._~+/=-]{8,}['\"]?"),
)

_VALID_SINKS = frozenset(
    {
        "stdout",
        "stderr",
        "sdk_debug",
        "exception",
        "http_header",
        "ui_event",
        "artifact",
        "diagnostic",
        "model_input",
    }
)


def _encode_variants(secret: str) -> tuple[str, ...]:
    variants: list[str] = [secret]
    b64 = base64.b64encode(secret.encode("utf-8")).decode("ascii")
    url_enc = urllib.parse.quote(secret, safe="")
    json_esc = json.dumps(secret)[1:-1]
    for v in (b64, url_enc, json_esc):
        if v and v not in variants:
            variants.append(v)
    return tuple(sorted(variants, key=len, reverse=True))


@dataclass(frozen=True, slots=True)
class RedactionContract:
    holdback_window_chars: int
    network_verification_enabled: Literal[False] = False
    dynamic_plugins_enabled: Literal[False] = False
    external_allowlist_honored: Literal[False] = False
    guarantees_100_percent_detection: Literal[False] = False
    negative_scan_downgrades_classification: Literal[False] = False
    residual_risk_note: str = (
        "Regex and exact-canary matching cannot identify all unstructured private data; "
        "data classification and EgressGuard remain the primary enforcement boundary."
    )


@dataclass(frozen=True, slots=True)
class RedactionResult:
    sink: str
    sanitized_text: str
    redaction_count: int
    data_class: str
    allow_remote_egress: bool


class StreamingSecretRedactor:
    """Stateful streaming redactor handling arbitrary chunk splits and long secrets."""

    def __init__(
        self,
        *,
        registered_secrets: tuple[str, ...] = (),
        min_pattern_holdback: int = 256,
    ) -> None:
        all_variants: list[str] = []
        for s in registered_secrets:
            if s:
                for v in _encode_variants(s):
                    if v not in all_variants:
                        all_variants.append(v)
        self._variants = tuple(sorted(all_variants, key=len, reverse=True))
        max_secret_len = max((len(v) for v in self._variants), default=0)
        # Dynamic holdback window scales with the longest registered secret + pattern margin
        self._holdback = max(min_pattern_holdback, max_secret_len + 64)
        self._buffer = ""
        self.total_redactions = 0

    @property
    def holdback_window_chars(self) -> int:
        return self._holdback

    def _scrub(self, text: str) -> str:
        out = text
        for v in self._variants:
            if v in out:
                cnt = out.count(v)
                self.total_redactions += cnt
                out = out.replace(v, "[REDACTED]")
        for pat in _OFFLINE_PATTERNS:
            out, n = pat.subn("[REDACTED]", out)
            self.total_redactions += n
        return out

    def feed(self, chunk: str | bytes) -> str:
        piece = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else chunk
        self._buffer += piece
        self._buffer = self._scrub(self._buffer)
        if len(self._buffer) <= self._holdback:
            return ""
        emit_len = len(self._buffer) - self._holdback
        emitted = self._buffer[:emit_len]
        self._buffer = self._buffer[emit_len:]
        return emitted

    def flush(self) -> str:
        final = self._scrub(self._buffer)
        self._buffer = ""
        return final


class RedactionPipeline:
    """Unified offline redaction across all sinks while preserving data classification."""

    def __init__(self, *, registered_secrets: tuple[str, ...] = ()) -> None:
        self._secrets = tuple(s for s in registered_secrets if s)

    def contract(self) -> RedactionContract:
        probe = StreamingSecretRedactor(registered_secrets=self._secrets)
        return RedactionContract(holdback_window_chars=probe.holdback_window_chars)

    def sanitize_sink(
        self,
        *,
        sink: str,
        text: str,
        data_class: str,
        uncertain_sensitivity: bool = False,
    ) -> RedactionResult:
        if sink not in _VALID_SINKS:
            raise ValueError(f"Unsupported redaction sink: {sink}")
        if data_class not in {"PUBLIC", "WORKSPACE", "SENSITIVE", "SECRET"}:
            raise ValueError(f"Unsupported data_class: {data_class}")
        redactor = StreamingSecretRedactor(registered_secrets=self._secrets)
        sanitized = redactor.feed(text) + redactor.flush()
        # Negative scan never downgrades SECRET or SENSITIVE; uncertain sensitivity blocks egress
        allow_remote = not uncertain_sensitivity and data_class in {"PUBLIC", "WORKSPACE"}
        return RedactionResult(
            sink=sink,
            sanitized_text=sanitized,
            redaction_count=redactor.total_redactions,
            data_class=data_class,
            allow_remote_egress=allow_remote,
        )

    def verify_secret_online_forbidden(self, candidate: str) -> None:
        del candidate
        raise PermissionError("Network verification of secrets is permanently disabled in OpenBot")
