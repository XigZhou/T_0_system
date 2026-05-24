from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from overnight_bt.sector_dashboard import (
    build_sector_dashboard_payload,
    upsert_sector_dashboard_rows,
)


class _sqlite_only:
    def __enter__(self):
        self.old_value = os.environ.get("T0_SQLITE_ONLY")
        os.environ["T0_SQLITE_ONLY"] = "1"
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.old_value is None:
            os.environ.pop("T0_SQLITE_ONLY", None)
        else:
            os.environ["T0_SQLITE_ONLY"] = self.old_value


def test_sector_dashboard_defaults_to_market_sqlite_rows():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        db_path = base / "market_data.sqlite"
        upsert_sector_dashboard_rows(
            db_path=db_path,
            theme_strength_rows=[
                {
                    "trade_date": "20240103",
                    "theme_rank": 1,
                    "theme_name": "AI算力",
                    "theme_score": 0.91,
                    "volume_price_score": 0.88,
                    "reversal_score": 0.22,
                    "m5": 0.05,
                    "m20": 0.12,
                    "m60": 0.2,
                    "m120": 0.3,
                    "amount_ratio_20": 1.5,
                    "board_up_ratio": 0.8,
                    "positive_m20_ratio": 0.9,
                    "strongest_board": "算力概念",
                    "strongest_subtheme": "服务器",
                    "strongest_board_score": 0.93,
                    "board_count": 2,
                    "subtheme_count": 1,
                    "theme_rank_pct": 0.0,
                }
            ],
            board_strength_rows=[
                {
                    "trade_date": "20240103",
                    "board_rank_overall": 1,
                    "board_rank_in_theme": 1,
                    "theme_name": "AI算力",
                    "subtheme_name": "服务器",
                    "board_type": "concept",
                    "board_name": "算力概念",
                    "theme_board_score": 0.93,
                    "volume_price_score": 0.88,
                    "reversal_score": 0.22,
                    "pct_chg": 2.3,
                    "m5": 0.06,
                    "m20": 0.13,
                    "m60": 0.21,
                    "m120": 0.31,
                    "amount_ratio_20": 1.6,
                }
            ],
            stock_exposure_rows=[
                {
                    "stock_code": "601138",
                    "stock_name": "工业富联",
                    "primary_theme": "AI算力",
                    "primary_subtheme": "服务器",
                    "exposure_score": 1.0,
                    "theme_count": 1,
                    "subtheme_count": 1,
                    "board_count": 1,
                    "theme_names": "AI算力",
                    "subtheme_names": "服务器",
                    "board_names": "算力概念",
                    "matched_keywords": "算力",
                    "latest_fetched_at": "2024-01-03 15:00:00",
                }
            ],
            mapping_rows=[
                {
                    "theme_name": "AI算力",
                    "subtheme_name": "服务器",
                    "matched_keyword": "算力",
                    "board_type": "concept",
                    "board_code": "BK0001",
                    "board_name": "算力概念",
                    "source": "test",
                    "fetched_at": "2024-01-03 15:00:00",
                }
            ],
            market_context_rows=[
                {
                    "trade_date": "20240103",
                    "sh_close": 3000.0,
                    "sh_pct_chg": 0.8,
                    "sh_m20": 0.02,
                    "sh_m60": 0.01,
                    "hs300_close": 3500.0,
                    "hs300_pct_chg": 0.6,
                    "hs300_m20": 0.03,
                    "hs300_m60": 0.02,
                    "cyb_close": 1900.0,
                    "cyb_pct_chg": 1.2,
                    "cyb_m20": -0.01,
                    "cyb_m60": -0.02,
                }
            ],
            summary={"latest_trade_date": "20240103", "error_count": 0},
        )

        payload = build_sector_dashboard_payload(base_dir=base, db_path=db_path)

        assert payload["status"] == "ready"
        assert payload["summary"]["latest_trade_date"] == "20240103"
        assert payload["summary"]["theme_daily_rows"] == 1
        assert payload["summary"]["source"] == "sqlite"
        assert payload["latest_themes"][0]["theme_name"] == "AI算力"
        assert payload["latest_boards"][0]["board_name"] == "算力概念"
        assert payload["stock_exposure"][0]["stock_code"] == "601138"
        assert payload["mapping_rows"][0]["board_code"] == "BK0001"
        assert payload["market_context"]["status"] == "ready"
        assert payload["market_context"]["path"] == "market_data.sqlite:sector_market_context"


def test_sector_dashboard_empty_sqlite_does_not_require_csv_or_data_bundle():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        payload = build_sector_dashboard_payload(base_dir=base, db_path=base / "market_data.sqlite")

        assert payload["status"] == "empty"
        assert payload["summary"]["source"] == "sqlite"
        assert payload["paths"]["storage"] == "SQLite"
        assert any("SQLite 板块研究数据未初始化" in message for message in payload["messages"])
        assert all("data_bundle" not in message for message in payload["messages"])


def test_sector_dashboard_sqlite_only_blocks_legacy_csv_source():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        processed = base / "sector_research" / "data" / "processed"
        report = base / "sector_research" / "reports"
        processed.mkdir(parents=True)
        report.mkdir(parents=True)
        (processed / "theme_strength_daily.csv").write_text(
            "trade_date,theme_name,theme_score\n20240103,AI算力,0.9\n",
            encoding="utf-8",
        )

        with _sqlite_only(), pytest.raises(RuntimeError, match="SQLite-only mode blocks legacy source"):
            build_sector_dashboard_payload(
                base_dir=base,
                source="csv",
                processed_dir="sector_research/data/processed",
                report_dir="sector_research/reports",
            )
