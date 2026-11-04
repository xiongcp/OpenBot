"""Offline, fixed-seed replay with actual SQLite state snapshots and effect counts."""

import json
import platform
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services/core/src")]

from tests.fakes.ports import CrashInjected  # noqa: E402
from tests.protocol.early_recovery_poc.model import POINTS, ProtocolPoc  # noqa: E402


def run():
    snapshots = []
    for point in POINTS:
        with TemporaryDirectory(prefix="openbot-poc-") as directory:
            model = ProtocolPoc(Path(directory))
            model.receive()
            model.propose()
            model.approve()
            try:
                model.run(crash=point)
            except CrashInjected:
                pass
            else:
                raise AssertionError("Fault point not exercised")
            before = model.snapshot()
            clock = model.clock
            model.close()
            model = ProtocolPoc(Path(directory), clock=clock)
            model.recover(old_isolated=True)
            after = model.snapshot()
            if before["operation"] == "DISPATCHING":
                assert after["operation"] == "UNKNOWN"
                assert after["quarantine"]
                assert after["effects"] == before["effects"]
            elif after["operation"] == "READY":
                model.run()
                assert model.snapshot()["effects"] == 1
            snapshots.append(
                {
                    "seed": 7,
                    "fault": point,
                    "before": before,
                    "recovered": after,
                    "final": model.snapshot(),
                }
            )
            model.close()
    return {
        "scope": "M0 protocol only; synthetic worker; not OS isolation",
        "platform": [platform.system(), platform.machine()],
        "python": sys.version,
        "sqlite": sqlite3.sqlite_version,
        "scenarios": snapshots,
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
