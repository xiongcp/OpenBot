from openbot.adapters.local_api.server import ApiRequest, ApiResponse
from openbot.policy.pairing import PairingService
from openbot_feishu.inbound import FeishuInboundAdapter, FeishuInboundConfig

from tests.contracts.local_api.test_local_api_contracts import local_api_env

__all__ = ["local_api_env"]


class _GatewayApiClient:
    def __init__(self, api, token: str, *, fail_persist: bool = False) -> None:
        self._api = api
        self._token = token
        self.fail_persist = fail_persist

    def post_task(self, idempotency_key: str, body: dict[str, object]) -> ApiResponse:
        if self.fail_persist:
            return ApiResponse(503, b'{"code":"WRITER_UNAVAILABLE"}')
        import json

        return self._api.handle(
            ApiRequest(
                "POST",
                "/v1/tasks",
                headers={
                    "Host": "127.0.0.1:41931",
                    "Authorization": f"Bearer {self._token}",
                    "X-OpenBot-Profile": "pro_test1",
                    "Idempotency-Key": idempotency_key,
                },
                body=json.dumps(body).encode("utf-8"),
            )
        )


def test_feishu_inbound_acks_only_after_persist_and_rejects_group_stranger_and_oversized(
    local_api_env,
) -> None:
    api, context, writer, _, _, _, _, _, gw_token, _ = local_api_env
    pairing = PairingService(writer)
    chal = pairing.create_local_challenge(
        profile_id="pro_test1", expected_tenant_key="ten_1", expected_app_id="app_1"
    )
    cand = pairing.submit_remote_claim(
        challenge_id=chal.challenge_id,
        code=chal.code,
        tenant_key="ten_1",
        app_id="app_1",
        open_id="ou_owner_new",
        display_name="Owner",
    )
    pairing.confirm_candidate_locally(
        context, cand.candidate_id, request_id="inb-pair-1", deadline_monotonic_ms=999999999999
    )

    client = _GatewayApiClient(api, gw_token)
    adapter = FeishuInboundAdapter(
        config=FeishuInboundConfig(
            tenant_key="ten_1",
            app_id="app_1",
            workspace_id="wsp_test1",
            max_attachment_bytes=1024,
        ),
        pairing=pairing,
        api_client=client,
    )

    valid_event = {
        "header": {
            "event_id": "evt_msg_1",
            "event_type": "im.message.receive_v1",
            "tenant_key": "ten_1",
            "app_id": "app_1",
        },
        "event": {
            "sender": {"sender_id": {"open_id": "ou_owner_new"}},
            "message": {
                "message_id": "om_1",
                "chat_type": "p2p",
                "message_type": "text",
                "content": '{"text":"analyze repo"}',
            },
        },
    }

    # 1. Duplicate events return the exact same task_id and ACK=True after persist
    r1 = adapter.handle_ws_event(valid_event)
    r2 = adapter.handle_ws_event(valid_event)
    assert r1.ws_ack is True
    assert r1.task_id == r2.task_id
    assert r1.ack_latency_ms >= 0
    assert r1.llm_waited_in_callback is False

    # 2. Group chat is rejected by default
    group_ev = {
        **valid_event,
        "header": {**valid_event["header"], "event_id": "evt_grp_1"},
        "event": {
            **valid_event["event"],
            "message": {**valid_event["event"]["message"], "chat_type": "group"},
        },
    }
    assert adapter.handle_ws_event(group_ev).rejection_code == "GROUP_CHAT_DISABLED"

    # 3. Stranger or cross-tenant sender is rejected
    stranger_ev = {
        **valid_event,
        "header": {**valid_event["header"], "event_id": "evt_str_1"},
        "event": {
            **valid_event["event"],
            "sender": {"sender_id": {"open_id": "ou_stranger"}},
        },
    }
    assert adapter.handle_ws_event(stranger_ev).rejection_code == "UNPAIRED_SENDER"

    # 4. Oversized attachment is rejected
    big_ev = {
        **valid_event,
        "header": {**valid_event["header"], "event_id": "evt_big_1"},
        "event": {
            **valid_event["event"],
            "message": {
                **valid_event["event"]["message"],
                "attachment_size_bytes": 999999,
            },
        },
    }
    assert adapter.handle_ws_event(big_ev).rejection_code == "ATTACHMENT_TOO_LARGE"

    # 5. If daemon inbox persistence fails, ws_ack MUST be False!
    client.fail_persist = True
    fail_ev = {
        **valid_event,
        "header": {**valid_event["header"], "event_id": "evt_fail_1"},
    }
    r_fail = adapter.handle_ws_event(fail_ev)
    assert r_fail.ws_ack is False
    assert r_fail.rejection_code == "INBOX_PERSIST_FAILED"
