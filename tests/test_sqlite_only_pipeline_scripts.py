from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _script_text(name: str) -> str:
    return (ROOT / "scripts" / name).read_text(encoding="utf-8")


def test_core_after_close_pipeline_uses_sqlite_feature_update_not_data_bundle():
    text = _script_text("run_core_after_close_pipeline.sh")

    assert "data_bundle" not in text
    assert "run_daily_top100_update.sh" not in text
    assert "collect_stock_daily_raw.py" in text
    assert "compute_stock_daily_features.py" in text
    assert "run_stock_pool_template_update.py" not in text
    assert "--source \"${STOCK_POOL_SOURCE}\"" in text
    assert 'STOCK_POOL_SOURCE="${STOCK_POOL_SOURCE:-all}"' in text
    assert "sqlite_raw_collect" in text
    assert "sqlite_feature_compute" in text
    assert "stock_daily_features" in text


def test_paper_trading_cron_uses_shared_sqlite_trade_calendar_check():
    text = _script_text("run_paper_trading_cron.sh")
