#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/T_0_system}"
VENV_ACTIVATE="${VENV_ACTIVATE:-/home/ubuntu/TencentCloud/myenv/bin/activate}"
LOG_DIR="${LOG_DIR:-${PROJECT_DIR}/logs/core_after_close_pipeline}"
LOCK_DIR="${LOCK_DIR:-/tmp/t0_core_after_close_pipeline.lock}"
PAPER_CONFIG_DIR="${PAPER_CONFIG_DIR:-configs/paper_accounts}"
RUN_PAPER_AFTER_CLOSE="${RUN_PAPER_AFTER_CLOSE:-1}"
SCHEDULER_JOB_NAME="${SCHEDULER_JOB_NAME:-core_after_close_generate}"
CORE_STATUS_FILE="${CORE_STATUS_FILE:-}"
STOCK_POOL_SOURCE="${STOCK_POOL_SOURCE:-all}"
FEATURE_RETRY_ATTEMPTS="${FEATURE_RETRY_ATTEMPTS:-3}"
FEATURE_RETRY_SLEEP_SECONDS="${FEATURE_RETRY_SLEEP_SECONDS:-2.0}"
FEATURE_SLEEP_SECONDS="${FEATURE_SLEEP_SECONDS:-0.2}"
export T0_SQLITE_ONLY="${T0_SQLITE_ONLY:-1}"

CHECK_ONLY=0
if [[ "${1:-}" == "--check-only" ]]; then
  CHECK_ONLY=1
  shift
fi
RUN_DATE="${1:-$(TZ=Asia/Shanghai date +%Y%m%d)}"

mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/${RUN_DATE}.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

log() {
  echo "[$(date '+%F %T')] $*"
}

fail() {
  log "失败：$*"
  exit 1
}

write_status() {
  local status="$1"
  local reason="${2:-}"
  [[ -n "${CORE_STATUS_FILE}" ]] || return 0
  mkdir -p "$(dirname "${CORE_STATUS_FILE}")"
  {
    echo "status=${status}"
    echo "reason=${reason}"
    echo "run_date=${RUN_DATE}"
    echo "log_file=${LOG_FILE}"
  } > "${CORE_STATUS_FILE}"
}

record_start() {
  python - "${SCHEDULER_JOB_NAME}" "${RUN_DATE}" "${LOG_FILE}" <<'PY'
import sys
from overnight_bt.scheduler import record_run_start
run = record_run_start(sys.argv[1], target_date=sys.argv[2], log_file=sys.argv[3])
print(run["run_id"])
PY
}

record_end() {
  local status="$1"
  local failed_stage="${2:-}"
  local error_summary="${3:-}"
  [[ -n "${RUN_ID:-}" ]] || return 0
  python - "${RUN_ID}" "${status}" "${failed_stage}" "${error_summary}" "${LOG_FILE}" <<'PY'
import sys
from overnight_bt.scheduler import record_run_end
record_run_end(
    sys.argv[1],
    status=sys.argv[2],
    failed_stage=sys.argv[3],
    error_summary=sys.argv[4],
    log_file=sys.argv[5],
)
PY
}

CURRENT_STAGE="bootstrap"
RUN_ID=""
on_error() {
  local exit_code=$?
  record_end "failed" "${CURRENT_STAGE}" "core after-close failed at ${CURRENT_STAGE} (exit ${exit_code})" || true
  exit "${exit_code}"
}
trap on_error ERR

is_trade_day() {
  python - "${RUN_DATE}" <<'PY'
import os
import sys
from overnight_bt.trade_calendar import is_a_share_trade_day

market_db_path = os.environ.get("MARKET_DATA_DB_PATH", "").strip() or None
is_open = is_a_share_trade_day(sys.argv[1], env_path=".env", market_db_path=market_db_path)
print("1" if is_open is True else "0")
PY
}

log "开始核心收盘后调度：date=${RUN_DATE}, check_only=${CHECK_ONLY}"
if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  log "已有核心收盘后调度任务在运行，本次跳过。"
  write_status "skipped_locked" "已有核心收盘后调度任务在运行"
  exit 0
fi
trap 'rmdir "${LOCK_DIR}" 2>/dev/null || true' EXIT

cd "${PROJECT_DIR}"
[[ -f "${VENV_ACTIVATE}" ]] || fail "虚拟环境不存在：${VENV_ACTIVATE}"
source "${VENV_ACTIVATE}"

if [[ "${CHECK_ONLY}" == "1" ]]; then
  [[ -f "scripts/collect_stock_daily_raw.py" ]] || fail "missing scripts/collect_stock_daily_raw.py"
  [[ -f "scripts/compute_stock_daily_features.py" ]] || fail "missing scripts/compute_stock_daily_features.py"
  [[ -x "scripts/run_paper_trading_cron.sh" ]] || fail "missing executable scripts/run_paper_trading_cron.sh"
  log "check-only ok: collect SQLite raw tables, compute stock_daily_features, then run paper after-close for ${STOCK_POOL_SOURCE} (all means main universe)."
  write_status "check_only" "check-only did not execute core chain"
  exit 0
fi

CURRENT_STAGE="trade_day"
IS_TRADE_DAY="$(is_trade_day)"
if [[ "${IS_TRADE_DAY}" != "1" ]]; then
  log "${RUN_DATE} 不是股票交易日，跳过核心收盘后调度。"
  write_status "skipped_non_trade_day" "非交易日"
  exit 0
fi
log "${RUN_DATE} 是股票交易日。"

CURRENT_STAGE="record_start"
RUN_ID="$(record_start)"
CURRENT_STAGE="sqlite_raw_collect"
log "1/3 collect main-universe daily raw inputs into SQLite raw tables"
python scripts/collect_stock_daily_raw.py \
  --source "${STOCK_POOL_SOURCE}" \
  --start-date "${RUN_DATE}" \
  --end-date "${RUN_DATE}" \
  --include-up-to-date \
  --retry-attempts "${FEATURE_RETRY_ATTEMPTS}" \
  --retry-sleep-seconds "${FEATURE_RETRY_SLEEP_SECONDS}" \
  --sleep-seconds "${FEATURE_SLEEP_SECONDS}"

CURRENT_STAGE="sqlite_feature_compute"
log "2/3 compute main-universe stock indicators into stock_daily_features"
python scripts/compute_stock_daily_features.py \
  --source "${STOCK_POOL_SOURCE}" \
  --start-date "${RUN_DATE}" \
  --end-date "${RUN_DATE}" \
  --include-up-to-date \
  --retry-attempts "${FEATURE_RETRY_ATTEMPTS}" \
  --retry-sleep-seconds "${FEATURE_RETRY_SLEEP_SECONDS}" \
  --sleep-seconds "${FEATURE_SLEEP_SECONDS}"

CURRENT_STAGE="paper_after_close"
log "3/3 run paper after-close"
if [[ "${RUN_PAPER_AFTER_CLOSE}" == "1" ]]; then
  CONFIG_DIR="${PAPER_CONFIG_DIR}" scripts/run_paper_trading_cron.sh after-close "${RUN_DATE}"
else
  log "RUN_PAPER_AFTER_CLOSE=${RUN_PAPER_AFTER_CLOSE}, skip paper after-close."
fi

CURRENT_STAGE="record_success"
record_end "success"
write_status "success" "核心链完成"
log "核心收盘后调度完成：date=${RUN_DATE}, run_id=${RUN_ID}"
