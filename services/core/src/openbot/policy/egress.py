"""Unified data egress policy across models, notifications, browser, MCP, and local runners."""

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

type EgressVerdict = Literal["ALLOW", "ASK", "DENY", "REQUIRE_LOCAL"]
type EgressSurface = Literal[
    "MODEL_GATEWAY",
    "LOCAL_MODEL_RUNNER",
    "FEISHU_NOTIFICATION",
    "BROWSER",
    "MCP",
    "FILE_UPLOAD",
    "MESSAGE_TOOL",
]

_MODE_RANK: dict[str, int] = {"OFFLINE": 0, "LOCAL_MODEL": 1, "CONNECTED": 2}
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_PROXY_ENV_KEYS = frozenset(
    {
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    }
)


@dataclass(frozen=True, slots=True)
class LocalModelRunnerAttestation:
    """Proof required before trusting a loopback model runner as non-cloud local inference."""

    model_id: str
    model_source_verified: bool
    cloud_routing_disabled: bool
    web_search_disabled: bool
    egress_isolated_verified: bool

    def is_verified_local(self) -> bool:
        low = self.model_id.lower()
        has_cloud_tag = (":cloud" in low) or low.startswith(("cloud/", "remote/"))
        return (
            bool(self.model_id.strip())
            and not has_cloud_tag
            and self.model_source_verified
            and self.cloud_routing_disabled
            and self.web_search_disabled
            and self.egress_isolated_verified
        )


@dataclass(frozen=True, slots=True)
class EgressRequest:
    surface: str
    task_network_mode: str
    data_class: str
    destination_url: str
    from_summary: bool = False
    from_artifact: bool = False
    redacted: bool = False
    implicit_features: tuple[str, ...] = ()
    runner_attestation: LocalModelRunnerAttestation | None = None


@dataclass(frozen=True, slots=True)
class EgressDecision:
    decision: EgressVerdict
    reason_code: str
    effective_network_mode: str
    target_host: str


@dataclass(frozen=True, slots=True)
class ControlledHttpConfig:
    trust_env: Literal[False]
    follow_redirects: Literal[False]
    max_retries: Literal[0]
    proxy_url: str | None
    sanitized_env: dict[str, str]
    probe_coverage: str
    unproven_by_python_probe: str


class EgressGuard:
    """Shared data-class and destination egress evaluator across all outbound surfaces."""

    def __init__(
        self,
        *,
        profile_network_mode: str,
        profile_allowed_domains: frozenset[str],
        workspace_allowed_domains: frozenset[str],
    ) -> None:
        if profile_network_mode not in _MODE_RANK:
            raise ValueError(f"Invalid profile_network_mode: {profile_network_mode}")
        self._profile_mode = profile_network_mode
        self._allowed_domains = frozenset(
            d.lower() for d in (profile_allowed_domains & workspace_allowed_domains)
        )

    def evaluate(self, request: EgressRequest) -> EgressDecision:
        if request.task_network_mode not in _MODE_RANK:
            return EgressDecision("DENY", "INVALID_NETWORK_MODE", self._profile_mode, "")
        # Effective mode is the intersection (strictest) of profile and task mode
        eff_mode = (
            self._profile_mode
            if _MODE_RANK[self._profile_mode] <= _MODE_RANK[request.task_network_mode]
            else request.task_network_mode
        )

        parsed = urlsplit(request.destination_url)
        host = (parsed.hostname or "").lower()
        if not host or parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            return EgressDecision("DENY", "INVALID_DESTINATION_URL", eff_mode, host)

        # 1. Provider-hosted tools, implicit asset downloads, and online secret verifiers refused
        if request.implicit_features:
            return EgressDecision("DENY", "IMPLICIT_OR_HOSTED_EGRESS_FORBIDDEN", eff_mode, host)

        # 2. SECRET data is never permitted to leave the local machine, even if redacted=True
        if request.data_class == "SECRET":
            return EgressDecision("DENY", "SECRET_EGRESS_FORBIDDEN", eff_mode, host)
        if request.data_class not in {"PUBLIC", "WORKSPACE", "SENSITIVE"}:
            return EgressDecision("DENY", "UNKNOWN_DATA_CLASS", eff_mode, host)

        is_loopback = host in _LOOPBACK_HOSTS

        # 3. Local model runner verification: localhost alone never proves local inference
        if request.surface == "LOCAL_MODEL_RUNNER" or is_loopback:
            if (
                request.runner_attestation is None
                or not request.runner_attestation.is_verified_local()
            ):
                return EgressDecision(
                    "DENY", "LOCAL_MODEL_CLOUD_ROUTING_OR_UNVERIFIED", eff_mode, host
                )
            return EgressDecision("ALLOW", "VERIFIED_LOCAL_LOOPBACK", eff_mode, host)

        # 4. Non-loopback remote egress is completely blocked in OFFLINE across ALL surfaces
        if eff_mode == "OFFLINE":
            return EgressDecision("DENY", "OFFLINE_REMOTE_EGRESS_DENIED", eff_mode, host)

        # 5. LOCAL_MODEL blocks remote model egress
        if eff_mode == "LOCAL_MODEL" and request.surface in {"MODEL_GATEWAY", "LOCAL_MODEL_RUNNER"}:
            return EgressDecision("DENY", "LOCAL_MODEL_REMOTE_LLM_DENIED", eff_mode, host)

        # 6. Domain allowlist check (intersection of profile and workspace allowlists)
        if parsed.scheme != "https" or host not in self._allowed_domains:
            return EgressDecision("DENY", "DESTINATION_NOT_IN_ALLOWLIST", eff_mode, host)

        # 7. Data classification and surface rules on allowed domains
        # Redaction, summary, or artifact wrapping never downgrades SENSITIVE restrictions!
        if request.data_class == "SENSITIVE":
            if request.surface == "FEISHU_NOTIFICATION":
                return EgressDecision(
                    "REQUIRE_LOCAL", "SENSITIVE_PREVIEW_REQUIRES_LOCAL", eff_mode, host
                )
            return EgressDecision("ASK", "SENSITIVE_REMOTE_REQUIRES_APPROVAL", eff_mode, host)

        if request.surface in {"FILE_UPLOAD", "MESSAGE_TOOL"}:
            return EgressDecision("ASK", "EXTERNAL_WRITE_REQUIRES_APPROVAL", eff_mode, host)

        return EgressDecision("ALLOW", "ALLOWED_EGRESS", eff_mode, host)


def build_controlled_http_config(
    *,
    effective_network_mode: str,
    allowed_domains: frozenset[str],
    approved_proxy_url: str | None = None,
    ambient_env: dict[str, str] | None = None,
) -> ControlledHttpConfig:
    """Strip ambient proxy env vars and enforce trust_env=False, max_retries=0."""
    if effective_network_mode not in _MODE_RANK:
        raise ValueError(f"Invalid effective_network_mode: {effective_network_mode}")
    if approved_proxy_url is not None:
        if effective_network_mode == "OFFLINE":
            raise PermissionError("Proxy configuration is forbidden in OFFLINE mode")
        parsed = urlsplit(approved_proxy_url)
        p_host = (parsed.hostname or "").lower()
        if (
            parsed.scheme not in {"http", "https"}
            or not p_host
            or p_host not in {d.lower() for d in allowed_domains}
        ):
            raise PermissionError(f"Unapproved proxy host refused: {approved_proxy_url}")

    sanitized = {k: v for k, v in (ambient_env or {}).items() if k not in _PROXY_ENV_KEYS}
    return ControlledHttpConfig(
        trust_env=False,
        follow_redirects=False,
        max_retries=0,
        proxy_url=approved_proxy_url,
        sanitized_env=sanitized,
        probe_coverage=(
            "Python sys.addaudithook socket/open/process events and httpx transport settings"
        ),
        unproven_by_python_probe=(
            "Native C/Rust extensions, unmanaged child processes, and browser service workers "
            "require OS/container network namespace isolation"
        ),
    )
