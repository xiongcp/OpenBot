from openbot_feishu.progress import FeishuProgressCardCoordinator


def test_feishu_progress_coalesces_100_updates_and_protects_terminal_state() -> None:
    coord = FeishuProgressCardCoordinator(min_interval_ms=500)

    # 1. Rapid 100 progress updates within throttle window coalesce into 1 pending revision
    for i in range(1, 101):
        coord.record_update(
            task_id="tsk_1",
            state="RUNNING",
            summary=f"step {i}",
            now_ms=1000 + i,
        )
    due = coord.drain_due(now_ms=2000)
    assert len(due) == 1
    assert due[0].summary == "step 100"
    assert due[0].coalesced_count == 99

    # 2. retry_after delays next flush until backoff expires
    coord.on_rate_limited(task_id="tsk_1", retry_after_ms=3000, now_ms=2000)
    coord.record_update(task_id="tsk_1", state="RUNNING", summary="step 101", now_ms=2500)
    assert coord.drain_due(now_ms=4000) == ()
    due_after = coord.drain_due(now_ms=5001)
    assert len(due_after) == 1

    # 3. Terminal state (SUCCEEDED/FAILED/CANCELLED) is never overwritten by late RUNNING updates
    coord.record_update(task_id="tsk_1", state="SUCCEEDED", summary="done", now_ms=6000)
    coord.record_update(task_id="tsk_1", state="RUNNING", summary="late step 50", now_ms=6005)
    final_due = coord.drain_due(now_ms=6010)
    assert len(final_due) == 1
    assert final_due[0].state == "SUCCEEDED"
    assert final_due[0].summary == "done"
