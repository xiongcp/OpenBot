import pytest
from openbot.policy.pairing import PairingService
from openbot.storage.inbox import authorize
from openbot.storage.migrate import connect
from openbot_feishu.pairing import FeishuPairingForwarder

from tests.integration.storage.test_recovery import recovery_env

__all__ = ["recovery_env"]


def test_pairing_requires_local_confirmation_rejects_first_sender_and_revocation_increments_epoch(
    recovery_env,
) -> None:
    path, context, writer, _, _, _, _, _, _, _ = recovery_env
    pairing = PairingService(writer)
    forwarder = FeishuPairingForwarder(pairing)

    # 1. Stranger sending first message NEVER auto-becomes owner
    assert forwarder.on_unpaired_first_message(
        tenant_key="ten_1", app_id="app_1", open_id="ou_stranger_1"
    ) == {"auto_paired": False, "status": "REJECTED_UNPAIRED_SENDER"}

    # 2. Local owner initiates short-TTL challenge bound to profile/tenant/app
    chal = pairing.create_local_challenge(
        profile_id="pro_test1",
        expected_tenant_key="ten_1",
        expected_app_id="app_1",
        ttl_ms=60_000,
        max_attempts=2,
    )

    # Wrong tenant or wrong code fails and decrements attempts
    with pytest.raises(PermissionError, match="TENANT_OR_APP_MISMATCH"):
        forwarder.forward_remote_claim(
            challenge_id=chal.challenge_id,
            code=chal.code,
            tenant_key="ten_evil",
            app_id="app_1",
            open_id="ou_evil",
            display_name="Evil",
        )

    # Valid remote claim ONLY creates PENDING_LOCAL_CONFIRMATION, not active owner yet!
    candidate = forwarder.forward_remote_claim(
        challenge_id=chal.challenge_id,
        code=chal.code,
        tenant_key="ten_1",
        app_id="app_1",
        open_id="ou_owner_new",
        display_name="Alice Owner",
    )
    assert candidate.status == "PENDING_LOCAL_CONFIRMATION"
    assert pairing.is_active_owner("ou_owner_new") is False

    # Replay of same challenge is rejected
    with pytest.raises(PermissionError, match="CHALLENGE_ALREADY_CLAIMED_OR_EXPIRED"):
        forwarder.forward_remote_claim(
            challenge_id=chal.challenge_id,
            code=chal.code,
            tenant_key="ten_1",
            app_id="app_1",
            open_id="ou_replay",
            display_name="Replay",
        )

    # 3. Local confirmation activates owner in SQLite
    confirmed = pairing.confirm_candidate_locally(
        context,
        candidate.candidate_id,
        request_id="pair-conf-1",
        deadline_monotonic_ms=999999999999,
    )
    assert confirmed["status"] == "ACTIVE_OWNER"
    assert pairing.is_active_owner("ou_owner_new") is True

    # 4. Revoking owner increments profile_config.identity_epoch and invalidates old context
    revoked = pairing.revoke_owner(
        context,
        principal_id=confirmed["principal_id"],
        request_id="pair-rev-1",
        deadline_monotonic_ms=999999999999,
    )
    assert revoked["new_identity_epoch"] == context.identity_epoch + 1
    assert pairing.is_active_owner("ou_owner_new") is False

    db = connect(path)
    try:
        with pytest.raises(PermissionError):
            authorize(db, context)
    finally:
        db.close()
