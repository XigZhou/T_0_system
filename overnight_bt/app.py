from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from .backtest import export_backtest_zip, run_portfolio_backtest
from .daily_plan import build_daily_plan
from .models import (
    BacktestRequest,
    BacktestResponse,
    DailyPlanRequest,
    DailyPlanResponse,
    PaperTemplateResponse,
    PaperTradingRunRequest,
    PaperTradingRunResponse,
    SignalQualityRequest,
    SignalQualityResponse,
    SingleStockBacktestRequest,
    SingleStockBacktestResponse,
)
from .paper_trading import list_paper_account_templates, read_paper_trading_ledger, run_paper_trading
from .signal_quality import run_signal_quality
from .sector_dashboard import build_sector_dashboard_payload
from .single_stock import run_single_stock_backtest


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Signal-Based Swing Portfolio Backtest")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/single", response_class=HTMLResponse)
def single_stock_page() -> str:
    return (STATIC_DIR / "single.html").read_text(encoding="utf-8")


@app.get("/daily", response_class=HTMLResponse)
def daily_plan_page() -> str:
    return (STATIC_DIR / "daily.html").read_text(encoding="utf-8")


@app.get("/paper", response_class=HTMLResponse)
def paper_trading_page() -> str:
    return (STATIC_DIR / "paper.html").read_text(encoding="utf-8")


@app.get("/sector", response_class=HTMLResponse)
def sector_research_page() -> str:
    return (STATIC_DIR / "sector.html").read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/run-backtest", response_model=BacktestResponse)
def run_backtest_api(req: BacktestRequest):
    try:
        result = run_portfolio_backtest(req)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@app.post("/api/run-signal-quality", response_model=SignalQualityResponse)
def run_signal_quality_api(req: SignalQualityRequest):
    try:
        result = run_signal_quality(req)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@app.post("/api/run-single-stock", response_model=SingleStockBacktestResponse)
def run_single_stock_api(req: SingleStockBacktestRequest):
    try:
        return run_single_stock_backtest(req)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/daily-plan", response_model=DailyPlanResponse)
def daily_plan_api(req: DailyPlanRequest):
    try:
        return build_daily_plan(req)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/paper/templates", response_model=PaperTemplateResponse)
def paper_templates_api(config_dir: str = "configs/paper_accounts"):
    try:
        return {"templates": list_paper_account_templates(config_dir)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/paper/run", response_model=PaperTradingRunResponse)
def paper_run_api(req: PaperTradingRunRequest):
    try:
        return run_paper_trading(req)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/paper/ledger", response_model=PaperTradingRunResponse)
def paper_ledger_api(config_path: str = "", config_dir: str = "configs/paper_accounts", account_id: str = ""):
    try:
        return read_paper_trading_ledger(
            PaperTradingRunRequest(
                config_path=config_path,
                config_dir=config_dir,
                account_id=account_id,
                action="mark",
            )
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/sector/overview")
def sector_overview_api(processed_dir: str = "sector_research/data/processed", report_dir: str = "sector_research/reports"):
    try:
        return build_sector_dashboard_payload(base_dir=BASE_DIR, processed_dir=processed_dir, report_dir=report_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/run-backtest-export")
def export_backtest_api(req: BacktestRequest):
    try:
        result = run_portfolio_backtest(req)
        payload = export_backtest_zip(result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    headers = {"Content-Disposition": 'attachment; filename="swing_backtest_export.zip"'}
    return Response(content=payload, media_type="application/zip", headers=headers)
