"""Bind every model request to the existing durable token budget; never invent prices."""

import time

from openbot.application.budgets import BudgetService
from openbot.storage.inbox import InboundContext
from openbot.storage.writer import Writer


class RuntimeBudget:
    def __init__(self, writer: Writer, context: InboundContext, task_id: str):
        self.writer, self.context, self.task_id = writer, context, task_id
        self.service = BudgetService(writer)

    def reserve(self, request_id: str, units: int) -> None:
        cmd = self.service.reserve(
            self.context,
            self.task_id,
            call_ref=request_id,
            kind="MODEL",
            reserved_amount_micros=0,
            reserved_tokens=units,
            request_id="agent-reserve:" + request_id,
            deadline_monotonic_ms=int(time.monotonic() * 1000) + 5000,
        )
        self.writer.submit(cmd).result(timeout=5)

    def settle(self, request_id: str, input_tokens: int, output_tokens: int) -> None:
        cmd = self.service.settle(
            self.context,
            self.task_id,
            call_ref=request_id,
            actual_amount_micros=0,
            actual_tokens=input_tokens + output_tokens,
            request_id="agent-settle:" + request_id,
            deadline_monotonic_ms=int(time.monotonic() * 1000) + 5000,
        )
        self.writer.submit(cmd).result(timeout=5)

    def unknown(self, request_id: str) -> None:
        cmd = self.service.mark_unknown(
            self.context,
            self.task_id,
            call_ref=request_id,
            reason="MODEL_USAGE_UNKNOWN",
            request_id="agent-unknown:" + request_id,
            deadline_monotonic_ms=int(time.monotonic() * 1000) + 5000,
        )
        self.writer.submit(cmd).result(timeout=5)
