import asyncio
import json

import pytest
from openbot.boundaries import accept_model_call, normalize_inbound
from openbot.contracts import ContractError
from openbot.domain.events import TrustedSource
from openbot.domain.providers import ModelRequest, ToolCall
from openbot.domain.tools import Effect, RetryClass, ToolManifest


def manifest():
    return ToolManifest(
        "test.marker",
        "1",
        b'{"type":"object","properties":{"marker":'
        b'{"type":"string"}},"required":["marker"],"additionalProperties":false}',
        b'{"type":"object"}',
        Effect.LOCAL_WRITE,
        RetryClass.IDEMPOTENT_WRITE,
        ("workspace",),
        "stop",
        "marker",
        1000,
        1024,
    )


def test_model_can_only_propose_registered_arguments():
    call = accept_model_call(
        '{"tool_name":"test.marker","args":{"marker":"ok"}}', manifest(), "call_demo1"
    )
    assert call.arguments == b'{"marker":"ok"}'
    for payload in [
        {"tool_name": "test.marker", "args": {"marker": "ok"}, "principal_id": "owner"},
        {"tool_name": "test.marker", "args": {"marker": "ok", "endpoint": "https://evil.invalid"}},
        {"tool_name": "message.send", "args": {"marker": "ok"}},
    ]:
        with pytest.raises(ContractError):
            accept_model_call(json.dumps(payload), manifest(), "call_demo1")
    with pytest.raises(ContractError):
        accept_model_call('{"tool_name":"test.marker","args":', manifest(), "call_demo1")


def test_inbound_identity_is_injected_by_authenticated_boundary():
    context = TrustedSource("pro_demo1", "pri_demo1", "fake:tenant:app", 1)
    raw = (
        '{"schema_version":"1.1","event_id":"evt_demo1","trace_id":"trc_demo1",'
        '"correlation_id":"cor_demo1","payload":{"text":"hello"}}'
    )
    event = normalize_inbound(raw, context, 1000)
    assert event.source == context
    assert event.received_at_ms == 1000
    assert event.payload == b'{"text":"hello"}'
    for extra in [{"is_owner": True}, {"source": "trusted"}, {"received_at_ms": 0}]:
        with pytest.raises(ContractError):
            normalize_inbound(json.dumps(json.loads(raw) | extra), context, 1000)


def test_two_fake_providers_and_executor_share_contract(tmp_path):
    from tests.fakes.ports import FakeExecutor, FakeProvider

    async def run():
        request = ModelRequest("req_demo1", "fake", (), 1000, 1)
        for spelling in ["compact", "spaced"]:
            provider = FakeProvider(spelling)
            response = await provider.generate(request)
            call = response.blocks[0]
            assert isinstance(call, ToolCall)
            executor = FakeExecutor(tmp_path / spelling)
            receipt = executor.execute("dsp_demo1", call)
            assert executor.execute("dsp_demo1", call) == receipt
            assert executor.effects == 1
            await provider.close()

    asyncio.run(run())
