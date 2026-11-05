from pathlib import Path

from openbot.cli import build_cli_parser

ROOT = Path(__file__).resolve().parents[2]


def test_getting_started_troubleshooting_and_security_docs_cover_boundaries() -> None:
    gs = ROOT / "docs/getting-started.md"
    ts = ROOT / "docs/troubleshooting.md"
    sec = ROOT / "SECURITY.md"
    ext = ROOT / "docs/evidence/external-environments.md"
    acc = ROOT / "docs/releases/mvp-acceptance.md"
    assert gs.is_file()
    assert ts.is_file()
    assert sec.is_file()
    assert ext.is_file()
    assert acc.is_file()

    gs_text = gs.read_text(encoding="utf-8")
    ts_text = ts.read_text(encoding="utf-8")
    sec_text = sec.read_text(encoding="utf-8")
    ext_text = ext.read_text(encoding="utf-8")
    acc_text = acc.read_text(encoding="utf-8")

    assert "operation reconcile" in ts_text
    assert "--ignore-and-rerun" in ts_text
    assert "M4" in gs_text
    assert "daemon serve" in gs_text
    assert "English Summary" in gs_text
    assert "English Summary" in ts_text
    assert "English Summary" in sec_text

    # Capability matrix must separate implementation_status and verification_status
    assert "implementation_status" in acc_text
    assert "verification_status" in acc_text
    assert "M1 仍未完成" not in ext_text

    # Verify documented CLI command forms parse through the real build_cli_parser()
    parser = build_cli_parser()
    for sample_argv in (
        ["daemon", "serve", "--profile-dir", "/tmp/p1"],
        ["health", "--profile-dir", "/tmp/p1", "--require-daemon"],
        ["task", "create", "--profile-dir", "/tmp/p1", "--workspace", "wsp_1", "--goal", "g"],
        [
            "approval",
            "decide",
            "--profile-dir",
            "/tmp/p1",
            "--approval-id",
            "apr_1",
            "--expected-version",
            "1",
            "--binding-hash",
            "h",
            "--decision",
            "APPROVE",
        ],
        [
            "operation",
            "reconcile",
            "--profile-dir",
            "/tmp/p1",
            "--operation-id",
            "op_1",
            "--expected-version",
            "4",
            "--outcome",
            "CONFIRMED_SUCCEEDED",
            "--evidence-content",
            "ok",
        ],
    ):
        parsed = parser.parse_args(sample_argv)
        assert parsed.group is not None
