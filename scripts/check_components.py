"""Offline installation admission; design recommendations never authorize a runtime."""

import hashlib
import json
import platform
import re
import sys
import tomllib
from importlib.metadata import distributions
from pathlib import Path

from packaging.markers import Marker


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def validate_record(record, catalog, phase):
    component = catalog.get(record["component_id"])
    if not component or component["decision"] not in {"DEFAULT_ADAPTER", "GATED_CANDIDATE"}:
        raise ValueError("Unapproved component")
    phases = ["M0", "M1", "M2", "M3", "M4", "P2"]
    if phases.index(record["phase"]) > phases.index(phase):
        raise ValueError("Component is from a later phase")
    if phases.index(component["introduction_phase"]) > phases.index(record["phase"]):
        raise ValueError("Catalog introduction gate not met")
    if record["state"] != "LOCAL_TESTED":
        raise ValueError("Component qualification missing")
    if not re.fullmatch(r"[a-f0-9]{64}", record["sha256"]):
        raise ValueError("Artifact hash missing")
    if not record["source"].startswith("https://files.pythonhosted.org/"):
        raise ValueError("Unapproved package source")
    if record["license"] in {"", "UNKNOWN", "VERIFY_BEFORE_ADMISSION"}:
        raise ValueError("License unknown")
    if not record["license_files"] or not record["evidence"]:
        raise ValueError("License or qualification evidence missing")


def verify(root, phase):
    lock = tomllib.loads((root / "uv.lock").read_text())
    catalog = {
        c["component_id"]: c
        for c in json.loads((root / "components/catalog.json").read_text())["components"]
    }
    stage = "m0" if phase == "M0" else "m1-sdk"
    admission = json.loads((root / f"components/admissions/{stage}.json").read_text())
    if admission["runtime_enabled"]:
        raise ValueError("Development qualification cannot enable runtime capabilities")
    snapshot = root / admission["lock_snapshot"]
    if admission["lock_sha256"] != hashlib.sha256(snapshot.read_bytes()).hexdigest():
        raise ValueError("Lock changed: requalify the affected components")
    # Each native OS uses a separate qualification file. This record is macOS only.
    if admission["platform"] != [platform.system(), platform.machine()]:
        raise ValueError("No qualification for this native platform")
    all_locked = {p["name"]: p for p in lock["package"]}
    selected = set()

    def select(dep):
        if dep.get("marker") and not Marker(dep["marker"]).evaluate():
            return
        name = dep["name"]
        if name in selected:
            return
        selected.add(name)
        for child in all_locked[name].get("dependencies", []):
            select(child)

    root_package = all_locked["openbot"]
    dependencies = root_package["dependencies"] + root_package["dev-dependencies"]["dev-contracts"]
    if phase == "M1":
        dependencies += root_package["dev-dependencies"]["provider-openai"]
    for dep in dependencies:
        select(dep)
    locked = {n: p for n, p in all_locked.items() if n in selected}
    records = {r["package"]: r for r in admission["packages"]}
    if len(records) != len(admission["packages"]):
        raise ValueError("Duplicate qualification records")
    if set(records) != set(locked):
        raise ValueError("Lock/admission package mismatch")
    installed = {
        normalize(d.metadata["Name"]): d.version
        for d in distributions()
        if normalize(d.metadata["Name"]) != "openbot"
    }
    if installed != {n: r["version"] for n, r in records.items()}:
        raise ValueError("Installed package set does not match the qualified environment")
    for name, record in records.items():
        validate_record(record, catalog, phase)
        package = locked[name]
        if package["version"] != record["version"]:
            raise ValueError("Version drift")
        artifacts = package.get("wheels", []) + [package.get("sdist", {})]
        if not any(
            a.get("url") == record["source"] and a.get("hash") == "sha256:" + record["sha256"]
            for a in artifacts
        ):
            raise ValueError("Artifact not in the actual lock")
        for license_file in record["license_files"]:
            path = root / license_file["path"]
            if (
                not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != license_file["sha256"]
            ):
                raise ValueError("License evidence missing or modified")
        if not all((root / p).is_file() for p in record["evidence"]):
            raise ValueError("Qualification evidence missing")
    return {
        "scope": "local development and contracts only",
        "packages": len(records),
        "runtime_capabilities_enabled": False,
        "platform": admission["platform"],
    }


if __name__ == "__main__":
    try:
        phase = sys.argv[1] if len(sys.argv) > 1 else "M0"
        if phase not in {"M0", "M1"}:
            raise ValueError("No actual qualification record for the requested phase")
        print(json.dumps(verify(Path(__file__).resolve().parents[1], phase)))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
