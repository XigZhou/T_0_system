#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/T_0_system}"
VENV_ACTIVATE="${VENV_ACTIVATE:-/home/ubuntu/TencentCloud/myenv/bin/activate}"
CONFIG_DIR="${CONFIG_DIR:-configs/paper_accounts}"
LOG_DIR="${LOG_DIR:-${PROJECT_DIR}/logs/paper_trading_cron}"
LOCK_ROOT="${LOCK_ROOT:-/tmp}"

ACTION="${1:-}"
if [[ -z "${ACTION}" ]]; then
  echo "usage: $0 execute|generate|mark|after-close|--check-only [YYYYMMDD]" >&2
  exit 2
fi

CHECK_ONLY=0
if [[ "${ACTION}" == "--check-only" ]]; then
  CHECK_ONLY=1
  ACTION="${2:-after-close}"
  RUN_DATE="${3:-$(TZ=Asia/Shanghai date +%Y%m%d)}"
else
  RUN_DATE="${2:-$(TZ=Asia/Shanghai date +%Y%m%d)}"
fi

case "${ACTION}" in
  execute|generate|mark|after-close) ;;
  *)
    echo "unknown action: ${ACTION}; allowed: execute|generate|mark|after-close" >&2
    exit 2
    ;;
esac

mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/${RUN_DATE}_${ACTION}.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "[$(date '+%F %T')] start paper trading cron: action=${ACTION}, date=${RUN_DATE}"

LOCK_DIR="${LOCK_ROOT}/t0_paper_trading_${ACTION}.lock"
if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  echo "[$(date '+%F %T')] ${ACTION} task is already running, skip."
  exit 0
fi
trap 'rmdir "${LOCK_DIR}" 2>/dev/null || true' EXIT

cd "${PROJECT_DIR}"
if [[ ! -f "${VENV_ACTIVATE}" ]]; then
  echo "virtualenv activate file not found: ${VENV_ACTIVATE}"
  exit 1
fi
source "${VENV_ACTIVATE}"

IS_TRADE_DAY="$(
  python - "${RUN_DATE}" <<'PY'
from pathlib import Path
import sys

import pandas as pd

from overnight_bt.utils import load_env

run_date = sys.argv[1]
is_open = None

try:
    import tushare as ts

    token = load_env(Path(".env")).get("TUSHARE_TOKEN", "").strip()
    if token:
        pro = ts.pro_api(token)
        cal = pro.trade_cal(exchange="", start_date=run_date, end_date=run_date, fields="cal_date,is_open")
        if cal is not None and not cal.empty:
            is_open = str(cal.iloc[0].get("is_open", "")).strip() == "1"
except Exception as exc:
    print(f"Tushare trade calendar check failed, fallback to local calendar: {exc}", file=sys.stderr)

if is_open is None:
    calendar_path = Path("data_bundle/trade_calendar.csv")
    if calendar_path.exists():
        cal = pd.read_csv(calendar_path, dtype=str, encoding="utf-8-sig")
        date_col = "trade_date" if "trade_date" in cal.columns else "cal_date"
        rows = cal[cal[date_col].astype(str) == run_date]
        if not rows.empty:
            is_open = str(rows.iloc[0].get("is_open", "1")).strip() == "1"

print("1" if is_open else "0")
PY
)"

if [[ "${IS_TRADE_DAY}" != "1" ]]; then
  echo "[$(date '+%F %T')] ${RUN_DATE} is not an A-share trading day, skip paper trading task."
  exit 0
fi

echo "[$(date '+%F %T')] ${RUN_DATE} is an A-share trading day."

ensure_stock_pool_latest() {
  python - "${RUN_DATE}" "${CONFIG_DIR}" <<'PY'
from pathlib import Path
import sys

from overnight_bt.paper_trading import _stock_pool_db_path, list_paper_account_templates
from overnight_bt.stock_pool_templates import DEFAULT_USERNAME, _connect, init_stock_pool_db

run_date = sys.argv[1]
config_dir = sys.argv[2]
templates = list_paper_account_templates(config_dir)
if not templates:
    raise SystemExit(f"no paper account templates found in {config_dir}")

errors = [item for item in templates if item.get("error")]
if errors:
    lines = [f"{item.get('account_id', '')}: {item.get('error', '')}" for item in errors]
    raise SystemExit("paper account template read errors; fix them in /paper/templates first:\n" + "\n".join(lines))

checks = {}
for item in templates:
    username = str(item.get("stock_pool_username") or DEFAULT_USERNAME).strip() or DEFAULT_USERNAME
    template_name = str(item.get("stock_pool_template_name") or "").strip()
    if not template_name:
        raise SystemExit(f"{item.get('account_id', '')} missing stock_pool_template_name")
    db_path = _stock_pool_db_path(str(item.get("stock_pool_db_path") or ""))
    account_label = f"{item.get('account_name', item.get('account_id', ''))}({item.get('account_id', '')})"
    checks.setdefault((str(db_path), username, template_name), []).append(account_label)

problems = []
for (db_path_text, username, template_name), accounts in sorted(checks.items()):
    db_path = Path(db_path_text)
    init_stock_pool_db(db_path)
    with _connect(db_path) as conn:
        summary = conn.execute(
            """
            SELECT
                COUNT(*) AS stock_count,
                SUM(CASE WHEN latest_date IS NULL THEN 1 ELSE 0 END) AS missing_count,
                MIN(latest_date) AS min_latest_date,
                MAX(latest_date) AS max_latest_date
            FROM (
                SELECT s.symbol, MAX(f.trade_date) AS latest_date
                FROM stock_pool_template_stocks s
                LEFT JOIN stock_daily_features f ON f.symbol=s.symbol
                WHERE s.username=? AND s.template_name=?
                GROUP BY s.symbol
            )
            """,
            (username, template_name),
        ).fetchone()
        stale_rows = conn.execute(
            """
            SELECT s.symbol, COALESCE(s.stock_name, '') AS stock_name, MAX(f.trade_date) AS latest_date
            FROM stock_pool_template_stocks s
            LEFT JOIN stock_daily_features f ON f.symbol=s.symbol
            WHERE s.username=? AND s.template_name=?
            GROUP BY s.symbol
            HAVING COALESCE(MAX(f.trade_date), '') < ?
            ORDER BY COALESCE(MAX(f.trade_date), ''), s.symbol
            LIMIT 20
            """,
            (username, template_name, run_date),
        ).fetchall()

    stock_count = int(summary["stock_count"] or 0)
    missing_count = int(summary["missing_count"] or 0)
    min_latest = str(summary["min_latest_date"] or "")
    max_latest = str(summary["max_latest_date"] or "")
    print(
        "stock pool check: "
        f"{username}/{template_name}, accounts={','.join(accounts)}, stock_count={stock_count}, "
        f"missing_count={missing_count}, min_latest={min_latest or 'NA'}, max_latest={max_latest or 'NA'}, db={db_path}"
    )
    if stock_count <= 0:
        problems.append(f"{username}/{template_name}: empty template")
    elif stale_rows:
        examples = ", ".join(
            f"{row['symbol']}({row['stock_name'] or '-'}:{row['latest_date'] or 'NA'})" for row in stale_rows
        )
        problems.append(f"{username}/{template_name}: sample stale symbols not updated to {run_date}: {examples}")

if problems:
    raise SystemExit("stock pool SQLite is not fully updated to target trading day; skip paper after-close task:\n" + "\n".join(problems))
PY
}

run_all_accounts() {
  local action_name="$1"
  echo "[$(date '+%F %T')] run all paper accounts: ${action_name}"
  python scripts/run_paper_trading.py --config-dir "${CONFIG_DIR}" --all --action "${action_name}" --date "${RUN_DATE}"
}

if [[ "${CHECK_ONLY}" == "1" ]]; then
  case "${ACTION}" in
    generate|mark|after-close)
      ensure_stock_pool_latest
      ;;
    execute)
      echo "[$(date '+%F %T')] execute check-only only validates trading day; execution prices are read at order date."
      ;;
  esac
  echo "[$(date '+%F %T')] check-only passed, no paper trading action executed."
  exit 0
fi

case "${ACTION}" in
  execute)
    run_all_accounts execute
    ;;
  generate)
    ensure_stock_pool_latest
    run_all_accounts generate
    ;;
  mark)
    ensure_stock_pool_latest
    run_all_accounts mark
    ;;
  after-close)
    ensure_stock_pool_latest
    run_all_accounts mark
    run_all_accounts generate
    ;;
esac

SUCCESS_FILE="${LOG_DIR}/latest_${ACTION}_success.txt"
{
  echo "success_date=${RUN_DATE}"
  echo "action=${ACTION}"
  echo "finished_at=$(date '+%F %T')"
  echo "log_file=${LOG_FILE}"
} > "${SUCCESS_FILE}"

echo "[$(date '+%F %T')] paper trading cron finished: action=${ACTION}, date=${RUN_DATE}"
