"""Deterministic six-dimensional policy evaluator. Hints and pathspec never grant authority."""

import hashlib
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from openbot.contracts import canonicalize, strict_json

type PolicyDecisionKind = Literal["ALLOW", "ASK", "DENY", "REQUIRE_LOCAL"]

_NET_RANK: dict[str, int] = {"OFFLINE": 0, "LOCAL_MODEL": 1, "CONNECTED": 2}
_VALID_EFFECTS = frozenset({"READ", "LOCAL_WRITE", "EXTERNAL_WRITE", "CODE_EXECUTION"})
_VALID_RETRY_CLASSES = frozenset(
    {
        "SAFE_READ",
        "IDEMPOTENT_WRITE",
        "PROVIDER_IDEMPOTENT",
        "RECONCILE_ONLY",
        "NON_RETRYABLE",
    }
)
_VALID_DATA_CLASSES = frozenset({"PUBLIC", "WORKSPACE", "SENSITIVE", "SECRET"})
_VALID_DESTINATIONS = frozenset({"LOCAL_ONLY", "MODEL_ENDPOINT", "FEISHU", "EXTERNAL_HOST"})


@dataclass(frozen=True, slots=True)
class ActorContext:
    principal_id: str
    role: str
    status: str
    identity_epoch: int
    expected_identity_epoch: int
    channel: str


@dataclass(frozen=True, slots=True)
class ResourceContext:
    workspace_id: str
    workspace_status: str
    path_in_workspace: bool
    is_sensitive_path: bool
    is_control_setting: bool = False


@dataclass(frozen=True, slots=True)
class ActionContext:
    tool_name: str
    tool_reviewed_active: bool
    effect: str
    retry_class: str


@dataclass(frozen=True, slots=True)
class DestinationContext:
    kind: str
    host: str | None
    task_network_mode: str
    verified_local_model: bool = False


@dataclass(frozen=True, slots=True)
class CapabilityGrant:
    grant_id: str
    principal_id: str
    workspace_id: str
    allowed_tools: frozenset[str]
    allowed_effects: frozenset[str]
    not_expired: bool


@dataclass(frozen=True, slots=True)
class EvaluationInput:
    actor: ActorContext
    resource: ResourceContext
    action: ActionContext
    data_class: str
    destination: DestinationContext
    execution_backend: str
    backend_qualified: bool = False
    preview_truncated: bool = False
    request_allowed_hosts: frozenset[str] = field(default_factory=frozenset)
    grant: CapabilityGrant | None = None
    untrusted_hints: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    decision: PolicyDecisionKind
    reason_code: str
    policy_version: str
    effective_network_mode: str
    effective_allowed_hosts: tuple[str, ...]
    ignored_hint_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PolicySnapshot:
    version: int
    privacy_mode: str
    allow_workspace_read: bool
    reviewed_tools: frozenset[str]
    profile_allowed_hosts: frozenset[str] = field(default_factory=frozenset)
    workspace_allowed_hosts: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_raw_revision(
        cls,
        *,
        version: int,
        privacy_mode: str,
        expected_digest: str,
        rules_json: str | bytes,
        reviewed_tools: frozenset[str],
    ) -> "PolicySnapshot":
        if type(version) is not int or version < 1 or privacy_mode not in _NET_RANK:
            raise PermissionError("Invalid policy version or privacy_mode")
        rules = strict_json(rules_json)
        if not isinstance(rules, dict):
            raise PermissionError("Policy rules must be a JSON object")
        computed = hashlib.sha256(canonicalize(rules)).hexdigest()
        if computed != expected_digest:
            raise PermissionError("Policy revision digest mismatch")
        allow_read = bool(rules.get("allow_workspace_read", True))
        prof_hosts = frozenset(str(h) for h in rules.get("profile_allowed_hosts", []))
        ws_hosts = frozenset(str(h) for h in rules.get("workspace_allowed_hosts", []))
        return cls(
            version=version,
            privacy_mode=privacy_mode,
            allow_workspace_read=allow_read,
            reviewed_tools=frozenset(reviewed_tools),
            profile_allowed_hosts=prof_hosts,
            workspace_allowed_hosts=ws_hosts,
        )

    @classmethod
    def from_db(cls, db: sqlite3.Connection) -> "PolicySnapshot":
        cfg = db.execute(
            "SELECT policy_version,privacy_mode FROM profile_config WHERE singleton=1"
        ).fetchone()
        if not cfg:
            raise PermissionError("Profile config unavailable")
        version, privacy_mode = int(cfg[0]), str(cfg[1])
        rev = db.execute(
            "SELECT digest,rules_json FROM policy_revisions WHERE version=?", (version,)
        ).fetchone()
        if not rev:
            raise PermissionError("Active policy revision missing")
        tools = frozenset(
            str(r[0]) for r in db.execute("SELECT tool_id FROM tool_registry WHERE status='ACTIVE'")
        )
        return cls.from_raw_revision(
            version=version,
            privacy_mode=privacy_mode,
            expected_digest=str(rev[0]),
            rules_json=str(rev[1]),
            reviewed_tools=tools,
        )


class PolicyEvaluator:
    def __init__(self, snapshot: PolicySnapshot):
        self._snapshot = snapshot

    def _result(
        self,
        decision: PolicyDecisionKind,
        reason_code: str,
        effective_mode: str,
        allowed_hosts: frozenset[str],
        inp: EvaluationInput,
    ) -> PolicyDecision:
        return PolicyDecision(
            decision=decision,
            reason_code=reason_code,
            policy_version=f"policy-{self._snapshot.version}",
            effective_network_mode=effective_mode,
            effective_allowed_hosts=tuple(sorted(allowed_hosts)),
            ignored_hint_keys=tuple(sorted(str(k) for k in inp.untrusted_hints)),
        )

    def evaluate(self, inp: EvaluationInput) -> PolicyDecision:
        snap = self._snapshot
        base_hosts = snap.profile_allowed_hosts & snap.workspace_allowed_hosts
        eff_hosts = (
            (base_hosts & inp.request_allowed_hosts) if inp.request_allowed_hosts else base_hosts
        )
        mode_fallback = (
            inp.destination.task_network_mode
            if inp.destination.task_network_mode in _NET_RANK
            else "OFFLINE"
        )

        # 1. Actor authority & epoch
        actor = inp.actor
        if (
            actor.status != "ACTIVE"
            or actor.role != "OWNER"
            or type(actor.identity_epoch) is not int
            or actor.identity_epoch < 1
            or actor.identity_epoch != actor.expected_identity_epoch
        ):
            return self._result(
                "DENY", "ACTOR_UNTRUSTED_OR_STALE_EPOCH", mode_fallback, eff_hosts, inp
            )

        # 2. Execution backend hard gates
        if inp.execution_backend == "TRUSTED_HOST_EXECUTION":
            return self._result(
                "DENY", "TRUSTED_HOST_EXECUTION_FORBIDDEN", mode_fallback, eff_hosts, inp
            )
        if inp.execution_backend not in {"NONE", "ISOLATED_CONTAINER"}:
            return self._result("DENY", "UNKNOWN_EXECUTION_BACKEND", mode_fallback, eff_hosts, inp)

        # 3. Resource boundary gates (pathspec hints never authorize access)
        res = inp.resource
        if res.workspace_status != "ACTIVE" or not res.path_in_workspace or res.is_sensitive_path:
            return self._result(
                "DENY", "RESOURCE_OUTSIDE_OR_SENSITIVE_PATH", mode_fallback, eff_hosts, inp
            )

        # 4. Action / Tool review & retry class gates
        act = inp.action
        if (
            not act.tool_reviewed_active
            or act.tool_name not in snap.reviewed_tools
            or act.effect not in _VALID_EFFECTS
            or act.retry_class not in _VALID_RETRY_CLASSES
        ):
            return self._result("DENY", "UNKNOWN_OR_UNREVIEWED_TOOL", mode_fallback, eff_hosts, inp)
        if act.retry_class == "NON_RETRYABLE":
            return self._result(
                "DENY", "NON_RETRYABLE_DISABLED_IN_MVP", mode_fallback, eff_hosts, inp
            )
        if act.effect == "CODE_EXECUTION" and (
            inp.execution_backend != "ISOLATED_CONTAINER" or not inp.backend_qualified
        ):
            return self._result(
                "DENY", "ISOLATION_BACKEND_UNAVAILABLE", mode_fallback, eff_hosts, inp
            )

        # 5. Data classification hard gates
        if inp.data_class not in _VALID_DATA_CLASSES:
            return self._result("DENY", "UNKNOWN_DATA_CLASS", mode_fallback, eff_hosts, inp)
        if inp.data_class == "SECRET":
            return self._result("DENY", "SECRET_DATA_ACCESS_DENIED", mode_fallback, eff_hosts, inp)
        if inp.data_class == "SENSITIVE" and inp.destination.kind != "LOCAL_ONLY":
            return self._result("DENY", "SENSITIVE_EGRESS_DENIED", mode_fallback, eff_hosts, inp)

        # 6. Destination & network/origin intersection gates
        dest = inp.destination
        if dest.task_network_mode not in _NET_RANK or snap.privacy_mode not in _NET_RANK:
            return self._result("DENY", "UNKNOWN_NETWORK_MODE", "OFFLINE", eff_hosts, inp)
        if _NET_RANK[dest.task_network_mode] > _NET_RANK[snap.privacy_mode]:
            return self._result(
                "DENY", "NETWORK_SCOPE_EXPANSION_DENIED", snap.privacy_mode, eff_hosts, inp
            )
        effective_mode = dest.task_network_mode

        if inp.request_allowed_hosts and not (inp.request_allowed_hosts <= base_hosts):
            return self._result(
                "DENY", "ORIGIN_SCOPE_EXPANSION_DENIED", effective_mode, eff_hosts, inp
            )
        if dest.kind not in _VALID_DESTINATIONS:
            return self._result("DENY", "UNKNOWN_DESTINATION_KIND", effective_mode, eff_hosts, inp)
        if effective_mode == "OFFLINE" and dest.kind != "LOCAL_ONLY":
            return self._result("DENY", "OFFLINE_EGRESS_DENIED", effective_mode, eff_hosts, inp)
        if effective_mode == "LOCAL_MODEL":
            if dest.kind == "MODEL_ENDPOINT" and not dest.verified_local_model:
                return self._result(
                    "DENY", "UNVERIFIED_LOCAL_MODEL_ENDPOINT", effective_mode, eff_hosts, inp
                )
            if dest.kind == "EXTERNAL_HOST" and (not dest.host or dest.host not in eff_hosts):
                return self._result(
                    "DENY", "DESTINATION_NOT_IN_ALLOWED_ORIGINS", effective_mode, eff_hosts, inp
                )
        if effective_mode == "CONNECTED" and dest.kind == "EXTERNAL_HOST":
            if not dest.host or dest.host not in eff_hosts:
                return self._result(
                    "DENY", "DESTINATION_NOT_IN_ALLOWED_ORIGINS", effective_mode, eff_hosts, inp
                )

        # 7. REQUIRE_LOCAL surface gates (cannot be bypassed by remote approval or grants)
        if res.is_control_setting:
            return self._result(
                "REQUIRE_LOCAL", "CONTROL_SETTING_REQUIRES_LOCAL", effective_mode, eff_hosts, inp
            )
        if inp.data_class == "SENSITIVE" and actor.channel != "local":
            return self._result(
                "REQUIRE_LOCAL", "SENSITIVE_REQUIRES_LOCAL_SURFACE", effective_mode, eff_hosts, inp
            )
        if inp.preview_truncated and actor.channel != "local":
            return self._result(
                "REQUIRE_LOCAL",
                "TRUNCATED_PREVIEW_REQUIRES_LOCAL",
                effective_mode,
                eff_hosts,
                inp,
            )

        # 8. ALLOW vs ASK
        if (
            act.effect == "READ"
            and inp.data_class in {"PUBLIC", "WORKSPACE"}
            and dest.kind in {"LOCAL_ONLY", "MODEL_ENDPOINT"}
        ):
            if snap.allow_workspace_read:
                return self._result(
                    "ALLOW", "WORKSPACE_READ_ALLOWED", effective_mode, eff_hosts, inp
                )
            return self._result("ASK", "READ_REQUIRES_APPROVAL", effective_mode, eff_hosts, inp)

        grant = inp.grant
        if (
            grant is not None
            and grant.not_expired
            and grant.principal_id == actor.principal_id
            and grant.workspace_id == res.workspace_id
            and act.tool_name in grant.allowed_tools
            and act.effect in grant.allowed_effects
            and act.effect == "LOCAL_WRITE"
            and inp.data_class in {"PUBLIC", "WORKSPACE"}
            and dest.kind == "LOCAL_ONLY"
        ):
            return self._result("ALLOW", "CAPABILITY_GRANT_ALLOWED", effective_mode, eff_hosts, inp)

        return self._result("ASK", "EFFECT_REQUIRES_APPROVAL", effective_mode, eff_hosts, inp)
