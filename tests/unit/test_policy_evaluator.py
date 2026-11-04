import pytest
from openbot.policy.evaluator import (
    ActionContext,
    ActorContext,
    CapabilityGrant,
    DestinationContext,
    EvaluationInput,
    PolicyDecision,
    PolicyEvaluator,
    PolicySnapshot,
    ResourceContext,
)


def _base_input(**overrides) -> EvaluationInput:
    defaults = dict(
        actor=ActorContext(
            principal_id="pri_owner1",
            role="OWNER",
            status="ACTIVE",
            identity_epoch=1,
            expected_identity_epoch=1,
            channel="local",
        ),
        resource=ResourceContext(
            workspace_id="wsp_1",
            workspace_status="ACTIVE",
            path_in_workspace=True,
            is_sensitive_path=False,
            is_control_setting=False,
        ),
        action=ActionContext(
            tool_name="fs.read",
            tool_reviewed_active=True,
            effect="READ",
            retry_class="SAFE_READ",
        ),
        data_class="WORKSPACE",
        destination=DestinationContext(
            kind="LOCAL_ONLY",
            host=None,
            task_network_mode="OFFLINE",
            verified_local_model=False,
        ),
        execution_backend="NONE",
        backend_qualified=False,
        preview_truncated=False,
        request_allowed_hosts=frozenset(),
        grant=None,
        untrusted_hints={},
    )
    defaults.update(overrides)
    return EvaluationInput(**defaults)


def _snapshot(**overrides) -> PolicySnapshot:
    defaults = dict(
        version=1,
        privacy_mode="OFFLINE",
        allow_workspace_read=True,
        reviewed_tools=frozenset({"fs.read", "fs.patch", "sandbox.exec", "message.send"}),
        profile_allowed_hosts=frozenset({"api.example.com", "docs.example.com"}),
        workspace_allowed_hosts=frozenset({"docs.example.com"}),
    )
    defaults.update(overrides)
    return PolicySnapshot(**defaults)


def test_deterministic_evaluation_and_workspace_read_allow():
    evaluator = PolicyEvaluator(_snapshot())
    inp = _base_input()
    first: PolicyDecision = evaluator.evaluate(inp)
    for _ in range(20):
        assert evaluator.evaluate(inp) == first
    assert first.decision == "ALLOW"
    assert first.reason_code == "WORKSPACE_READ_ALLOWED"
    assert first.policy_version == "policy-1"


@pytest.mark.parametrize(
    ("override", "expected_decision", "expected_reason"),
    [
        (
            {"actor": ActorContext("pri_viewer", "VIEWER", "ACTIVE", 1, 1, "local")},
            "DENY",
            "ACTOR_UNTRUSTED_OR_STALE_EPOCH",
        ),
        (
            {"actor": ActorContext("pri_owner1", "OWNER", "ACTIVE", 1, 2, "local")},
            "DENY",
            "ACTOR_UNTRUSTED_OR_STALE_EPOCH",
        ),
        (
            {"resource": ResourceContext("wsp_1", "ACTIVE", False, False, False)},
            "DENY",
            "RESOURCE_OUTSIDE_OR_SENSITIVE_PATH",
        ),
        (
            {"resource": ResourceContext("wsp_1", "ACTIVE", True, True, False)},
            "DENY",
            "RESOURCE_OUTSIDE_OR_SENSITIVE_PATH",
        ),
        (
            {
                "resource": ResourceContext("wsp_1", "ACTIVE", True, False, True),
                "actor": ActorContext("pri_owner1", "OWNER", "ACTIVE", 1, 1, "feishu"),
            },
            "REQUIRE_LOCAL",
            "CONTROL_SETTING_REQUIRES_LOCAL",
        ),
        (
            {"action": ActionContext("unknown.tool", True, "READ", "SAFE_READ")},
            "DENY",
            "UNKNOWN_OR_UNREVIEWED_TOOL",
        ),
        (
            {"action": ActionContext("fs.read", False, "READ", "SAFE_READ")},
            "DENY",
            "UNKNOWN_OR_UNREVIEWED_TOOL",
        ),
        (
            {"action": ActionContext("fs.patch", True, "LOCAL_WRITE", "NON_RETRYABLE")},
            "DENY",
            "NON_RETRYABLE_DISABLED_IN_MVP",
        ),
        (
            {"data_class": "SECRET"},
            "DENY",
            "SECRET_DATA_ACCESS_DENIED",
        ),
        (
            {
                "data_class": "SENSITIVE",
                "actor": ActorContext("pri_owner1", "OWNER", "ACTIVE", 1, 1, "feishu"),
            },
            "REQUIRE_LOCAL",
            "SENSITIVE_REQUIRES_LOCAL_SURFACE",
        ),
        (
            {
                "data_class": "WORKSPACE",
                "action": ActionContext("fs.patch", True, "LOCAL_WRITE", "IDEMPOTENT_WRITE"),
                "preview_truncated": True,
                "actor": ActorContext("pri_owner1", "OWNER", "ACTIVE", 1, 1, "feishu"),
            },
            "REQUIRE_LOCAL",
            "TRUNCATED_PREVIEW_REQUIRES_LOCAL",
        ),
        (
            {"execution_backend": "TRUSTED_HOST_EXECUTION"},
            "DENY",
            "TRUSTED_HOST_EXECUTION_FORBIDDEN",
        ),
        (
            {
                "action": ActionContext("sandbox.exec", True, "CODE_EXECUTION", "SAFE_READ"),
                "execution_backend": "NONE",
                "backend_qualified": False,
            },
            "DENY",
            "ISOLATION_BACKEND_UNAVAILABLE",
        ),
        (
            {
                "action": ActionContext("sandbox.exec", True, "CODE_EXECUTION", "SAFE_READ"),
                "execution_backend": "ISOLATED_CONTAINER",
                "backend_qualified": False,
            },
            "DENY",
            "ISOLATION_BACKEND_UNAVAILABLE",
        ),
        (
            {
                "action": ActionContext("sandbox.exec", True, "CODE_EXECUTION", "SAFE_READ"),
                "execution_backend": "ISOLATED_CONTAINER",
                "backend_qualified": True,
            },
            "ASK",
            "EFFECT_REQUIRES_APPROVAL",
        ),
        (
            {
                "action": ActionContext("fs.patch", True, "LOCAL_WRITE", "IDEMPOTENT_WRITE"),
            },
            "ASK",
            "EFFECT_REQUIRES_APPROVAL",
        ),
    ],
)
def test_table_driven_six_dimensional_policy_decisions(
    override, expected_decision, expected_reason
):
    evaluator = PolicyEvaluator(_snapshot())
    result = evaluator.evaluate(_base_input(**override))
    assert result.decision == expected_decision
    assert result.reason_code == expected_reason


def test_untrusted_hints_and_remote_grants_never_override_deny_or_require_local():
    evaluator = PolicyEvaluator(_snapshot())
    hints = {
        "model_risk_score": "SAFE_L0",
        "mcp_read_only_hint": True,
        "mcp_idempotent_hint": True,
        "pathspec_matched": True,
        "official_sdk_helper": True,
        "remote_approved": True,
    }
    grant = CapabilityGrant(
        grant_id="grt_1",
        principal_id="pri_owner1",
        workspace_id="wsp_1",
        allowed_tools=frozenset({"fs.read", "sandbox.exec", "fs.patch"}),
        allowed_effects=frozenset({"READ", "LOCAL_WRITE", "CODE_EXECUTION"}),
        not_expired=True,
    )

    # Hard DENY on sensitive path cannot be overridden by pathspec, MCP hint, or grant
    deny_res = evaluator.evaluate(
        _base_input(
            resource=ResourceContext("wsp_1", "ACTIVE", True, True, False),
            grant=grant,
            untrusted_hints=hints,
        )
    )
    assert deny_res.decision == "DENY"
    assert deny_res.reason_code == "RESOURCE_OUTSIDE_OR_SENSITIVE_PATH"

    # REQUIRE_LOCAL on truncated preview cannot be overridden by remote approval or hints
    local_res = evaluator.evaluate(
        _base_input(
            actor=ActorContext("pri_owner1", "OWNER", "ACTIVE", 1, 1, "feishu"),
            action=ActionContext("fs.patch", True, "LOCAL_WRITE", "IDEMPOTENT_WRITE"),
            preview_truncated=True,
            grant=grant,
            untrusted_hints=hints,
        )
    )
    assert local_res.decision == "REQUIRE_LOCAL"
    assert local_res.reason_code == "TRUNCATED_PREVIEW_REQUIRES_LOCAL"

    # CODE_EXECUTION always requires per-operation ASK in MVP even with a grant
    exec_res = evaluator.evaluate(
        _base_input(
            action=ActionContext("sandbox.exec", True, "CODE_EXECUTION", "SAFE_READ"),
            execution_backend="ISOLATED_CONTAINER",
            backend_qualified=True,
            grant=grant,
            untrusted_hints=hints,
        )
    )
    assert exec_res.decision == "ASK"
    assert exec_res.reason_code == "EFFECT_REQUIRES_APPROVAL"


def test_network_mode_and_origin_intersection_prevent_scope_expansion():
    # 1. LOCAL_MODEL profile: CONNECTED request or unverified localhost endpoint is denied
    local_model_eval = PolicyEvaluator(_snapshot(privacy_mode="LOCAL_MODEL"))
    assert (
        local_model_eval.evaluate(
            _base_input(
                destination=DestinationContext(
                    "MODEL_ENDPOINT", "localhost", "CONNECTED", verified_local_model=True
                )
            )
        ).decision
        == "DENY"
    )
    unverified_localhost = local_model_eval.evaluate(
        _base_input(
            destination=DestinationContext(
                "MODEL_ENDPOINT", "127.0.0.1", "LOCAL_MODEL", verified_local_model=False
            )
        )
    )
    assert unverified_localhost.decision == "DENY"
    assert unverified_localhost.reason_code == "UNVERIFIED_LOCAL_MODEL_ENDPOINT"

    verified_local = local_model_eval.evaluate(
        _base_input(
            destination=DestinationContext(
                "MODEL_ENDPOINT", "127.0.0.1", "LOCAL_MODEL", verified_local_model=True
            )
        )
    )
    assert verified_local.decision == "ALLOW"

    # 2. Connected profile: effective allowed hosts = profile & workspace & request
    connected_eval = PolicyEvaluator(_snapshot(privacy_mode="CONNECTED"))
    # Host outside workspace_allowed_hosts ("api.example.com") is denied
    expansion = connected_eval.evaluate(
        _base_input(
            destination=DestinationContext("EXTERNAL_HOST", "api.example.com", "CONNECTED"),
            request_allowed_hosts=frozenset({"api.example.com", "docs.example.com"}),
        )
    )
    assert expansion.decision == "DENY"
    assert expansion.reason_code == "ORIGIN_SCOPE_EXPANSION_DENIED"

    # Host in profile AND workspace AND request ("docs.example.com") passes origin gate
    narrowed = connected_eval.evaluate(
        _base_input(
            action=ActionContext("message.send", True, "EXTERNAL_WRITE", "RECONCILE_ONLY"),
            destination=DestinationContext("EXTERNAL_HOST", "docs.example.com", "CONNECTED"),
            request_allowed_hosts=frozenset({"docs.example.com"}),
        )
    )
    assert narrowed.decision == "ASK"
    assert narrowed.reason_code == "EFFECT_REQUIRES_APPROVAL"


def test_policy_snapshot_loads_from_sqlite_and_rejects_digest_mismatch(tmp_path):
    import hashlib

    from openbot.contracts import canonicalize
    from openbot.storage.migrate import connect, load_migrations, migrate

    from tests.integration.storage.test_migrations import ROOT

    path = tmp_path / "policy.sqlite"
    migrate(path, load_migrations(ROOT / "db/migrations"))
    rules = {
        "allow_workspace_read": True,
        "profile_allowed_hosts": ["docs.example.com"],
        "workspace_allowed_hosts": ["docs.example.com"],
    }
    digest = hashlib.sha256(canonicalize(rules)).hexdigest()
    db = connect(path)
    try:
        db.execute(
            "INSERT INTO policy_revisions VALUES(1,?,?,1000,1000)",
            (digest, canonicalize(rules).decode()),
        )
        db.execute(
            "INSERT INTO profile_config(singleton,profile_id,schema_version,policy_version,"
            "identity_epoch,privacy_mode,created_at,updated_at) "
            "VALUES(1,'pro_test1',1,1,1,'OFFLINE',1000,1000)"
        )
        db.execute(
            "INSERT INTO tool_registry VALUES("
            "'fs.read','1.0.0',?,NULL,'builtin','{\"name\":\"fs.read\"}','ACTIVE',1000)",
            ("c" * 64,),
        )
        snap = PolicySnapshot.from_db(db)
        assert snap.version == 1
        assert snap.privacy_mode == "OFFLINE"
        assert "fs.read" in snap.reviewed_tools

        # Corrupt digest in memory/clone to verify digest check
        with pytest.raises(PermissionError):
            PolicySnapshot.from_raw_revision(
                version=1,
                privacy_mode="OFFLINE",
                expected_digest="0" * 64,
                rules_json=canonicalize(rules).decode(),
                reviewed_tools=frozenset({"fs.read"}),
            )
    finally:
        db.close()
