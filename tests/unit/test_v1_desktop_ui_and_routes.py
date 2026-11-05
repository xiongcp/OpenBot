import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from openbot.adapters.local_api.client_routes import ClientRoutes
from openbot.adapters.local_api.server import ApiRequest
from openbot.application.agent_runtime import AgentRuntime

from tests.contracts.local_api.test_local_api_contracts import _headers, local_api_env
from tests.integration.test_agent_runtime import SyntheticModel
from tests.integration.test_client_state import apply_config, service

__all__ = ["local_api_env"]
ROOT = Path(__file__).resolve().parents[2]


def test_v1_063_client_routes_structured_diff_preview_and_drift(
    local_api_env: Any, tmp_path: Path
) -> None:
    api, ctx, writer, tasks, ops, dispatch = local_api_env[:6]
    state = service(local_api_env)
    apply_config(state, mode="CONNECTED")
    runtime = AgentRuntime(
        state=state,
        tasks=tasks,
        operations=ops,
        dispatcher=dispatch,
        artifacts=api._artifacts,
        registry=api._registry,
        workspace=tmp_path,
        runtime_epoch="ep_1",
        tool=None,
        model_factory=lambda cfg, b: SyntheticModel(b, tool=False),
    )
    routes = ClientRoutes(state, runtime)
    api._client = routes
    try:
        created = api.handle(
            ApiRequest(
                "POST",
                "/v1/tasks",
                headers=_headers(local_api_env[7]),
                body=json.dumps(
                    {
                        "workspace_id": "wsp_test1",
                        "goal": "diff preview",
                        "network_mode": "CONNECTED",
                    }
                ),
            )
        ).json()
        task_id = created["task_id"]
        writer.submit(tasks.command(ctx, task_id, 0, "RUNNING", "r-diff-1", 999999999999)).result(5)
        proposed = json.loads(
            ops.propose(
                ctx,
                task_id,
                "workspace.apply_patch",
                json.dumps(
                    {
                        "path": "config.py",
                        "old_snippet": "PORT = 8000\n",
                        "new_snippet": "PORT = 9000\n",
                    }
                ),
                {
                    "workspace_generation": 1,
                    "files": [{"relative_path": "config.py", "sha256": "sha256:" + "1" * 64}],
                },
                "WORKSPACE",
                {"kind": "LOCAL", "resource_ref": ctx.workspace_id},
                "prop-diff-1",
                999999999999,
            )
        )
        prev = routes.preview(proposed["approval_id"])
        assert prev["target_path"] == "config.py"
        assert prev["old_sha256"] == "1" * 64
        assert prev["new_sha256"] is not None and len(prev["new_sha256"]) == 64
        assert any("-PORT = 8000" in ln for ln in prev["diff_lines"])
        assert any("+PORT = 9000" in ln for ln in prev["diff_lines"])
        assert prev["precondition_drift"] is False
    finally:
        runtime.close()


def test_v1_061_to_067_desktop_ui_modules_pass_node_test_suite() -> None:
    fallback_node = (
        "/Users/admin-1234/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
    )
    node_bin = shutil.which("node") or fallback_node
    if not Path(node_bin).is_file():
        return
    res = subprocess.run(
        [node_bin, "--test", str(ROOT / "apps/desktop/tests/projection.test.mjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
