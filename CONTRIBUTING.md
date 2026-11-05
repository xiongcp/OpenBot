# Contributing to OpenBot

Thank you for contributing to OpenBot. Before submitting changes, review [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md), [SECURITY.md](SECURITY.md), and [docs/project-status.json](docs/project-status.json).

## Local Verification

```sh
uv sync --locked
.venv/bin/python scripts/verify.py
.venv/bin/openbot doctor --json
```

## Core Safety Invariants

1. All tool effects execute through the authoritative Broker; model output, MCP metadata, DOM/AX trees, and workspace memory are `TAINTED_EXTERNAL`.
2. Approvals only transition operations to `READY`; `CONSUMED` grants never revive.
3. Uncertain outcomes remain `UNKNOWN / RECONCILING` with zero automatic replay.
4. Secrets never enter process `argv`, child `env`, WebView DOM, logs, or diagnostic bundles.
5. Every change to controlled supply-chain files must update `release/checksums.json` in the same commit.

## License

Contributions are licensed under the [Apache License 2.0](LICENSE).
