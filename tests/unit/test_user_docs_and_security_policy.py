from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_getting_started_troubleshooting_and_security_docs_cover_boundaries() -> None:
    gs = ROOT / "docs/getting-started.md"
    ts = ROOT / "docs/troubleshooting.md"
    sec = ROOT / "SECURITY.md"
    assert gs.is_file()
    assert ts.is_file()
    assert sec.is_file()

    gs_text = gs.read_text(encoding="utf-8")
    ts_text = ts.read_text(encoding="utf-8")
    sec_text = sec.read_text(encoding="utf-8")

    assert "operation reconcile" in ts_text
    assert "--ignore-and-rerun" in ts_text
    assert "M4" in gs_text
    assert "English Summary" in gs_text
    assert "English Summary" in ts_text
    assert "English Summary" in sec_text
