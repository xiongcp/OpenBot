"""Minimal M0 diagnostics. Task commands belong to OB-028."""

import argparse
import json
from collections.abc import Sequence

from openbot import __version__


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="openbot")
    parser.add_argument("command", choices=("version", "health"))
    args = parser.parse_args(argv)
    if args.command == "version":
        print(__version__)
    else:
        print(
            json.dumps(
                {
                    "version": __version__,
                    "daemon_running": False,
                    "isolation": "CAPABILITY_UNAVAILABLE",
                    "stage": "M0",
                }
            )
        )
    return 0
