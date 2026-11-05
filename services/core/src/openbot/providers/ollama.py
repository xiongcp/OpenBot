"""Local Ollama provider adapter verifying runner egress and zero cloud fallback (OB-026)."""

import http.client
import json
import re
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class LocalModelEndpointAttestation:
    endpoint_url: str
    model_id: str
    local_weights_digest: str
    runner_offline_egress_verified: bool
    cloud_relay_enabled: bool
    web_search_plugin_enabled: bool
    supports_structured_tools: bool
    allow_runtime_model_pull: bool = False

    def validate_local_authority(self) -> None:
        parsed = urlparse(self.endpoint_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"}:
            raise PermissionError("CAPABILITY_UNAVAILABLE: non-loopback local model endpoint")
        # Localhost alone NEVER proves local inference: verify weights digest, offline egress,
        # and absence of cloud relay / web search / runtime model pulling!
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.local_weights_digest):
            raise PermissionError("CAPABILITY_UNAVAILABLE: missing pinned local_weights_digest")
        if not self.runner_offline_egress_verified:
            raise PermissionError("CAPABILITY_UNAVAILABLE: runner offline egress not verified")
        if self.cloud_relay_enabled or "cloud" in self.model_id.lower():
            raise PermissionError("CAPABILITY_UNAVAILABLE: localhost cloud relay is forbidden")
        if self.web_search_plugin_enabled:
            raise PermissionError("CAPABILITY_UNAVAILABLE: runner web search plugin is forbidden")
        if self.allow_runtime_model_pull:
            raise PermissionError("CAPABILITY_UNAVAILABLE: runtime model pulling is forbidden")


@dataclass(frozen=True, slots=True)
class OllamaRawResponse:
    content: str
    tool_calls: tuple[dict[str, Any], ...]
    prompt_tokens: int
    eval_tokens: int


class OllamaTransportPort(Protocol):
    def post_chat(self, payload: dict[str, object]) -> OllamaRawResponse: ...


class OllamaHttpTransport:
    """Real loopback HTTP transport to a local Ollama runner on 127.0.0.1."""

    def __init__(self, endpoint_url: str, *, timeout_seconds: float = 10.0) -> None:
        parsed = urlparse(endpoint_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"}:
            raise PermissionError("OllamaHttpTransport only permits loopback http endpoints")
        port = parsed.port or 11434
        self._host = f"{parsed.hostname}:{port}"
        self._path = parsed.path or "/api/chat"
        self._timeout = timeout_seconds

    def probe_models(self) -> list[dict[str, Any]]:
        conn = http.client.HTTPConnection(self._host, timeout=self._timeout)
        try:
            conn.request("GET", "/api/tags")
            resp = conn.getresponse()
            if resp.status != 200:
                raise ConnectionRefusedError(f"Ollama /api/tags returned {resp.status}")
            doc = json.loads(resp.read().decode("utf-8"))
            return list(doc.get("models", []))
        except OSError as exc:
            raise ConnectionRefusedError(str(exc)) from exc
        finally:
            conn.close()

    def post_chat(self, payload: dict[str, object]) -> OllamaRawResponse:
        conn = http.client.HTTPConnection(self._host, timeout=self._timeout)
        try:
            raw_req = json.dumps(payload).encode("utf-8")
            conn.request(
                "POST",
                self._path,
                body=raw_req,
                headers={"Content-Type": "application/json"},
            )
            resp = conn.getresponse()
            if resp.status != 200:
                raise RuntimeError(f"Ollama /api/chat returned {resp.status}")
            doc = json.loads(resp.read().decode("utf-8"))
            msg = dict(doc.get("message", {}))
            return OllamaRawResponse(
                content=str(msg.get("content", "")),
                tool_calls=tuple(msg.get("tool_calls", ())),
                prompt_tokens=int(doc.get("prompt_eval_count", 0)),
                eval_tokens=int(doc.get("eval_count", 0)),
            )
        except OSError as exc:
            raise ConnectionRefusedError(str(exc)) from exc
        finally:
            conn.close()


@dataclass(frozen=True, slots=True)
class LocalGenerationResult:
    status: Literal["OK", "LOCAL_PROVIDER_FAILED"]
    model_id: str
    content: str
    candidate_tool_calls: tuple[dict[str, Any], ...]
    cloud_fallback_attempted: Literal[False] = False
    authority_granted: Literal[False] = False


class OllamaLocalProviderAdapter:
    """Execute local model requests without runtime pulls, cloud relays, or cloud fallback."""

    def __init__(
        self,
        *,
        attestation: LocalModelEndpointAttestation,
        transport: OllamaTransportPort,
    ) -> None:
        attestation.validate_local_authority()
        self._att = attestation
        self._transport = transport

    def generate(
        self,
        *,
        prompt: str,
        require_tools: bool,
        privacy_mode: Literal["LOCAL_MODEL", "OFFLINE", "CONNECTED"],
    ) -> LocalGenerationResult:
        del privacy_mode
        if require_tools and not self._att.supports_structured_tools:
            raise PermissionError("CAPABILITY_UNAVAILABLE_NO_TOOL_SUPPORT")
        try:
            resp = self._transport.post_chat(
                {
                    "model": self._att.model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                }
            )
        except Exception as exc:
            return LocalGenerationResult(
                status="LOCAL_PROVIDER_FAILED",
                model_id=self._att.model_id,
                content=str(exc),
                candidate_tool_calls=(),
                cloud_fallback_attempted=False,
                authority_granted=False,
            )
        return LocalGenerationResult(
            status="OK",
            model_id=self._att.model_id,
            content=resp.content,
            candidate_tool_calls=resp.tool_calls,
            cloud_fallback_attempted=False,
            authority_granted=False,
        )
