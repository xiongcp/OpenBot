import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_feishu_live_tenant_sanitized_fixture_captures_ws_and_cardkit_without_secrets() -> None:
    fixture_path = ROOT / "tests/fixtures/feishu/sanitized_events.json"
    raw_text = fixture_path.read_text(encoding="utf-8")
    doc = json.loads(raw_text)
    live = doc["live_tenant_probe_sanitized"]

    assert live["token_exchange"]["code"] == 0
    assert live["token_exchange"]["expire_seconds"] == 7200
    assert live["ws_endpoint_discovery"]["ws_host"] == "msg-frontier.feishu.cn"
    assert (
        live["ws_endpoint_discovery"]["ws_upgrade_status_line"]
        == "HTTP/1.1 101 Switching Protocols"
    )
    assert live["ws_endpoint_discovery"]["client_config"]["PingInterval"] == 90
    assert live["cardkit_v1"]["create_card_code"] == 0
    assert live["cardkit_v1"]["stale_sequence_code"] == 300317
    assert live["error_contracts"]["missing_scope_tenant_readonly"]["code"] == 99991672
    # Ensure only SHA-256 prefix is stored and no raw secret field exists in the fixture
    assert len(live["app_id_sha256_prefix"]) == 16
    assert "app_secret" not in raw_text.lower()
