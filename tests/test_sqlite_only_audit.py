from __future__ import annotations

from pathlib import Path

from scripts.audit_sqlite_only_read_paths import audit, main


def test_audit_detects_legacy_read_markers(tmp_path, capsys):
    root = tmp_path
    module_dir = root / "overnight_bt"
    module_dir.mkdir()
    (module_dir / "legacy_reader.py").write_text(
        "import pandas as pd\n"
        "pd.read_csv('data_bundle/processed_qfq/000001.csv')\n"
        "legacy_db_path = 'data_store/stock_pool_templates.sqlite'\n",
        encoding="utf-8",
    )

    findings = audit(root=root, scan_dirs=("overnight_bt",))

    categories = {item.category for item in findings}
    assert "data_bundle" in categories
    assert "pandas_read_csv" in categories
    assert "legacy_template_db" in categories


def test_audit_fail_on_legacy_returns_nonzero(tmp_path):
    root = tmp_path
    scripts_dir = root / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "legacy.sh").write_text("cat data_bundle/trade_calendar.csv\n", encoding="utf-8")

    code = main(["--root", str(root), "--fail-on-legacy"])

    assert code == 1


def test_audit_json_output(tmp_path, capsys):
    root = tmp_path
    static_dir = root / "static"
    static_dir.mkdir()
    (static_dir / "app.js").write_text("const path = 'configs/paper_accounts';\n", encoding="utf-8")

    code = main(["--root", str(root), "--json"])
    out = capsys.readouterr().out

    assert code == 0
    assert "legacy_yaml" in out
