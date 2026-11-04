import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_browser_dom_source_reuse_audit_records_no_copy_and_forbids_agent_run() -> None:
    rec_path = ROOT / "components/source-reuse/browser-dom.json"
    doc_path = ROOT / "docs/evidence/source-reuse-browser-dom.md"
    assert rec_path.is_file()
    assert doc_path.is_file()
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    assert rec["task_id"] == "OB-095"
    assert rec["decision"] == "NO_COPY"
    assert rec["autonomous_agent_run_permitted"] is False
    assert rec["extraction_verification"] == "NOT_APPLICABLE"
