import traceback
from pathlib import Path

import pytest
from openbot.policy.secrets.broker import (
    SecretBroker,
    SecretUnavailableError,
    build_minimal_child_spawn_spec,
)


class ControlledKeychainBackend:
    def __init__(self, backend_id: str = "macos.Keychain", state: str = "AVAILABLE") -> None:
        self.backend_id = backend_id
        self.state = state
        self.items: dict[str, bytes] = {}

    def get_secret(self, secret_ref: str) -> bytes:
        if self.state != "AVAILABLE":
            raise SecretUnavailableError(secret_ref, reason_code=self.state)
        if secret_ref not in self.items:
            raise SecretUnavailableError(secret_ref, reason_code="SECRET_NOT_FOUND")
        return self.items[secret_ref]

    def set_secret(self, secret_ref: str, value: bytes) -> None:
        if self.state != "AVAILABLE":
            raise SecretUnavailableError(secret_ref, reason_code=self.state)
        self.items[secret_ref] = value

    def delete_secret(self, secret_ref: str) -> None:
        if self.state != "AVAILABLE":
            raise SecretUnavailableError(secret_ref, reason_code=self.state)
        self.items.pop(secret_ref, None)


def test_unapproved_or_fallback_backends_are_rejected_and_locked_keychain_fails_closed():
    for bad_backend in (
        "plaintext.FileKeyring",
        "cryptography.FernetFileKeyring",
        "unknown.Plugin",
    ):
        with pytest.raises(PermissionError, match="Unapproved credential backend"):
            SecretBroker(ControlledKeychainBackend(backend_id=bad_backend))

    for failure_state in (
        "KEYCHAIN_LOCKED",
        "DBUS_UNAVAILABLE",
        "HEADLESS_NO_SESSION",
        "USER_CANCELLED",
    ):
        kc = ControlledKeychainBackend(state=failure_state)
        broker = SecretBroker(kc)
        with pytest.raises(SecretUnavailableError) as exc_info:
            broker.resolve_for_feishu_gateway("keychain:feishu:tenant1_app")
        assert exc_info.value.reason_code == failure_state


def test_compartmentalized_injection_single_use_worker_handle_and_revocation():
    kc = ControlledKeychainBackend()
    feishu_secret = b"fs_sec_canary_998877"
    openai_secret = b"sk_openai_canary_112233"
    anthropic_secret = b"sk_anth_canary_445566"
    worker_secret = b"wk_tok_canary_776655"
    kc.set_secret("keychain:feishu:app1", feishu_secret)
    kc.set_secret("keychain:provider:openai:main", openai_secret)
    kc.set_secret("keychain:provider:anthropic:main", anthropic_secret)
    kc.set_secret("keychain:worker:git_read", worker_secret)

    broker = SecretBroker(kc)

    # 1. Gateway can ONLY access feishu secret; model gateway can ONLY access selected provider key
    assert broker.resolve_for_feishu_gateway("keychain:feishu:app1") == feishu_secret
    with pytest.raises(PermissionError, match="compartment"):
        broker.resolve_for_feishu_gateway("keychain:provider:openai:main")

    assert (
        broker.resolve_for_model_provider("keychain:provider:openai:main", "openai")
        == openai_secret
    )
    with pytest.raises(PermissionError, match="selected_provider"):
        broker.resolve_for_model_provider("keychain:provider:anthropic:main", "openai")

    # 2. Worker receives a single-use, attempt-bound IPC handle; cannot reuse or cross-consume
    handle = broker.mint_worker_handle(
        "keychain:worker:git_read", attempt_id="att_1", ttl_ms=10_000
    )
    assert feishu_secret.decode() not in repr(handle)
    assert worker_secret.decode() not in repr(handle)
    with pytest.raises(PermissionError, match="attempt_id"):
        broker.consume_worker_handle(handle.handle_id, attempt_id="att_other")

    assert broker.consume_worker_handle(handle.handle_id, attempt_id="att_1") == worker_secret
    with pytest.raises(PermissionError, match="consumed|invalid"):
        broker.consume_worker_handle(handle.handle_id, attempt_id="att_1")

    # 3. Revoking a secret_ref invalidates active handles and refuses subsequent resolution
    handle2 = broker.mint_worker_handle(
        "keychain:worker:git_read", attempt_id="att_2", ttl_ms=10_000
    )
    broker.revoke("keychain:worker:git_read")
    with pytest.raises(PermissionError, match="consumed|invalid"):
        broker.consume_worker_handle(handle2.handle_id, attempt_id="att_2")
    with pytest.raises(SecretUnavailableError):
        broker.mint_worker_handle("keychain:worker:git_read", attempt_id="att_3", ttl_ms=10_000)


def test_child_env_argv_home_mount_and_exception_never_leak_canary(tmp_path):
    kc = ControlledKeychainBackend()
    canary = "sk_canary_super_secret_do_not_leak_42"
    kc.set_secret("keychain:provider:openai:main", canary.encode())
    broker = SecretBroker(kc)
    broker.register_canary(canary)

    # 1. Token in argv or mounted host HOME is rejected
    with pytest.raises(PermissionError, match="argv"):
        build_minimal_child_spawn_spec(
            argv=("curl", "-H", f"Authorization: Bearer {canary}"),
            isolated_workdir=tmp_path,
            host_home=Path("/Users/admin-1234"),
            mounts=(tmp_path,),
            broker=broker,
        )
    with pytest.raises(PermissionError, match="HOME"):
        build_minimal_child_spawn_spec(
            argv=("git", "status"),
            isolated_workdir=tmp_path,
            host_home=Path("/Users/admin-1234"),
            mounts=(Path("/Users/admin-1234/.ssh"),),
            broker=broker,
        )

    # 2. Clean child spawn spec never inherits ambient env and contains zero canary bytes
    spec = build_minimal_child_spawn_spec(
        argv=("git", "status"),
        isolated_workdir=tmp_path,
        host_home=Path("/Users/admin-1234"),
        mounts=(tmp_path,),
        broker=broker,
        handle_id="shd_opaque_123",
    )
    assert canary not in str(spec.env)
    assert canary not in str(spec.argv)
    assert spec.env["HOME"] != "/Users/admin-1234"

    # 3. Exception stack traces never contain the canary value
    try:
        raise SecretUnavailableError("keychain:provider:openai:main", reason_code="KEYCHAIN_LOCKED")
    except SecretUnavailableError:
        tb = traceback.format_exc()
        assert canary not in tb
