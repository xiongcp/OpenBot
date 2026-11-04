import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def checker():
    path = ROOT / "scripts/check_components.py"
    spec = importlib.util.spec_from_file_location("check_components", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_minimal_environment_matches_admission():
    check = checker()
    check.verify(ROOT, "M1" if importlib.util.find_spec("openai") else "M0")


@pytest.mark.parametrize(
    "mutation", ["unknown_package", "late_stage", "missing_hash", "license", "not_run"]
)
def test_unqualified_or_incomplete_records_block_capability(mutation):
    check = checker()
    record = {
        "package": "rfc8785",
        "version": "0.1.4",
        "phase": "M0",
        "component_id": "rfc8785",
        "state": "LOCAL_TESTED",
        "source": "https://files.pythonhosted.org/packages/example.whl",
        "sha256": "a" * 64,
        "license": "Apache-2.0",
        "license_files": [{"path": "licenses/test.txt", "sha256": "b" * 64}],
        "evidence": ["tests/contracts/test_contracts.py"],
    }
    catalog = {"rfc8785": {"decision": "DEFAULT_ADAPTER", "introduction_phase": "M0"}}
    bad = copy.deepcopy(record)
    if mutation == "unknown_package":
        bad["component_id"] = "unapproved"
    elif mutation == "late_stage":
        bad["phase"] = "M3"
    elif mutation == "missing_hash":
        bad["sha256"] = ""
    elif mutation == "license":
        bad["license"] = "UNKNOWN"
    else:
        bad["state"] = "NOT_RUN"
    with pytest.raises(ValueError):
        check.validate_record(bad, catalog, "M0")
