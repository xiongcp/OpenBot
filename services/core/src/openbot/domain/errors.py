from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OutcomeError:
    code: str
    message: str
    retryable: bool
    trace_id: str
    operation_state: str
    task_state: str

    def public(self) -> dict[str, str | bool]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "trace_id": self.trace_id,
        }


def outcome_error(reason: str, *, dispatched: bool, trace_id: str) -> OutcomeError:
    if dispatched:
        return OutcomeError(
            "OUTCOME_UNKNOWN",
            "Outcome requires reconciliation",
            False,
            trace_id,
            "UNKNOWN",
            "RECONCILING",
        )
    if reason == "policy":
        return OutcomeError("POLICY_DENIED", "Action denied", False, trace_id, "REJECTED", "PAUSED")
    return OutcomeError(
        "REQUEST_NOT_COMPLETED",
        "Query the stable request identifier",
        False,
        trace_id,
        "READY",
        "WAITING_RESOURCE",
    )
