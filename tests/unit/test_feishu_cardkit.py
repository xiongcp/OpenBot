from openbot_feishu.cardkit import CardChannelPolicy, FeishuCardChannelSelector


def test_cardkit_tracks_token_ttl_from_mint_time_and_degrades_gracefully() -> None:
    policy = CardChannelPolicy(
        cardkit_enabled=True,
        callback_token_ttl_ms=1_800_000,
        callback_token_max_uses=2,
    )
    selector = FeishuCardChannelSelector(policy)

    # 1. Task created at t=0, user clicks 45 minutes later (t=2_700_000 ms):
    # Token is minted at click time (t=2_700_000 ms), so at t=2_705_000 ms it is VALID!
    selector.register_callback_token(token="cb_tok_1", task_created_ms=0, token_minted_ms=2_700_000)
    ch1 = selector.select_update_channel(token="cb_tok_1", now_ms=2_705_000, message_updatable=True)
    assert ch1.channel == "CARDKIT_STREAM"
    assert ch1.degraded is False

    # 2. Second use succeeds; third use exceeds max_uses -> degrades to MESSAGE_PATCH_API
    ch2 = selector.select_update_channel(token="cb_tok_1", now_ms=2_710_000, message_updatable=True)
    assert ch2.channel == "CARDKIT_STREAM"
    ch3 = selector.select_update_channel(token="cb_tok_1", now_ms=2_715_000, message_updatable=True)
    assert ch3.channel == "MESSAGE_PATCH_API"
    assert ch3.degraded is True
    assert ch3.degrade_reason == "TOKEN_USES_EXHAUSTED"

    # 3. Missing CardKit permission or non-updatable original message degrades to PLAIN_RESEND
    no_ck = FeishuCardChannelSelector(
        CardChannelPolicy(
            cardkit_enabled=False, callback_token_ttl_ms=60_000, callback_token_max_uses=1
        )
    )
    ch_no_perm = no_ck.select_update_channel(token=None, now_ms=1000, message_updatable=False)
    assert ch_no_perm.channel == "PLAIN_RESEND"
    assert ch_no_perm.degraded is True
