#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/T_0_system}"
VENV_ACTIVATE="${VENV_ACTIVATE:-/home/ubuntu/TencentCloud/myenv/bin/activate}"
CONFIG_DIR="${CONFIG_DIR:-configs/paper_accounts}"
LOG_DIR="${LOG_DIR:-${PROJECT_DIR}/logs/paper_trading_cron}"
LOCK_ROOT="${LOCK_ROOT:-/tmp}"
export T0_SQLITE_ONLY="${T0_SQLITE_ONLY:-1}"

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
import os
import sys

from overnight_bt.trade_calendar import is_a_share_trade_day

market_db_path = os.environ.get("MARKET_DATA_DB_PATH", "").strip() or None
is_open = is_a_share_trade_day(sys.argv[1], env_path=".env", market_db_path=market_db_path)
print("1" if is_open is True else "0")
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
import os
import sys

from overnight_bt import market_data_store
from overnight_bt.paper_trading import _stock_pool_db_path, list_paper_account_templates
from overnight_bt.stock_pool_templates import DEFAULT_USERNAME, read_template_symbols
from overnight_bt.utils import to_float

run_date = sys.argv[1]
config_dir = sys.argv[2]
market_db_path = os.environ.get("MARKET_DATA_DB_PATH", "").strip() or None
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
    stocks = read_template_symbols(username, template_name, db_path=db_path)
    symbols = [str(stock["symbol"]).zfill(6) for stock in stocks]
    stock_by_symbol = {str(stock["symbol"]).zfill(6): stock for stock in stocks}
    rows = market_data_store.read_feature_rows(
        symbols,
        start_date=run_date,
        end_date=run_date,
        db_path=market_db_path,
        legacy_db_path=market_data_store.DISABLE_LEGACY_FALLBACK,
    )
    available = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").zfill(6)
        raw_close = to_float(row.get("raw_close"))
        close = to_float(row.get("close"))
        if raw_close is not None and raw_close > 0 and close is not None and close > 0:
            available[symbol] = row
    missing_symbols = [symbol for symbol in symbols if symbol not in available]

    print(
        "stock pool check: "
        f"{username}/{template_name}, accounts={','.join(accounts)}, stock_count={len(symbols)}, "
        f"market_data_present={len(available)}, missing_count={len(missing_symbols)}, "
        f"trade_date={run_date}, template_db={db_path}, market_db={market_db_path or market_data_store.DEFAULT_DB_PATH}"
    )
    if not symbols:
        problems.append(f"{username}/{template_name}: empty template")
    elif missing_symbols:
        examples = ", ".join(
            f"{symbol}({stock_by_symbol.get(symbol, {}).get('stock_name') or '-'})" for symbol in missing_symbols[:20]
        )
        problems.append(f"{username}/{template_name}: sample symbols missing market data for {run_date}: {examples}")

if problems:
    raise SystemExit("market data SQLite is not fully updated to target trading day; skip paper after-close task:\n" + "\n".join(problems))
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
