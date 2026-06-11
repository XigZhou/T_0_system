from __future__ import annotations

import os
import logging
from datetime import datetime
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send

from . import auth
from .backtest import export_backtest_table_excel, export_backtest_zip, run_portfolio_backtest
from .daily_plan import build_daily_plan
from .main_universe import (
    DEFAULT_DB_PATH as MAIN_UNIVERSE_DB_PATH,
    MainUniverseSaveRequest,
    list_main_universe,
    resolve_stock_names,
    save_main_universe,
)
from .market_data_view import check_market_stock, list_market_factors, list_market_stocks
from .models import (
    UserStatusUpdateRequest,
    UserPasswordResetRequest,
    UserListResponse,
    AuthRegisterRequest,
    AuthMeResponse,
    AuthLoginRequest,
    AdminStockDataTaskRequest,
    AdminOverviewResponse,
    MainUniverseResolveRequest,
    MainUniverseSaveApiRequest,
    SchedulerRetryRequest,
    SchedulerRetryResponse,
    SchedulerRunsResponse,
    BacktestRequest,
    BacktestResponse,
    DailyPlanRequest,
    DailyPlanResponse,
    PaperTemplateSaveRequest,
    PaperTemplateResponse,
    PaperTradingRunRequest,
    PaperTradingRunResponse,
    SignalQualityRequest,
    SignalQualityResponse,
    SingleStockBacktestRequest,
    SingleStockBacktestResponse,
    StockPoolRefreshRequest,
    StockPoolTemplateResponse,
    StockPoolTemplateSaveRequest,
    StockPoolValidateRequest,
)
from .paper_trading import (
    delete_paper_account_template,
    list_paper_account_templates,
    read_paper_account_template,
    read_paper_trading_ledger,
    run_paper_trading,
    save_paper_account_template,
)
from .signal_quality import run_signal_quality
from .sector_dashboard import build_sector_dashboard_payload
from .single_stock import run_single_stock_backtest
from .scheduler import DEFAULT_DB_PATH as SCHEDULER_DB_PATH, create_retry_run, get_run, init_scheduler_db, list_runs
from .stock_pool_feature_store import (
    StockPoolFeatureUpdateConfig,
    list_stock_pool_update_jobs,
    read_stock_pool_update_job,
    run_stock_daily_feature_computation,
    run_stock_daily_raw_collection,
    run_stock_pool_feature_update,
)
from .stock_pool_templates import (
    ADMIN_USERNAME,
    DEFAULT_USERNAME,
    delete_stock_pool_template,
    ensure_default_stock_pool_templates,
    list_stock_pool_templates,
    read_stock_pool_template,
    save_stock_pool_template,
    seed_default_stock_pool_templates,
    validate_stock_pool_symbols,
)
from .utils import normalize_date_text


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
logger = logging.getLogger(__name__)

MARKET_DATA_DB_ENV = "T0_MARKET_DATA_DB_PATH"


def _market_data_db_path() -> Path:
    configured = os.environ.get(MARKET_DATA_DB_ENV, "").strip()
    return Path(configured).expanduser() if configured else MAIN_UNIVERSE_DB_PATH

PROTECTED_STATIC_PATHS = {
    "console/index.html": "user",
}


class AuthenticatedStaticFiles(StaticFiles):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request_path = str(scope.get("path", "")).split("?", 1)[0]
        static_path = request_path.removeprefix("/static/").lstrip("/")
        required_role = PROTECTED_STATIC_PATHS.get(static_path)
        if required_role:
            cookie_header = ""
            for key, value in scope.get("headers", []):
                if key.lower() == b"cookie":
                    cookie_header = value.decode("latin-1")
                    break
            session_id = None
            for part in cookie_header.split(";"):
                name, _, value = part.strip().partition("=")
                if name == auth.SESSION_COOKIE_NAME:
                    session_id = value
                    break
            user = auth.get_user_by_session(session_id)
            if user is None:
                await auth.redirect_to_login_response()(scope, receive, send)
                return
            if required_role == "admin" and user.get("role") != "admin":
                response = JSONResponse({"detail": "admin only"}, status_code=403)
                await response(scope, receive, send)
                return
        await super().__call__(scope, receive, send)


app = FastAPI(title="Signal-Based Swing Portfolio Backtest")
app.mount("/static", AuthenticatedStaticFiles(directory=STATIC_DIR), name="static")


def _html_page(filename: str) -> str:
    return (STATIC_DIR / filename).read_text(encoding="utf-8")


def _console_page() -> str:
    return _html_page("console/index.html")


def _direct_user(username: str = DEFAULT_USERNAME, role: str = "admin") -> dict:
    clean = str(username or DEFAULT_USERNAME).strip() or DEFAULT_USERNAME
    return {"username": clean, "role": role, "is_admin": role == "admin", "is_active": True}


def _resolve_current_user(current_user) -> dict | None:
    if isinstance(current_user, dict):
        return current_user
    if current_user is None:
        return None
    return _direct_user()


def _current_username(current_user=None, fallback: str = DEFAULT_USERNAME) -> str:
    if isinstance(current_user, dict):
        return str(current_user.get("username") or DEFAULT_USERNAME).strip() or DEFAULT_USERNAME
    return str(fallback or DEFAULT_USERNAME).strip() or DEFAULT_USERNAME


def _force_request_user(req, current_user=None, *fields: str):
    if not isinstance(current_user, dict):
        return req
    username = _current_username(current_user)
    for field in fields:
        if hasattr(req, field):
            setattr(req, field, username)
    return req


def _require_page_user(current_user):
    user = _resolve_current_user(current_user)
    if user is None:
        return auth.redirect_to_login_response()
    return None


def _require_page_admin(current_user):
    redirect = _require_page_user(current_user)
    if redirect is not None:
        return redirect
    user = _resolve_current_user(current_user)
    if user and user.get("role") == "admin":
        return None
    raise HTTPException(status_code=403, detail="只有 admin 用户可以使用该页面")


def _require_admin_user(current_user=None, fallback_username: str = DEFAULT_USERNAME) -> str:
    user = _resolve_current_user(current_user)
    if isinstance(current_user, dict):
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="只有 admin 用户可以使用该功能")
        return _current_username(current_user)
    return _require_stock_pool_admin(fallback_username)


def _auth_response(user: dict, session_id: str | None = None) -> JSONResponse:
    response = JSONResponse({"authenticated": True, "user": user})
    if session_id:
        response.set_cookie(
            key=auth.SESSION_COOKIE_NAME,
            value=session_id,
            httponly=True,
            samesite="lax",
            max_age=auth.SESSION_DAYS * 24 * 60 * 60,
        )
    return response


def _require_stock_pool_admin(username: str) -> str:
    clean_username = str(username or DEFAULT_USERNAME).strip() or DEFAULT_USERNAME
    if clean_username != ADMIN_USERNAME:
        raise HTTPException(status_code=403, detail="只有 admin 用户可以执行股票池数据刷新和查看更新任务")
    return clean_username

def _ensure_default_stock_pool_templates_best_effort() -> None:
    try:
        ensure_default_stock_pool_templates()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Default stock pool template initialization skipped: %s", exc, exc_info=True)


@app.get("/login", response_class=HTMLResponse)
def login_page() -> str:
    return _html_page("login.html")


@app.get("/register", response_class=HTMLResponse)
def register_page() -> str:
    return _html_page("register.html")


@app.get("/", response_class=HTMLResponse)
@app.get("/backtests/portfolio", response_class=HTMLResponse)
def portfolio_console_page(current_user: dict | None = Depends(auth.optional_current_user)):
    redirect = _require_page_user(current_user)
    if redirect is not None:
        return redirect
    return _console_page()


@app.get("/single", response_class=HTMLResponse)
@app.get("/backtests/single-stock", response_class=HTMLResponse)
def single_stock_page(current_user: dict | None = Depends(auth.optional_current_user)):
    redirect = _require_page_user(current_user)
    if redirect is not None:
        return redirect
    return _console_page()


@app.get("/daily", response_class=HTMLResponse)
@app.get("/trading/daily-plan", response_class=HTMLResponse)
def daily_plan_page(current_user: dict | None = Depends(auth.optional_current_user)):
    redirect = _require_page_user(current_user)
    if redirect is not None:
        return redirect
    return _console_page()


@app.get("/paper", response_class=HTMLResponse)
@app.get("/trading/paper", response_class=HTMLResponse)
def paper_trading_page(current_user: dict | None = Depends(auth.optional_current_user)):
    redirect = _require_page_user(current_user)
    if redirect is not None:
        return redirect
    return _console_page()


@app.get("/paper/templates", response_class=HTMLResponse)
@app.get("/portfolio/paper-templates", response_class=HTMLResponse)
def paper_template_manager_page(current_user: dict | None = Depends(auth.optional_current_user)):
    redirect = _require_page_user(current_user)
    if redirect is not None:
        return redirect
    return _console_page()


@app.get("/stock-pools", response_class=HTMLResponse)
@app.get("/portfolio/stock-pools", response_class=HTMLResponse)
def stock_pool_template_page(current_user: dict | None = Depends(auth.optional_current_user)):
    redirect = _require_page_user(current_user)
    if redirect is not None:
        return redirect
    _ensure_default_stock_pool_templates_best_effort()
    return _console_page()


@app.get("/admin", response_class=HTMLResponse)
@app.get("/system/admin", response_class=HTMLResponse)
def admin_page(current_user: dict | None = Depends(auth.optional_current_user)):
    redirect = _require_page_admin(current_user)
    if redirect is not None:
        return redirect
    _ensure_default_stock_pool_templates_best_effort()
    return _console_page()


@app.get("/users", response_class=HTMLResponse)
@app.get("/system/users", response_class=HTMLResponse)
def users_page(current_user: dict | None = Depends(auth.optional_current_user)):
    redirect = _require_page_admin(current_user)
    if redirect is not None:
        return redirect
    return _console_page()


@app.get("/sector", response_class=HTMLResponse)
@app.get("/research/sectors", response_class=HTMLResponse)
def sector_research_page(current_user: dict | None = Depends(auth.optional_current_user)):
    redirect = _require_page_user(current_user)
    if redirect is not None:
        return redirect
    return _console_page()


@app.get("/market-data", response_class=HTMLResponse)
@app.get("/market-data/factors", response_class=HTMLResponse)
@app.get("/market-data/stocks", response_class=HTMLResponse)
@app.get("/system/health", response_class=HTMLResponse)
def readonly_console_page(current_user: dict | None = Depends(auth.optional_current_user)):
    redirect = _require_page_user(current_user)
    if redirect is not None:
        return redirect
    return _console_page()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/auth/me", response_model=AuthMeResponse)
def auth_me_api(current_user: dict | None = Depends(auth.optional_current_user)):
    user = _resolve_current_user(current_user)
    return {"authenticated": user is not None, "user": user}


@app.post("/api/auth/register")
def auth_register_api(req: AuthRegisterRequest, request: Request):
    try:
        user = auth.register_user(req.username, req.password, display_name=req.display_name)
        session_id = auth.create_session(user["username"], user_agent=request.headers.get("user-agent", ""))
        return _auth_response(user, session_id=session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/login")
def auth_login_api(req: AuthLoginRequest, request: Request):
    user = auth.authenticate_user(req.username, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    session_id = auth.create_session(user["username"], user_agent=request.headers.get("user-agent", ""))
    return _auth_response(user, session_id=session_id)


@app.post("/api/auth/logout")
def auth_logout_api(t0_session: str | None = Cookie(default=None, alias=auth.SESSION_COOKIE_NAME)):
    auth.revoke_session(t0_session)
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.SESSION_COOKIE_NAME)
    return response


@app.get("/api/users", response_model=UserListResponse)
def users_list_api(current_user: dict = Depends(auth.require_user)):
    _require_admin_user(current_user)
    return {"users": auth.list_users()}


@app.post("/api/users/{username}/status")
def user_status_api(username: str, req: UserStatusUpdateRequest, current_user: dict = Depends(auth.require_user)):
    _require_admin_user(current_user)
    try:
        return {"user": auth.update_user_status(username, req.is_active)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/users/{username}/password")
def user_password_reset_api(username: str, req: UserPasswordResetRequest, current_user: dict = Depends(auth.require_user)):
    _require_admin_user(current_user)
    try:
        user = auth.reset_user_password(username, req.new_password)
        return {"user": user, "message": "密码已重置，用户需要重新登录。"}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/run-backtest", response_model=BacktestResponse)
def run_backtest_api(req: BacktestRequest, current_user: dict = Depends(auth.require_user)):
    req = _force_request_user(req, current_user, "stock_pool_username")
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
def run_signal_quality_api(req: SignalQualityRequest, current_user: dict = Depends(auth.require_user)):
    req = _force_request_user(req, current_user, "stock_pool_username")
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
def run_single_stock_api(req: SingleStockBacktestRequest, current_user: dict = Depends(auth.require_user)):
    req = _force_request_user(req, current_user, "stock_pool_username")
    try:
        return run_single_stock_backtest(req)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/daily-plan", response_model=DailyPlanResponse)
def daily_plan_api(req: DailyPlanRequest, current_user: dict = Depends(auth.require_user)):
    req = _force_request_user(req, current_user, "stock_pool_username")
    try:
        return build_daily_plan(req)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/paper/templates", response_model=PaperTemplateResponse)
def paper_templates_api(config_dir: str = "configs/paper_accounts", username: str = DEFAULT_USERNAME, current_user: dict = Depends(auth.require_user)):
    username = _current_username(current_user, username)
    try:
        return {"templates": list_paper_account_templates(config_dir=config_dir, username=username)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/paper/template")
def paper_template_api(config_path: str = "", config_dir: str = "configs/paper_accounts", username: str = DEFAULT_USERNAME, account_id: str = "", current_user: dict = Depends(auth.require_user)):
    username = _current_username(current_user, username)
    try:
        return read_paper_account_template(config_path=config_path, config_dir=config_dir, username=username, account_id=account_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/paper/template")
def paper_template_save_api(req: PaperTemplateSaveRequest, current_user: dict = Depends(auth.require_user)):
    req = _force_request_user(req, current_user, "username", "stock_pool_username")
    try:
        return save_paper_account_template(req)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/api/paper/template")
def paper_template_delete_api(config_path: str = "", config_dir: str = "configs/paper_accounts", username: str = DEFAULT_USERNAME, account_id: str = "", current_user: dict = Depends(auth.require_user)):
    username = _current_username(current_user, username)
    try:
        return delete_paper_account_template(config_path=config_path, config_dir=config_dir, username=username, account_id=account_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/market-data/factors")
def market_data_factors_api(current_user: dict = Depends(auth.require_user)):
    try:
        return list_market_factors(db_path=_market_data_db_path())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/market-data/stocks")
def market_data_stocks_api(limit: int = 500, current_user: dict = Depends(auth.require_user)):
    try:
        return list_market_stocks(limit=limit, db_path=_market_data_db_path())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/market-data/stocks/check")
def market_data_stock_check_api(stock_name: str, current_user: dict = Depends(auth.require_user)):
    try:
        return check_market_stock(stock_name, db_path=_market_data_db_path())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/stock-pools/templates", response_model=StockPoolTemplateResponse)
def stock_pool_templates_api(username: str = DEFAULT_USERNAME, current_user: dict = Depends(auth.require_user)):
    username = _current_username(current_user, username)
    try:
        ensure_default_stock_pool_templates(username=username)
        return {"templates": list_stock_pool_templates(username=username)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/stock-pools/template")
def stock_pool_template_api(template_name: str, username: str = DEFAULT_USERNAME, current_user: dict = Depends(auth.require_user)):
    username = _current_username(current_user, username)
    try:
        ensure_default_stock_pool_templates(username=username)
        return read_stock_pool_template(template_name=template_name, username=username)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/stock-pools/template")
def stock_pool_template_save_api(req: StockPoolTemplateSaveRequest, current_user: dict = Depends(auth.require_user)):
    req = _force_request_user(req, current_user, "username")
    try:
        return save_stock_pool_template(req, main_universe_db_path=MAIN_UNIVERSE_DB_PATH)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/api/stock-pools/template")
def stock_pool_template_delete_api(template_name: str, username: str = DEFAULT_USERNAME, current_user: dict = Depends(auth.require_user)):
    username = _current_username(current_user, username)
    try:
        return delete_stock_pool_template(template_name=template_name, username=username)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/stock-pools/template/validate")
def stock_pool_template_validate_api(req: StockPoolValidateRequest, current_user: dict = Depends(auth.require_user)):
    try:
        return validate_stock_pool_symbols(req.stock_text, main_universe_db_path=MAIN_UNIVERSE_DB_PATH)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/stock-pools/templates/seed")
def stock_pool_template_seed_api(username: str = DEFAULT_USERNAME, current_user: dict = Depends(auth.require_user)):
    username = _current_username(current_user, username)
    try:
        return seed_default_stock_pool_templates(username=username)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/stock-pools/template/refresh")
def stock_pool_template_refresh_api(req: StockPoolRefreshRequest, current_user: dict = Depends(auth.require_user)):
    try:
        operator = _require_admin_user(current_user, req.username or DEFAULT_USERNAME)
        req.username = operator
        job_type = "initial_load" if req.source == "all" else "manual_refresh"
        config = StockPoolFeatureUpdateConfig(
            source=req.source,
            job_type=job_type,
            username=operator,
            template_name=req.template_name,
            stock_text=req.stock_text,
            start_date=req.start_date,
            end_date=req.end_date,
            force_full_rebuild=req.force_full_rebuild,
            max_symbols=req.max_symbols,
            sleep_seconds=req.sleep_seconds,
            batch_size=req.batch_size,
            batch_index=req.batch_index,
            offset=req.offset,
            resume_after_symbol=req.resume_after_symbol,
            retry_attempts=req.retry_attempts,
            retry_sleep_seconds=req.retry_sleep_seconds,
            only_missing=req.only_missing,
        )
        result = run_stock_pool_feature_update(config)
        if isinstance(result, dict):
            result = {**result, "legacy": True}
        return result
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc



CORE_TASK_NAMES = ("safe_retry", "core_after_close_generate", "daily_sync", "feature_build")


def _scheduler_overview_payload(db_path: str | Path | None = None) -> dict:
    runs = list_runs(limit=20, db_path=db_path)
    latest = runs[0] if runs else None
    status_counts: dict[str, int] = {}
    for row in runs:
        status = str(row.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "db_path": str(db_path or SCHEDULER_DB_PATH),
        "run_count": len(runs),
        "latest_run": latest,
        "status_counts": status_counts,
        "safe_retry_jobs": ["daily_sync", "feature_build", "core_after_close_generate"],
    }


def _core_tasks_payload(db_path: str | Path | None = None) -> dict:
    runs = list_runs(limit=200, db_path=db_path)
    payload: dict[str, dict] = {
        name: {"run_count": 0, "status_counts": {}, "latest_run": None}
        for name in CORE_TASK_NAMES
    }
    for row in runs:
        job_name = str(row.get("job_name") or "")
        task_name = "safe_retry" if row.get("retry_of_run_id") or row.get("status") == "retry_pending" else job_name
        if task_name not in payload:
            continue
        item = payload[task_name]
        item["run_count"] += 1
        status = str(row.get("status") or "unknown")
        item["status_counts"][status] = item["status_counts"].get(status, 0) + 1
        if item["latest_run"] is None:
            item["latest_run"] = row
    return payload


@app.get("/api/admin/overview", response_model=AdminOverviewResponse)
def admin_overview_api(current_user: dict = Depends(auth.require_user)):
    try:
        _require_admin_user(current_user)
        init_scheduler_db(SCHEDULER_DB_PATH)
        return {
            "scheduler": _scheduler_overview_payload(SCHEDULER_DB_PATH),
            "core_tasks": _core_tasks_payload(SCHEDULER_DB_PATH),
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/main-universe")
def admin_main_universe_api(include_inactive: bool = False, current_user: dict = Depends(auth.require_user)):
    try:
        _require_admin_user(current_user)
        rows = list_main_universe(db_path=MAIN_UNIVERSE_DB_PATH, include_inactive=include_inactive)
        return {
            "rows": rows,
            "count": len(rows),
            "include_inactive": include_inactive,
            "message": "已读取主股票池；本次读取未写入数据。",
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/main-universe/resolve")
def admin_main_universe_resolve_api(req: MainUniverseResolveRequest, current_user: dict = Depends(auth.require_user)):
    try:
        _require_admin_user(current_user)
        result = resolve_stock_names(req.names, db_path=MAIN_UNIVERSE_DB_PATH)
        return {**result, "written": False, "message": "仅解析股票名称，未写入主股票池数据。"}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/main-universe/save")
def admin_main_universe_save_api(req: MainUniverseSaveApiRequest, current_user: dict = Depends(auth.require_user)):
    try:
        _require_admin_user(current_user)
        save_req = MainUniverseSaveRequest(mode=req.mode, rows=req.rows, source=req.source)
        result = save_main_universe(save_req, db_path=MAIN_UNIVERSE_DB_PATH)
        saved_count = int(result.get("saved_count") or 0)
        return {
            **result,
            "written": saved_count > 0,
            "message": f"已写入主股票池 {saved_count} 只股票。" if saved_count else "没有写入主股票池；请检查未解析、重复或歧义输入。",
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/scheduler/runs", response_model=SchedulerRunsResponse)
def admin_scheduler_runs_api(limit: int = 50, current_user: dict = Depends(auth.require_user)):
    try:
        _require_admin_user(current_user)
        return {"runs": list_runs(limit=limit, db_path=SCHEDULER_DB_PATH)}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/scheduler/runs/{run_id}/retry", response_model=SchedulerRetryResponse)
def admin_scheduler_retry_run_api(
    run_id: str,
    req: SchedulerRetryRequest | None = None,
    current_user: dict = Depends(auth.require_user),
):
    try:
        _require_admin_user(current_user)
        original = get_run(run_id, db_path=SCHEDULER_DB_PATH)
        if str(original.get("status") or "") != "failed":
            raise ValueError("只有失败的任务运行记录可以登记安全重跑")
        retry_run = create_retry_run(run_id, db_path=SCHEDULER_DB_PATH)
        return {
            "original_run": original,
            "retry_run": retry_run,
            "message": "已登记安全重跑请求；调度执行由后续核心流水线处理，本接口不直接执行 shell 命令。",
        }
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

def _today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")


def _normalize_admin_stock_task_dates(req: AdminStockDataTaskRequest, mode: str = "range") -> tuple[str, str]:
    if mode == "today":
        today = _today_yyyymmdd()
        return today, today
    start_date = normalize_date_text(req.start_date)
    end_date = normalize_date_text(req.end_date)
    if not start_date or not end_date:
        raise ValueError("开始日期和结束日期不能为空")
    if start_date > end_date:
        raise ValueError("开始日期不能晚于结束日期")
    return start_date, end_date


def _run_admin_stock_data_task(
    req: AdminStockDataTaskRequest,
    job_type: str,
    current_user=None,
    date_mode: str = "range",
    runner=run_stock_daily_feature_computation,
):
    operator = _require_admin_user(current_user, req.username or DEFAULT_USERNAME)
    start_date, end_date = _normalize_admin_stock_task_dates(req, mode=date_mode)
    config = StockPoolFeatureUpdateConfig(
        source="all",
        job_type=job_type,
        username=operator,
        start_date=start_date,
        end_date=end_date,
        market_db_path=MAIN_UNIVERSE_DB_PATH,
        force_full_rebuild=True,
        max_symbols=req.max_symbols,
        sleep_seconds=req.sleep_seconds,
        retry_attempts=req.retry_attempts,
        retry_sleep_seconds=req.retry_sleep_seconds,
        only_missing=False,
    )
    return runner(config)


@app.post("/api/admin/stock-data/daily")
def admin_stock_daily_collect_api(req: AdminStockDataTaskRequest, current_user: dict = Depends(auth.require_user)):
    try:
        return _run_admin_stock_data_task(req, job_type="admin_daily_collect", current_user=current_user, runner=run_stock_daily_raw_collection)
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/stock-data/indicators")
def admin_stock_indicator_compute_api(req: AdminStockDataTaskRequest, current_user: dict = Depends(auth.require_user)):
    try:
        return _run_admin_stock_data_task(req, job_type="admin_indicator_compute", current_user=current_user, runner=run_stock_daily_feature_computation)
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/stock-data/daily/today")
def admin_stock_daily_today_api(req: AdminStockDataTaskRequest, current_user: dict = Depends(auth.require_user)):
    try:
        return _run_admin_stock_data_task(
            req,
            job_type="admin_daily_collect_today",
            current_user=current_user,
            date_mode="today",
            runner=run_stock_daily_raw_collection,
        )
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/stock-data/indicators/today")
def admin_stock_indicator_today_api(req: AdminStockDataTaskRequest, current_user: dict = Depends(auth.require_user)):
    try:
        return _run_admin_stock_data_task(
            req,
            job_type="admin_indicator_compute_today",
            current_user=current_user,
            date_mode="today",
            runner=run_stock_daily_feature_computation,
        )
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/stock-data/daily/range")
def admin_stock_daily_range_api(req: AdminStockDataTaskRequest, current_user: dict = Depends(auth.require_user)):
    try:
        return _run_admin_stock_data_task(
            req,
            job_type="admin_daily_collect_range",
            current_user=current_user,
            date_mode="range",
            runner=run_stock_daily_raw_collection,
        )
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/stock-data/indicators/range")
def admin_stock_indicator_range_api(req: AdminStockDataTaskRequest, current_user: dict = Depends(auth.require_user)):
    try:
        return _run_admin_stock_data_task(
            req,
            job_type="admin_indicator_compute_range",
            current_user=current_user,
            date_mode="range",
            runner=run_stock_daily_feature_computation,
        )
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/stock-pools/jobs")
def stock_pool_update_jobs_api(limit: int = 50, username: str = DEFAULT_USERNAME, current_user: dict = Depends(auth.require_user)):
    try:
        _require_admin_user(current_user, username)
        return {"jobs": list_stock_pool_update_jobs(limit=limit)}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/stock-pools/jobs/{job_id}")
def stock_pool_update_job_api(job_id: str, username: str = DEFAULT_USERNAME, current_user: dict = Depends(auth.require_user)):
    try:
        _require_admin_user(current_user, username)
        return read_stock_pool_update_job(job_id=job_id)
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/paper/run", response_model=PaperTradingRunResponse)
def paper_run_api(req: PaperTradingRunRequest, current_user: dict = Depends(auth.require_user)):
    req = _force_request_user(req, current_user, "username")
    try:
        return run_paper_trading(req)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/paper/ledger", response_model=PaperTradingRunResponse)
def paper_ledger_api(config_path: str = "", config_dir: str = "configs/paper_accounts", account_id: str = "", username: str = DEFAULT_USERNAME, current_user: dict = Depends(auth.require_user)):
    username = _current_username(current_user, username)
    try:
        return read_paper_trading_ledger(
            PaperTradingRunRequest(
                config_path=config_path,
                config_dir=config_dir,
                account_id=account_id,
                username=username,
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
def sector_overview_api(
    source: str = "sqlite",
    processed_dir: str = "sector_research/data/processed",
    report_dir: str = "sector_research/reports",
    market_context_path: str = "data_bundle/market_context.csv",
    market_db_path: str = "",
    current_user: dict = Depends(auth.require_user),
):
    try:
        return build_sector_dashboard_payload(
            base_dir=BASE_DIR,
            source=source,
            processed_dir=processed_dir,
            report_dir=report_dir,
            market_context_path=market_context_path,
            db_path=market_db_path or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/run-backtest-table-export")
def export_backtest_table_api(req: BacktestRequest, mode: str = "account", table: str = "trade_rows", current_user: dict = Depends(auth.require_user)):
    req = _force_request_user(req, current_user, "stock_pool_username")
    try:
        if mode == "signal_quality":
            result = run_signal_quality(SignalQualityRequest(**req.model_dump()))
        else:
            result = run_portfolio_backtest(req)
        payload = export_backtest_table_excel(result, table)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    filename = "daily_picks.xlsx" if table == "pick_rows" else "trade_flows.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@app.post("/api/run-backtest-export")
def export_backtest_api(req: BacktestRequest, current_user: dict = Depends(auth.require_user)):
    req = _force_request_user(req, current_user, "stock_pool_username")
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
