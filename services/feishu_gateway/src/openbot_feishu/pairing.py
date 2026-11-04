"""Feishu gateway pairing forwarder. Never grants owner on first message."""

from typing import Any

from openbot.policy.pairing import PairingService, PendingPairingCandidate


class FeishuPairingForwarder:
    """Forward remote pairing claims to daemon PairingService without auto-pairing."""

    def __init__(self, pairing_service: PairingService) -> None:
        self._pairing = pairing_service

    def on_unpaired_first_message(
        self, *, tenant_key: str, app_id: str, open_id: str
    ) -> dict[str, Any]:
        del tenant_key, app_id, open_id
        return {"auto_paired": False, "status": "REJECTED_UNPAIRED_SENDER"}

    def forward_remote_claim(
        self,
        *,
        challenge_id: str,
        code: str,
        tenant_key: str,
        app_id: str,
        open_id: str,
        display_name: str,
    ) -> PendingPairingCandidate:
        return self._pairing.submit_remote_claim(
            challenge_id=challenge_id,
            code=code,
            tenant_key=tenant_key,
            app_id=app_id,
            open_id=open_id,
            display_name=display_name,
        )
