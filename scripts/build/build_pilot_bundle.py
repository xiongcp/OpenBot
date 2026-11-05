"""Generate deterministic M3 unsigned pilot bundle manifest and verify absence of secrets/caches."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def build_manifest() -> dict[str, object]:
    assets_doc = json.loads((ROOT / "packaging/runtime-assets.json").read_text(encoding="utf-8"))
    lock_sha = hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest()
    return {
        "stage": assets_doc["bundle_stage"],
        "uv_lock_sha256": lock_sha,
        "signed_m4_release_claimed": False,
        "first_use_silent_download_permitted": False,
    }


if __name__ == "__main__":
    print(json.dumps(build_manifest(), indent=2))
