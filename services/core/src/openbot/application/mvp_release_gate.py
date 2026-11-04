"""M3 MVP release acceptance gate and risk auditor (OB-080)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openbot.application.supply_chain import ReleaseSupplyChainVerifier


@dataclass(frozen=True, slots=True)
class MvpReleaseDecision:
    darwin_arm64_pilot_ready: bool
    full_three_os_mvp_release_approved: bool
    blocking_reasons: tuple[str, ...]
    m4_signing_is_reverse_prerequisite: Literal[False] = False


class MvpReleaseAcceptanceGate:
    """Evaluate M3 MVP release readiness without relaxing three-OS or live-tenant gates."""

    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root.resolve()

    def evaluate_release_readiness(
        self,
        *,
        security_critical_failures: int,
        darwin_arm64_verified: bool,
        windows_native_verified: bool,
        linux_native_verified: bool,
        real_feishu_tenant_verified: bool,
    ) -> MvpReleaseDecision:
        sc = ReleaseSupplyChainVerifier(self._root).verify_all()
        reasons: list[str] = []
        if security_critical_failures > 0:
            reasons.append("security_critical_failures_present")
        if not darwin_arm64_verified or sc.verified_artifacts_count == 0:
            reasons.append("darwin_arm64_or_supply_chain_unverified")
        if not windows_native_verified:
            reasons.append("windows_native_unverified")
        if not linux_native_verified:
            reasons.append("linux_native_unverified")
        if not real_feishu_tenant_verified:
            reasons.append("real_feishu_tenant_unverified")

        pilot_ok = security_critical_failures == 0 and darwin_arm64_verified
        full_ok = len(reasons) == 0
        return MvpReleaseDecision(
            darwin_arm64_pilot_ready=pilot_ok,
            full_three_os_mvp_release_approved=full_ok,
            blocking_reasons=tuple(reasons),
        )
