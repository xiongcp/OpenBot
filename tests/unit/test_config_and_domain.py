import json

import pytest
from openbot.config import CapabilityUnavailable, ProfileConfig, authorize_connection, load_config
from openbot.domain.clock import ClockSnapshot, grant_valid
from openbot.domain.errors import outcome_error
from openbot.domain.tools import Effect, RetryClass


def config(**updates):
    return {"schema_version": "1.1", "profile_id": "pro_demo1", "mode": "OFFLINE", **updates}


def test_default_offline_and_explicitly_disabled_capabilities(tmp_path):
    raw = config(workspace=str(tmp_path))
    parsed = load_config(json.dumps(raw))
    assert parsed.mode == "OFFLINE"
    for kind in ["feishu", "browser", "mcp", "cloud_model", "local_model"]:
        with pytest.raises(CapabilityUnavailable):
            authorize_connection(parsed, kind)


@pytest.mark.parametrize(
    "updates",
    [
        {"mode": "OFFLINE", "feishu_enabled": True},
        {"mode": "unknown"},
        {"cloud_fallback": True},
        {"sdk_max_retries": 2},
        {"host_execution": True},
        {"runtime_downloads": True},
        {"schema_version": "1.2"},
        {"role": "owner"},
        {"model_secret_ref": ""},
        {"max_active_tasks": "1"},
        {"model_endpoint": "https://user:pass@example.invalid"},
    ],
)
def test_config_rejects_permission_expansion_and_coercion(tmp_path, updates):
    with pytest.raises(ValueError):
        load_config(json.dumps(config(workspace=str(tmp_path), **updates)))


def test_missing_workspace_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_config(json.dumps(config(workspace=str(tmp_path / "missing"))))


def test_loopback_and_user_claimed_evidence_do_not_authorize_local_inference(tmp_path):
    parsed = load_config(
        json.dumps(
            config(
                workspace=str(tmp_path),
                mode="LOCAL_MODEL",
                model_endpoint="http://127.0.0.1:11434",
            )
        )
    )
    with pytest.raises(CapabilityUnavailable):
        authorize_connection(parsed, "cloud_model")
    with pytest.raises(CapabilityUnavailable):
        authorize_connection(parsed, "local_model")
    with pytest.raises(ValueError):
        load_config(json.dumps(config(workspace=str(tmp_path), local_execution_proven=True)))


def test_connected_requires_explicit_endpoint_and_secret_handle(tmp_path):
    parsed = load_config(
        json.dumps(
            config(
                workspace=str(tmp_path),
                mode="CONNECTED",
                model_endpoint="https://api.openai.com/v1",
                model_secret_ref="keyring:openbot/test",
            )
        )
    )
    assert authorize_connection(parsed, "cloud_model") == "https://api.openai.com/v1"
    assert isinstance(parsed, ProfileConfig)


def test_persistent_ttl_requires_current_boot_and_stable_clocks():
    issued = ClockSnapshot(100_000, 10_000, "boot-1")
    assert grant_valid(issued, ClockSnapshot(100_500, 10_500, "boot-1"), 1000)
    for now in [
        ClockSnapshot(99_000, 10_500, "boot-1"),
        ClockSnapshot(102_000, 10_500, "boot-1"),
        ClockSnapshot(100_500, 10_500, "boot-2"),
        ClockSnapshot(101_000, 11_000, "boot-1"),
    ]:
        assert not grant_valid(issued, now, 1000)


def test_timeout_and_cancel_after_dispatch_do_not_claim_rollback():
    for reason in ["timeout", "cancelled", "connection_lost"]:
        err = outcome_error(reason, dispatched=True, trace_id="trc_demo1")
        assert err.code == "OUTCOME_UNKNOWN"
        assert not err.retryable
        assert err.operation_state == "UNKNOWN"
        assert err.task_state == "RECONCILING"
    assert not outcome_error("policy", dispatched=False, trace_id="trc_demo1").retryable


def test_effect_does_not_imply_retry_class():
    assert Effect.EXTERNAL_WRITE.value == "EXTERNAL_WRITE"
    assert RetryClass.RECONCILE_ONLY.value == "RECONCILE_ONLY"
