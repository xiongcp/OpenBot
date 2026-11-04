"""CardKit capability selection, token lifetime from mint time, and channel fallback (OB-053)."""

from dataclasses import dataclass
from typing import Literal

type CardUpdateChannel = Literal["CARDKIT_STREAM", "MESSAGE_PATCH_API", "PLAIN_RESEND"]


@dataclass(frozen=True, slots=True)
class CardChannelPolicy:
    cardkit_enabled: bool
    callback_token_ttl_ms: int
    callback_token_max_uses: int


@dataclass
class _CallbackTokenState:
    token: str
    task_created_ms: int
    token_minted_ms: int
    uses: int = 0


@dataclass(frozen=True, slots=True)
class ChannelSelection:
    channel: CardUpdateChannel
    degraded: bool
    degrade_reason: str | None


class FeishuCardChannelSelector:
    """Track callback token TTL from mint time (not task creation) and degrade cleanly."""

    def __init__(self, policy: CardChannelPolicy) -> None:
        self._policy = policy
        self._tokens: dict[str, _CallbackTokenState] = {}

    def register_callback_token(
        self, *, token: str, task_created_ms: int, token_minted_ms: int
    ) -> None:
        self._tokens[token] = _CallbackTokenState(
            token=token,
            task_created_ms=task_created_ms,
            token_minted_ms=token_minted_ms,
        )

    def select_update_channel(
        self, *, token: str | None, now_ms: int, message_updatable: bool
    ) -> ChannelSelection:
        if not message_updatable:
            return ChannelSelection(
                channel="PLAIN_RESEND",
                degraded=True,
                degrade_reason="MESSAGE_NOT_UPDATABLE",
            )
        if not self._policy.cardkit_enabled or token is None:
            return ChannelSelection(
                channel="MESSAGE_PATCH_API",
                degraded=not self._policy.cardkit_enabled,
                degrade_reason="CARDKIT_DISABLED_OR_NO_TOKEN",
            )
        st = self._tokens.get(token)
        if st is None:
            return ChannelSelection(
                channel="MESSAGE_PATCH_API",
                degraded=True,
                degrade_reason="UNKNOWN_CALLBACK_TOKEN",
            )
        # Lifetime is measured strictly from token_minted_ms, NOT task_created_ms!
        if now_ms - st.token_minted_ms >= self._policy.callback_token_ttl_ms:
            return ChannelSelection(
                channel="MESSAGE_PATCH_API",
                degraded=True,
                degrade_reason="TOKEN_TTL_EXPIRED",
            )
        if st.uses >= self._policy.callback_token_max_uses:
            return ChannelSelection(
                channel="MESSAGE_PATCH_API",
                degraded=True,
                degrade_reason="TOKEN_USES_EXHAUSTED",
            )
        st.uses += 1
        return ChannelSelection(
            channel="CARDKIT_STREAM",
            degraded=False,
            degrade_reason=None,
        )
