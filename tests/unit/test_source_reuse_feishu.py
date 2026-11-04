import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_feishu_source_reuse_audit_records_no_copy_without_vendoring_upstream_runtime() -> None:
    rec_path = ROOT / "components/source-reuse/feishu.json"
    doc_path = ROOT / "docs/evidence/source-reuse-feishu.md"
    assert rec_path.is_file()
    assert doc_path.is_file()
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    assert rec["task_id"] == "OB-094"
    assert rec["decision"] == "NO_COPY"
    assert rec["candidates_reviewed"] == ["nanobot", "langbot"]
    assert rec["files"] == []
    assert rec["extraction_verification"] == "NOT_APPLICABLE"
    assert "first-user" in rec["reason"]
