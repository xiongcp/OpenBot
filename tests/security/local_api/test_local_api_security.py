import json

from openbot.adapters.local_api.server import ApiRequest

from tests.contracts.local_api.test_local_api_contracts import _headers, local_api_env

__all__ = ["local_api_env"]


def test_non_loopback_proxy_spoof_cross_origin_wrong_profile_and_scope_escalation_are_rejected(
    local_api_env,
):
    api, _, _, _, _, _, _, owner_token, gw_token, ro_token = local_api_env

    # 1. Non-loopback client IP or X-Forwarded-For proxy spoofing is rejected (403)
    r_remote = api.handle(
        ApiRequest(
            "GET",
            "/v1/health",
            client_ip="192.168.1.50",
            headers=_headers(owner_token, **{"X-Forwarded-For": "127.0.0.1"}),
        )
    )
    assert r_remote.status_code == 403

    r_proxy_hdr = api.handle(
        ApiRequest(
            "GET",
            "/v1/health",
            client_ip="127.0.0.1",
            headers=_headers(owner_token, **{"X-Forwarded-For": "203.0.113.9"}),
        )
    )
    assert r_proxy_hdr.status_code == 403

    # 2. Untrusted Origin or non-local Host header (DNS rebinding) is rejected (403)
    r_origin = api.handle(
        ApiRequest(
            "POST",
            "/v1/tasks",
            headers=_headers(owner_token, Origin="https://evil.example.com"),
            body='{"workspace_id":"wsp_test1","goal":"x","network_mode":"OFFLINE"}',
        )
    )
    assert r_origin.status_code == 403

    r_host = api.handle(
        ApiRequest(
            "GET",
            "/v1/health",
            headers=_headers(owner_token, Host="attacker-rebind.com"),
        )
    )
    assert r_host.status_code == 403

    # 3. Wrong profile header or missing/invalid token is rejected
    r_prof = api.handle(
        ApiRequest(
            "GET",
            "/v1/health",
            headers=_headers(owner_token, **{"X-OpenBot-Profile": "pro_other"}),
        )
    )
    assert r_prof.status_code == 403

    r_anon = api.handle(ApiRequest("GET", "/v1/health", headers={"Host": "127.0.0.1"}))
    assert r_anon.status_code == 401

    # 4. Gateway token CANNOT fetch local approval challenges; readonly token CANNOT mutate tasks
    r_gw_chal = api.handle(
        ApiRequest(
            "POST",
            "/v1/approvals/apr_any/challenge",
            headers=_headers(gw_token),
        )
    )
    assert r_gw_chal.status_code == 403

    r_ro_mut = api.handle(
        ApiRequest(
            "POST",
            "/v1/tasks",
            headers=_headers(ro_token),
            body='{"workspace_id":"wsp_test1","goal":"x","network_mode":"OFFLINE"}',
        )
    )
    assert r_ro_mut.status_code == 403

    # 5. Reconcile endpoint rejects client-supplied target_state or revive_consumed_grant
    r_force = api.handle(
        ApiRequest(
            "POST",
            "/v1/operations/op_any/reconcile",
            headers=_headers(owner_token),
            body=json.dumps(
                {
                    "expected_version": 1,
                    "outcome": "CONFIRMED_SUCCEEDED",
                    "target_state": "SUCCEEDED",
                    "revive_consumed_grant": True,
                }
            ),
        )
    )
    assert r_force.status_code == 400
