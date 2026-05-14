#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/T_0_system}"
VENV_ACTIVATE="${VENV_ACTIVATE:-/home/ubuntu/TencentCloud/myenv/bin/activate}"
LOG_DIR="${LOG_DIR:-${PROJECT_DIR}/logs/stock_pool_template_update}"
LOCK_DIR="${LOCK_DIR:-/tmp/t0_stock_pool_template_update.lock}"
RUN_DATE="${1:-$(TZ=Asia/Shanghai date +%Y%m%d)}"

mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/${RUN_DATE}_cron.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

log() {
  echo "[$(date '+%F %T')] $*"
}

fail() {
  log "失败：$*"
  exit 1
}

log "开始股票池模板共享行情更新：date=${RUN_DATE}"

if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  log "已有股票池模板更新任务在运行，本次跳过。"
  exit 0
fi
trap 'rmdir "${LOCK_DIR}" 2>/dev/null || true' EXIT

cd "${PROJECT_DIR}"
[[ -f "${VENV_ACTIVATE}" ]] || fail "虚拟环境不存在：${VENV_ACTIVATE}"
source "${VENV_ACTIVATE}"

EXTRA_ARGS=()
[[ -n "${STOCK_POOL_BATCH_SIZE:-}" ]] && EXTRA_ARGS+=(--batch-size "${STOCK_POOL_BATCH_SIZE}")
[[ -n "${STOCK_POOL_BATCH_INDEX:-}" ]] && EXTRA_ARGS+=(--batch-index "${STOCK_POOL_BATCH_INDEX}")
[[ -n "${STOCK_POOL_OFFSET:-}" ]] && EXTRA_ARGS+=(--offset "${STOCK_POOL_OFFSET}")
[[ -n "${STOCK_POOL_RESUME_AFTER_SYMBOL:-}" ]] && EXTRA_ARGS+=(--resume-after-symbol "${STOCK_POOL_RESUME_AFTER_SYMBOL}")
[[ -n "${STOCK_POOL_RETRY_ATTEMPTS:-}" ]] && EXTRA_ARGS+=(--retry-attempts "${STOCK_POOL_RETRY_ATTEMPTS}")
[[ -n "${STOCK_POOL_RETRY_SLEEP_SECONDS:-}" ]] && EXTRA_ARGS+=(--retry-sleep-seconds "${STOCK_POOL_RETRY_SLEEP_SECONDS}")
[[ -n "${STOCK_POOL_MAX_SYMBOLS:-}" ]] && EXTRA_ARGS+=(--max-symbols "${STOCK_POOL_MAX_SYMBOLS}")
if [[ "${STOCK_POOL_INCLUDE_UP_TO_DATE:-0}" == "1" || "${STOCK_POOL_INCLUDE_UP_TO_DATE:-}" == "true" ]]; then
  EXTRA_ARGS+=(--include-up-to-date)
fi

python scripts/run_stock_pool_template_update.py \
  --source active_templates \
  --username "${STOCK_POOL_USERNAME:-admin}" \
  --start-date "${STOCK_POOL_START_DATE:-20220101}" \
  --end-date "${RUN_DATE}" \
  --sleep-seconds "${STOCK_POOL_SLEEP_SECONDS:-0.2}" \
  "${EXTRA_ARGS[@]}"

log "股票池模板共享行情更新完成。"
