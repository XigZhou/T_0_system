from __future__ import annotations

from datetime import datetime
from typing import Protocol

import pandas as pd


class SectorDataProvider(Protocol):
    def list_boards(self, board_type: str) -> pd.DataFrame:
        ...

    def fetch_board_history(self, board_name: str, board_type: str, start_date: str, end_date: str) -> pd.DataFrame:
        ...

    def fetch_board_constituents(self, board_name: str, board_type: str) -> pd.DataFrame:
        ...

    def fetch_fund_flow_rank(self, board_type: str, indicator: str) -> pd.DataFrame:
        ...


class AkshareSectorDataProvider:
    source = "AKShare"

    def __init__(self) -> None:
        try:
            import akshare as ak
        except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
            raise ModuleNotFoundError("请先安装 akshare：pip install akshare") from exc
        self.ak = ak

    def list_boards(self, board_type: str) -> pd.DataFrame:
        if board_type == "industry":
            raw = self.ak.stock_board_industry_name_em()
        elif board_type == "concept":
            raw = self.ak.stock_board_concept_name_em()
        else:
            raise ValueError(f"未知板块类型: {board_type}")
        return _standardize_board_list(raw, board_type, self.source)

    def fetch_board_history(self, board_name: str, board_type: str, start_date: str, end_date: str) -> pd.DataFrame:
        if board_type == "industry":
            raw = self.ak.stock_board_industry_hist_em(
                symbol=board_name,
                start_date=start_date,
                end_date=end_date,
                period="日k",
                adjust="",
            )
        elif board_type == "concept":
            raw = self.ak.stock_board_concept_hist_em(
                symbol=board_name,
                start_date=start_date,
                end_date=end_date,
                period="daily",
                adjust="",
            )
        else:
            raise ValueError(f"未知板块类型: {board_type}")
        return _standardize_board_history(raw, board_name, board_type, self.source)

    def fetch_board_constituents(self, board_name: str, board_type: str) -> pd.DataFrame:
        if board_type == "industry":
            raw = self.ak.stock_board_industry_cons_em(symbol=board_name)
        elif board_type == "concept":
            raw = self.ak.stock_board_concept_cons_em(symbol=board_name)
        else:
            raise ValueError(f"未知板块类型: {board_type}")
        return _standardize_constituents(raw, board_name, board_type, self.source)

    def fetch_fund_flow_rank(self, board_type: str, indicator: str) -> pd.DataFrame:
        sector_type = "行业资金流" if board_type == "industry" else "概念资金流"
        raw = self.ak.stock_sector_fund_flow_rank(indicator=indicator, sector_type=sector_type)
        return _standardize_fund_flow(raw, board_type, indicator, self.source)


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _first_col(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    for item in candidates:
        if item in frame.columns:
            return item
    return None


def _to_number(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text or text in {"-", "--", "None", "nan"}:
        return None
    multiplier = 1.0
    for suffix, suffix_multiplier in (("万亿", 1_000_000_000_000.0), ("亿", 100_000_000.0), ("万", 10_000.0)):
        if text.endswith(suffix):
            multiplier = suffix_multiplier
            text = text[: -len(suffix)]
            break
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def _numeric_series(frame: pd.DataFrame, candidates: list[str]) -> pd.Series:
    col = _first_col(frame, candidates)
    if col is None:
        return pd.Series([pd.NA] * len(frame), index=frame.index, dtype="Float64")
    return frame[col].map(_to_number).astype("Float64")


def _text_series(frame: pd.DataFrame, candidates: list[str]) -> pd.Series:
    col = _first_col(frame, candidates)
    if col is None:
        return pd.Series([""] * len(frame), index=frame.index, dtype=object)
    return frame[col].fillna("").astype(str).str.strip()


def _stock_code_series(frame: pd.DataFrame, candidates: list[str]) -> pd.Series:
    return _text_series(frame, candidates).map(_normalize_stock_code)


def _normalize_stock_code(value: object) -> str:
    text = str(value or "").strip()
    if not text or text in {"-", "--", "None", "nan"}:
        return ""
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return text
    if len(digits) <= 6:
        return digits.zfill(6)
    return digits[-6:]


def _standardize_board_list(raw: pd.DataFrame, board_type: str, source: str) -> pd.DataFrame:
    frame = raw.copy()
    name = _text_series(frame, ["板块名称", "名称", "行业名称", "概念名称"])
    code = _text_series(frame, ["板块代码", "代码"])
    result = pd.DataFrame(
        {
            "board_type": board_type,
            "board_code": code,
            "board_name": name,
            "latest_price": _numeric_series(frame, ["最新价", "最新"]),
            "pct_chg": _numeric_series(frame, ["涨跌幅", "涨幅"]),
            "amount": _numeric_series(frame, ["成交额"]),
            "turnover_rate": _numeric_series(frame, ["换手率"]),
            "up_count": _numeric_series(frame, ["上涨家数"]),
            "down_count": _numeric_series(frame, ["下跌家数"]),
            "leader_stock": _text_series(frame, ["领涨股票", "领涨股"]),
            "source": source,
            "fetched_at": _now_text(),
        }
    )
    return result[result["board_name"] != ""].drop_duplicates(["board_type", "board_name"]).reset_index(drop=True)


def _standardize_board_history(raw: pd.DataFrame, board_name: str, board_type: str, source: str) -> pd.DataFrame:
    frame = raw.copy()
    result = pd.DataFrame(
        {
            "trade_date": _text_series(frame, ["日期", "trade_date"]).str.replace("-", "", regex=False),
            "board_type": board_type,
            "board_name": board_name,
            "open": _numeric_series(frame, ["开盘", "open"]),
            "close": _numeric_series(frame, ["收盘", "close"]),
            "high": _numeric_series(frame, ["最高", "high"]),
            "low": _numeric_series(frame, ["最低", "low"]),
            "pct_chg": _numeric_series(frame, ["涨跌幅", "pct_chg"]),
            "vol": _numeric_series(frame, ["成交量", "vol"]),
            "amount": _numeric_series(frame, ["成交额", "amount"]),
            "turnover_rate": _numeric_series(frame, ["换手率", "turnover_rate"]),
            "source": source,
        }
    )
    result = result[result["trade_date"] != ""].copy()
    return result.sort_values("trade_date").reset_index(drop=True)


def _standardize_constituents(raw: pd.DataFrame, board_name: str, board_type: str, source: str) -> pd.DataFrame:
    frame = raw.copy()
    result = pd.DataFrame(
        {
            "board_type": board_type,
            "board_name": board_name,
            "stock_code": _stock_code_series(frame, ["代码", "股票代码", "symbol"]),
            "stock_name": _text_series(frame, ["名称", "股票名称", "name"]),
            "latest_price": _numeric_series(frame, ["最新价", "最新"]),
            "pct_chg": _numeric_series(frame, ["涨跌幅", "涨幅"]),
            "amount": _numeric_series(frame, ["成交额"]),
            "turnover_rate": _numeric_series(frame, ["换手率"]),
            "source": source,
            "fetched_at": _now_text(),
        }
    )
    result = result[(result["stock_code"] != "") | (result["stock_name"] != "")].copy()
    return result.drop_duplicates(["board_type", "board_name", "stock_code", "stock_name"]).reset_index(drop=True)


def _standardize_fund_flow(raw: pd.DataFrame, board_type: str, indicator: str, source: str) -> pd.DataFrame:
    frame = raw.copy()
    result = pd.DataFrame(
        {
            "board_type": board_type,
            "fund_flow_indicator": indicator,
            "board_name": _text_series(frame, ["名称", "板块名称"]),
            "pct_chg": _numeric_series(frame, ["涨跌幅"]),
            "main_net_inflow": _numeric_series(frame, ["主力净流入-净额", f"{indicator}主力净流入-净额", "今日主力净流入-净额"]),
            "main_net_inflow_ratio": _numeric_series(frame, ["主力净流入-净占比", f"{indicator}主力净流入-净占比", "今日主力净流入-净占比"]),
            "super_net_inflow": _numeric_series(frame, ["超大单净流入-净额", f"{indicator}超大单净流入-净额"]),
            "source": source,
            "fetched_at": _now_text(),
        }
    )
    return result[result["board_name"] != ""].reset_index(drop=True)
