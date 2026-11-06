import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location(
        "live_model_smoke", ROOT / "scripts/live_model_smoke.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("flag", ["--api-key", "--key", "--endpoint", "--secret"])
def test_credentials_are_never_accepted_as_arguments(flag, tmp_path):
    mod = load()
    with pytest.raises(SystemExit):
        mod.parse_args([flag, "x", "--evidence-dir", str(tmp_path)])


def test_evidence_redaction_drops_secrets_and_bodies():
    mod = load()
    record = mod.sanitize_evidence(
        {"endpoint": "https://h/v1", "api_key": "sk-abc", "file_text": "body", "requests": 5}
    )
    assert record == {"requests": 5}
