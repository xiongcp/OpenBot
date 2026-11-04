"""Keychain backend allowlist, compartmentalized secret broker, and single-use worker handles."""

import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

APPROVED_KEYRING_BACKENDS = frozenset(
    {
        "macos.Keychain",
        "windows.WinVaultKeyring",
        "linux.SecretService",
    }
)


class SecretUnavailableError(RuntimeError):
    """Explicit credential error that never includes raw secret bytes in its message."""

    def __init__(self, secret_ref: str, *, reason_code: str) -> None:
        super().__init__(f"Credential ref '{secret_ref}' unavailable: {reason_code}")
        self.secret_ref = secret_ref
        self.reason_code = reason_code


class CredentialBackendPort(Protocol):
    backend_id: str

    def get_secret(self, secret_ref: str) -> bytes: ...
    def set_secret(self, secret_ref: str, value: bytes) -> None: ...
    def delete_secret(self, secret_ref: str) -> None: ...


@dataclass(frozen=True, slots=True)
class SingleUseSecretHandle:
    """Opaque short-lived IPC handle for an isolated worker attempt. Never holds raw bytes."""

    handle_id: str
    secret_ref: str
    attempt_id: str
    expires_monotonic_ms: int


@dataclass(frozen=True, slots=True)
class ChildSpawnSecretSpec:
    argv: tuple[str, ...]
    env: dict[str, str]
    mounts: tuple[Path, ...]


class SecretBroker:
    """Enforce approved OS credential backend, compartment isolation, and single-use IPC handles."""

    def __init__(self, backend: CredentialBackendPort) -> None:
        if backend.backend_id not in APPROVED_KEYRING_BACKENDS:
            raise PermissionError(
                f"Unapproved credential backend '{backend.backend_id}'; "
                "plaintext or ad-hoc Fernet file fallbacks are forbidden"
            )
        self._backend = backend
        self._handles: dict[str, SingleUseSecretHandle] = {}
        self._revoked_refs: set[str] = set()
        self._canaries: set[str] = set()

    def register_canary(self, secret_value: str) -> None:
        if secret_value:
            self._canaries.add(secret_value)

    def known_canaries(self) -> frozenset[str]:
        return frozenset(self._canaries)

    def _require_active_ref(self, secret_ref: str) -> None:
        if not secret_ref.startswith("keychain:"):
            raise PermissionError("Only opaque keychain:<compartment>:<name> refs are permitted")
        if secret_ref in self._revoked_refs:
            raise SecretUnavailableError(secret_ref, reason_code="SECRET_REVOKED")

    def resolve_for_feishu_gateway(self, secret_ref: str) -> bytes:
        self._require_active_ref(secret_ref)
        if not secret_ref.startswith("keychain:feishu:"):
            raise PermissionError(
                "Feishu gateway compartment can only access keychain:feishu:* secrets"
            )
        val = self._backend.get_secret(secret_ref)
        self.register_canary(val.decode("utf-8", errors="ignore"))
        return val

    def resolve_for_model_provider(self, secret_ref: str, selected_provider: str) -> bytes:
        self._require_active_ref(secret_ref)
        prefix = f"keychain:provider:{selected_provider.lower()}:"
        if not secret_ref.startswith(prefix):
            raise PermissionError(
                f"Model gateway for selected_provider='{selected_provider}' "
                f"cannot access {secret_ref}"
            )
        val = self._backend.get_secret(secret_ref)
        self.register_canary(val.decode("utf-8", errors="ignore"))
        return val

    def mint_worker_handle(
        self, secret_ref: str, *, attempt_id: str, ttl_ms: int = 30_000
    ) -> SingleUseSecretHandle:
        self._require_active_ref(secret_ref)
        if not secret_ref.startswith("keychain:worker:"):
            raise PermissionError("Worker handles can only be minted for keychain:worker:* refs")
        if not attempt_id.strip() or ttl_ms <= 0:
            raise ValueError("Invalid attempt_id or ttl_ms")
        # Verify underlying secret is accessible in OS keychain without copying into handle
        val = self._backend.get_secret(secret_ref)
        self.register_canary(val.decode("utf-8", errors="ignore"))
        now_mono = int(time.monotonic() * 1000)
        handle = SingleUseSecretHandle(
            handle_id="shd_" + secrets.token_hex(16),
            secret_ref=secret_ref,
            attempt_id=attempt_id,
            expires_monotonic_ms=now_mono + ttl_ms,
        )
        self._handles[handle.handle_id] = handle
        return handle

    def consume_worker_handle(self, handle_id: str, *, attempt_id: str) -> bytes:
        handle = self._handles.get(handle_id)
        if handle is None:
            raise PermissionError("Worker secret handle is already consumed or invalid")
        if handle.attempt_id != attempt_id:
            raise PermissionError("Worker secret handle attempt_id mismatch")
        now_mono = int(time.monotonic() * 1000)
        del self._handles[handle_id]
        if now_mono >= handle.expires_monotonic_ms:
            raise PermissionError("Worker secret handle expired")
        self._require_active_ref(handle.secret_ref)
        return self._backend.get_secret(handle.secret_ref)

    def rotate(self, secret_ref: str, new_value: bytes) -> None:
        self._require_active_ref(secret_ref)
        self._backend.set_secret(secret_ref, new_value)
        self.register_canary(new_value.decode("utf-8", errors="ignore"))
        for hid, h in list(self._handles.items()):
            if h.secret_ref == secret_ref:
                del self._handles[hid]

    def revoke(self, secret_ref: str) -> None:
        self._revoked_refs.add(secret_ref)
        for hid, h in list(self._handles.items()):
            if h.secret_ref == secret_ref:
                del self._handles[hid]
        self._backend.delete_secret(secret_ref)


def build_minimal_child_spawn_spec(
    *,
    argv: tuple[str, ...],
    isolated_workdir: Path,
    host_home: Path,
    mounts: tuple[Path, ...],
    broker: SecretBroker,
    handle_id: str | None = None,
) -> ChildSpawnSecretSpec:
    """Build clean child env without inheriting os.environ, mounting HOME, or argv tokens."""
    if not argv:
        raise ValueError("argv must be non-empty")
    canaries = broker.known_canaries()
    for arg in argv:
        for c in canaries:
            if c and c in arg:
                raise PermissionError("Secret token detected in child argv; forbidden")

    resolved_home = host_home.resolve()
    for m in mounts:
        rm = m.resolve()
        if rm == resolved_home or rm.is_relative_to(resolved_home):
            raise PermissionError(f"Mounting host HOME directory is forbidden: {m}")

    clean_env: dict[str, str] = {
        "HOME": str((isolated_workdir / ".isolated_home").resolve()),
        "TMPDIR": str((isolated_workdir / ".isolated_tmp").resolve()),
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C.UTF-8",
    }
    if handle_id is not None:
        clean_env["OPENBOT_SECRET_HANDLE_ID"] = handle_id
    return ChildSpawnSecretSpec(argv=argv, env=clean_env, mounts=mounts)
