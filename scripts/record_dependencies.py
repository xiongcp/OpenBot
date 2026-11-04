"""Capture installed license texts and lock identities after local qualification."""

import hashlib
import json
import platform
import re
import sys
import tomllib
from importlib.metadata import distributions
from pathlib import Path

from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename

ROOT = Path(__file__).resolve().parents[1]


def run(stage="m0"):
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    packages = {p["name"]: p for p in lock["package"]}
    core = set()

    def walk(name):
        if name in core:
            return
        core.add(name)
        for dep in packages[name].get("dependencies", []):
            walk(dep["name"])

    for dep in packages["openbot"]["dependencies"]:
        walk(dep["name"])
    target = ROOT / "components/admissions"
    target.mkdir(exist_ok=True)
    tags = set(sys_tags())
    records = {}
    for dist in distributions():
        name = re.sub(r"[-_.]+", "-", dist.metadata["Name"]).lower()
        if name == "openbot":
            continue
        package = packages[name]
        wheels = [
            w
            for w in package.get("wheels", [])
            if parse_wheel_filename(w["url"].rsplit("/", 1)[1])[3] & tags
        ]
        if not wheels:
            raise ValueError("No locked wheel for installed platform: " + name)
        artifact = wheels[0]
        license_files = []
        for item in dist.files or []:
            if not (
                "dist-info/" in str(item)
                and any(x in item.name.upper() for x in ["LICENSE", "LICENCE", "COPYING", "NOTICE"])
            ):
                continue
            data = Path(dist.locate_file(item)).read_bytes()
            dest = ROOT / "evidence/implementation/licenses" / name / item.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            license_files.append(
                {"path": str(dest.relative_to(ROOT)), "sha256": hashlib.sha256(data).hexdigest()}
            )
        license_name = (
            dist.metadata.get("License-Expression")
            or {
                "pathspec": "MPL-2.0",
                "rfc8785": "Apache-2.0",
                "ruff": "MIT",
                "rfc3339-validator": "MIT",
                "six": "MIT",
            }.get(name)
            or dist.metadata.get("License")
        )
        if not license_name or not license_files:
            raise ValueError("Review installed license first: " + name)
        records[name] = {
            "package": name,
            "version": dist.version,
            "phase": "M0",
            "component_id": (
                "rfc8785"
                if name == "rfc8785"
                else "pydantic-jsonschema"
                if name in core
                else "cli-toolchain"
            ),
            "group": "core" if name in core else "dev-contracts",
            "state": "LOCAL_TESTED",
            "source": artifact["url"],
            "sha256": artifact["hash"].removeprefix("sha256:"),
            "license": license_name,
            "license_files": license_files,
            "upstream_metadata": f"https://pypi.org/project/{name}/{dist.version}/",
            "evidence": ["evidence/implementation/m0-tests.log"],
        }
    if stage == "m1-sdk":
        m0_names = {
            p["package"]
            for p in json.loads((ROOT / "components/admissions/m0.json").read_text())["packages"]
        }
        for name, record in records.items():
            if name not in m0_names:
                record.update(
                    phase="M1",
                    group="provider-openai",
                    component_id="httpx"
                    if name in {"httpx", "httpcore", "certifi", "idna", "anyio", "h11", "sniffio"}
                    else "model-openai",
                    evidence=["evidence/implementation/m1-sdk-tests.log"],
                )
    result = {
        "schema_version": "1.0",
        "phase": "M0" if stage == "m0" else "M1",
        "platform": [platform.system(), platform.machine()],
        "python": sys.version,
        "lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "lock_snapshot": f"components/locks/{stage}.uv.lock",
        "runtime_enabled": False,
        "packages": [records[n] for n in sorted(records)],
    }
    snapshot = ROOT / result["lock_snapshot"]
    if snapshot.exists() and snapshot.read_bytes() != (ROOT / "uv.lock").read_bytes():
        raise ValueError("Preserve prior lock; use a new record for dependency upgrades")
    snapshot.write_bytes((ROOT / "uv.lock").read_bytes())
    (target / (stage + ".json")).write_text(json.dumps(result, indent=2) + "\n")
    print(f"Recorded {len(records)} installed distributions and license texts")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "m0")
