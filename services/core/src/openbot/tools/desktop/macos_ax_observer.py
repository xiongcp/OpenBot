"""macOS native AXUIElement window observer with TCC probe and sensitive blacklist (V1-079)."""

from dataclasses import dataclass
from typing import Any, Literal

SENSITIVE_BUNDLE_BLACKLIST = frozenset(
    {
        "com.apple.keychainaccess",
        "com.1password.1password",
        "com.agilebits.onepassword7",
        "com.bitwarden.desktop",
        "com.apple.systempreferences.security",
        "com.apple.SecurityAgent",
    }
)
SENSITIVE_AX_ROLES = frozenset({"AXSecureTextField"})
SENSITIVE_TITLE_KEYWORDS = ("id_rsa", "id_ed25519", ".env", "private key", "keychain", "1password")


@dataclass(frozen=True, slots=True)
class AxNodeSnapshot:
    ax_path: str
    role: str
    title: str
    value_preview: str
    enabled: bool
    provenance_kind: Literal["TAINTED_EXTERNAL"] = "TAINTED_EXTERNAL"


@dataclass(frozen=True, slots=True)
class AxWindowSnapshot:
    app_bundle_id: str
    pid: int
    window_id: int
    window_title: str
    snapshot_revision: int
    nodes: tuple[AxNodeSnapshot, ...]
    provenance_kind: Literal["TAINTED_EXTERNAL"] = "TAINTED_EXTERNAL"
    authoritative_grants: Literal[False] = False


class MacOSAxWindowObserver:
    """Observe allowlisted macOS windows via AXUIElement while hard-blocking sensitive inputs."""

    def __init__(self, *, allowed_bundle_ids: frozenset[str]) -> None:
        overlap = allowed_bundle_ids & SENSITIVE_BUNDLE_BLACKLIST
        if overlap:
            raise PermissionError(f"BLACKLISTED_BUNDLE_CANNOT_BE_ALLOWLISTED: {sorted(overlap)}")
        self._allowed = allowed_bundle_ids
        self._rev_by_window: dict[int, int] = {}

    def check_tcc_accessibility_trusted(self, *, is_trusted: bool) -> dict[str, Any]:
        if not is_trusted:
            raise PermissionError(
                "CAPABILITY_UNAVAILABLE: macOS Accessibility (AXIsProcessTrusted) not granted. "
                "Enable OpenBot in System Settings > Privacy & Security > Accessibility."
            )
        return {"tcc_accessibility_trusted": True}

    def observe_window(
        self,
        *,
        app_bundle_id: str,
        pid: int,
        window_id: int,
        window_title: str,
        raw_nodes: tuple[dict[str, Any], ...],
        is_tcc_trusted: bool = True,
        secure_event_input_enabled: bool = False,
    ) -> AxWindowSnapshot:
        self.check_tcc_accessibility_trusted(is_trusted=is_tcc_trusted)
        if secure_event_input_enabled:
            raise PermissionError(
                "SENSITIVE_WINDOW_OR_SECURE_INPUT_BLOCKED: IsSecureEventInputEnabled is active"
            )
        if app_bundle_id in SENSITIVE_BUNDLE_BLACKLIST:
            raise PermissionError(
                f"SENSITIVE_WINDOW_OR_SECURE_INPUT_BLOCKED: blacklisted bundle {app_bundle_id}"
            )
        if app_bundle_id not in self._allowed:
            raise PermissionError(f"UNAPPROVED_DESKTOP_APP_BUNDLE: {app_bundle_id}")
        lower_title = window_title.lower()
        if any(k in lower_title for k in SENSITIVE_TITLE_KEYWORDS):
            raise PermissionError(
                f"SENSITIVE_WINDOW_OR_SECURE_INPUT_BLOCKED: sensitive window title '{window_title}'"
            )

        nodes: list[AxNodeSnapshot] = []
        for item in raw_nodes[:128]:
            role = str(item.get("role", "AXUnknown"))
            if role in SENSITIVE_AX_ROLES:
                raise PermissionError(
                    "SENSITIVE_WINDOW_OR_SECURE_INPUT_BLOCKED: AXSecureTextField present"
                )
            nodes.append(
                AxNodeSnapshot(
                    ax_path=str(item["ax_path"]),
                    role=role,
                    title=str(item.get("title", ""))[:256],
                    value_preview=str(item.get("value", ""))[:256],
                    enabled=bool(item.get("enabled", True)),
                )
            )
        rev = self._rev_by_window.get(window_id, 0) + 1
        self._rev_by_window[window_id] = rev
        return AxWindowSnapshot(
            app_bundle_id=app_bundle_id,
            pid=pid,
            window_id=window_id,
            window_title=window_title,
            snapshot_revision=rev,
            nodes=tuple(nodes),
        )
