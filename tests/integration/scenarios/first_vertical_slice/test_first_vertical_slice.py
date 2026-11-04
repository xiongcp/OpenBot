from pathlib import Path

import pytest
from openbot.application.vertical_slice import M1VerticalSliceHarness


def test_m1_vertical_slice_real_local_workspace_artifact_process_and_outbox_closed_loop(
    tmp_path: Path,
) -> None:
    harness = M1VerticalSliceHarness.create(tmp_path / "slice_real")
    try:
        report = harness.run_local_restricted_effect_slice()
        assert report["network_mode"] == "OFFLINE"
        assert report["real_production_services_called"] is False
        assert report["task_final_state"] == "SUCCEEDED"
        assert report["operation_final_state"] == "SUCCEEDED"
        assert report["approval_final_status"] == "CONSUMED"
        assert report["workspace_file_patched"] is True
        assert len(report["artifact_sha256"]) == 64
        assert report["worker_reaped"] is True
        assert report["outbox_status"] == "DELIVERED"
    finally:
        harness.close()


@pytest.mark.parametrize(
    "crash_point",
    [
        "before_claim",
        "after_claim_before_dispatch",
        "after_dispatch_before_effect",
        "after_effect_before_receipt",
        "after_complete_before_outbox_ack",
    ],
)
def test_m1_vertical_slice_five_crash_points_and_duplicate_inputs_never_double_execute(
    tmp_path: Path, crash_point: str
) -> None:
    harness = M1VerticalSliceHarness.create(tmp_path / f"slice_{crash_point}")
    try:
        outcome = harness.run_fault_crash_scenario(crash_point)
        assert outcome["duplicate_task_id_stable"] is True
        assert outcome["real_production_services_called"] is False
        if crash_point in {
            "before_claim",
            "after_claim_before_dispatch",
            "after_dispatch_before_effect",
        }:
            assert outcome["fault_executor_effect_count"] == 0
        else:
            assert outcome["fault_executor_effect_count"] == 1
        assert outcome["blind_replay_count"] == 0
        assert outcome["resolved_operation_state"] == "SUCCEEDED"
        assert outcome["resolved_task_state"] in {"QUEUED", "SUCCEEDED"}
    finally:
        harness.close()
