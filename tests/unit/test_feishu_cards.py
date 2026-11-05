from openbot_feishu.cards import FeishuPlainCardBuilder


def test_feishu_plain_cards_require_local_when_sensitive_or_truncated_and_highlight_unknown() -> (
    None
):
    builder = FeishuPlainCardBuilder()

    # 1. Safe WORKSPACE non-truncated preview includes APPROVE and DENY buttons
    safe_card = builder.build_approval_card(
        approval_id="apr_1",
        task_id="tsk_1",
        tool_name="fs.patch",
        data_class="WORKSPACE",
        impact_summary="Update hello.py (1 line)",
        truncated=False,
        expected_version=1,
        binding_hash="a" * 64,
        nonce="n_1",
    )
    assert safe_card.mode == "REMOTE_INTERACTIVE"
    assert safe_card.remote_approve_enabled is True
    assert safe_card.requires_cardkit is False
    assert safe_card.card_json["config"]["wide_screen_mode"] is True
    assert safe_card.card_json["header"]["title"]["tag"] == "plain_text"
    action_block = next(el for el in safe_card.card_json["elements"] if el["tag"] == "action")
    buttons = action_block["actions"]
    assert len(buttons) == 2
    assert buttons[0]["type"] == "primary"
    assert buttons[0]["value"]["decision"] == "APPROVE"
    assert "批准" in buttons[0]["text"]["content"]
    assert buttons[1]["type"] == "danger"
    assert buttons[1]["value"]["decision"] == "DENY"
    assert "拒绝" in buttons[1]["text"]["content"]

    # 1b. Resolved card after clicking APPROVE or DENY removes action buttons
    for dec, expected_tpl in (("APPROVE", "green"), ("DENY", "red")):
        resolved = builder.build_resolved_approval_card(
            approval_id="apr_1",
            task_id="tsk_1",
            tool_name="fs.patch",
            decision=dec,
            operator_open_id="ou_owner_1",
        )
        assert resolved.mode == "RESOLVED"
        assert resolved.remote_approve_enabled is False
        assert resolved.card_json["header"]["template"] == expected_tpl
        assert all(el.get("tag") != "action" for el in resolved.card_json["elements"])

    # 2. SENSITIVE/SECRET or truncated impact forces REQUIRE_LOCAL and disables remote approve
    for dc, trunc in (("SENSITIVE", False), ("SECRET", False), ("WORKSPACE", True)):
        local_only = builder.build_approval_card(
            approval_id="apr_2",
            task_id="tsk_1",
            tool_name="fs.patch",
            data_class=dc,
            impact_summary="diff containing sensitive content",
            truncated=trunc,
            expected_version=1,
            binding_hash="b" * 64,
            nonce="n_2",
        )
        assert local_only.mode == "REQUIRE_LOCAL"
        assert local_only.remote_approve_enabled is False
        assert "diff containing sensitive content" not in str(local_only.card_json)

    # 3. Result receipt card clearly distinguishes UNKNOWN (pending reconciliation) and PARTIAL
    unk_card = builder.build_result_card(
        task_id="tsk_1",
        operation_id="op_1",
        state="UNKNOWN",
        summary="Connection lost after dispatch",
    )
    assert unk_card.reconciliation_required is True
    assert "RECONCILIATION_REQUIRED" in str(unk_card.card_json)
