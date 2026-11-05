# OpenBot Support & Recovery Guide

## Self-Service Diagnostics & Safe Repair

Run the built-in 10-probe environment doctor:

```sh
.venv/bin/openbot doctor --profile-dir ~/.openbot/default --fix-safe --json
```

## Handling `UNKNOWN / RECONCILING` Operations

An `UNKNOWN` state means an operation was dispatched before a crash or timeout and its external effect is unconfirmed. Do not re-run the task blindly:

1. Inspect the operation in the Desktop **Reconciliation Wizard** or via `openbot operation show --operation-id <id> --json`.
2. Verify whether the target file or external side effect occurred.
3. Submit inline evidence and resolve as `CONFIRMED_SUCCEEDED` or `CONFIRMED_NOT_EXECUTED`.

## Reporting Issues

Use the repository Issue templates and never attach API keys, tokens, cookies, raw databases, or unredacted logs. Report security vulnerabilities privately per [SECURITY.md](SECURITY.md).
