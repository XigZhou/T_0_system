from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    processed_dir: str = Field(..., description="Directory containing per-stock processed CSV files")
    start_date: str = Field("", description="Backtest start date YYYYMMDD")
    end_date: str = Field("", description="Backtest end date YYYYMMDD")
    buy_condition: str = Field(..., description="Comma-separated boolean filters")
    score_expression: str = Field(..., description="Arithmetic score expression for TopN ranking")
    top_n: int = Field(10, ge=1, le=500)
    initial_cash: float = Field(1_000_000.0, gt=0)
    lot_size: int = Field(100, ge=1)
    buy_fee_rate: float = Field(0.0003, ge=0)
    sell_fee_rate: float = Field(0.0003, ge=0)
    stamp_tax_sell: float = Field(0.001, ge=0)
    realistic_execution: bool = Field(False)
    slippage_bps: float = Field(0.0, ge=0)
    min_commission: float = Field(0.0, ge=0)


class BacktestResponse(BaseModel):
    summary: dict
    daily_rows: list[dict]
    pick_rows: list[dict]
    trade_rows: list[dict]
    contribution_rows: list[dict]
    diagnostics: dict


@dataclass
class Position:
    symbol: str
    name: str
    shares: int
    buy_date: str
    buy_price: float
    buy_net_amount: float
    buy_adj_factor: float | None = None
