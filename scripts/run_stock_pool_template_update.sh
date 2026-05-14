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

positive_int() {
  local value="${1:-0}"
  if [[ "${value}" =~ ^[0-9]+$ ]]; then
    echo "${value}"
  else
    echo 0
  fi
}

COMMON_EXTRA_ARGS=()
[[ -n "${STOCK_POOL_OFFSET:-}" ]] && COMMON_EXTRA_ARGS+=(--offset "${STOCK_POOL_OFFSET}")
[[ -n "${STOCK_POOL_RESUME_AFTER_SYMBOL:-}" ]] && COMMON_EXTRA_ARGS+=(--resume-after-symbol "${STOCK_POOL_RESUME_AFTER_SYMBOL}")
[[ -n "${STOCK_POOL_RETRY_ATTEMPTS:-}" ]] && COMMON_EXTRA_ARGS+=(--retry-attempts "${STOCK_POOL_RETRY_ATTEMPTS}")
[[ -n "${STOCK_POOL_RETRY_SLEEP_SECONDS:-}" ]] && COMMON_EXTRA_ARGS+=(--retry-sleep-seconds "${STOCK_POOL_RETRY_SLEEP_SECONDS}")
[[ -n "${STOCK_POOL_MAX_SYMBOLS:-}" ]] && COMMON_EXTRA_ARGS+=(--max-symbols "${STOCK_POOL_MAX_SYMBOLS}")
if [[ "${STOCK_POOL_INCLUDE_UP_TO_DATE:-0}" == "1" || "${STOCK_POOL_INCLUDE_UP_TO_DATE:-}" == "true" ]]; then
  COMMON_EXTRA_ARGS+=(--include-up-to-date)
fi

run_one_batch() {
  local batch_index="${1:-}"
  local batch_args=()
  [[ -n "${STOCK_POOL_BATCH_SIZE:-}" ]] && batch_args+=(--batch-size "${STOCK_POOL_BATCH_SIZE}")
  if [[ -n "${batch_index}" ]]; then
    batch_args+=(--batch-index "${batch_index}")
  elif [[ -n "${STOCK_POOL_BATCH_INDEX:-}" ]]; then
    batch_args+=(--batch-index "${STOCK_POOL_BATCH_INDEX}")
  fi

  cmd=(
    python scripts/run_stock_pool_template_update.py
    --source active_templates
    --username "${STOCK_POOL_USERNAME:-admin}"
    --start-date "${STOCK_POOL_START_DATE:-20220101}"
    --end-date "${RUN_DATE}"
    --sleep-seconds "${STOCK_POOL_SLEEP_SECONDS:-0.2}"
  )
  cmd+=("${batch_args[@]}")
  cmd+=("${COMMON_EXTRA_ARGS[@]}")
  "${cmd[@]}"
}

BATCH_COUNT="$(positive_int "${STOCK_POOL_BATCH_COUNT:-1}")"
if (( BATCH_COUNT < 1 )); then
  BATCH_COUNT=1
fi
BATCH_SLEEP_SECONDS="${STOCK_POOL_BATCH_SLEEP_SECONDS:-60}"
START_BATCH_INDEX="$(positive_int "${STOCK_POOL_BATCH_INDEX:-0}")"

if [[ -n "${STOCK_POOL_BATCH_SIZE:-}" && "${BATCH_COUNT}" -gt 1 && -z "${STOCK_POOL_OFFSET:-}" && -z "${STOCK_POOL_RESUME_AFTER_SYMBOL:-}" ]]; then
  log "启用股票池多批次更新：batch_size=${STOCK_POOL_BATCH_SIZE}, start_batch_index=${START_BATCH_INDEX}, batch_count=${BATCH_COUNT}, batch_sleep_seconds=${BATCH_SLEEP_SECONDS}"
  for ((i = 0; i < BATCH_COUNT; i++)); do
    batch_index=$((START_BATCH_INDEX + i))
    log "股票池模板共享行情更新批次 $((i + 1))/${BATCH_COUNT}：batch_index=${batch_index}"
    run_one_batch "${batch_index}"
    if (( i + 1 < BATCH_COUNT )); then
      log "批次间暂停 ${BATCH_SLEEP_SECONDS} 秒，降低 Tushare 调用压力。"
      sleep "${BATCH_SLEEP_SECONDS}"
    fi
  done
elif [[ "${BATCH_COUNT}" -gt 1 ]]; then
  log "STOCK_POOL_BATCH_COUNT=${BATCH_COUNT} 需要同时设置 STOCK_POOL_BATCH_SIZE，且不能与 offset/resume-after 混用；本次按单批运行。"
  run_one_batch ""
else
  run_one_batch ""
fi

log "股票池模板共享行情更新完成。"
