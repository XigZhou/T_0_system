#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/T_0_system}"
RUN_AUX_RESEARCH_AFTER_CORE="${RUN_AUX_RESEARCH_AFTER_CORE:-0}"
CORE_STATUS_FILE="${CORE_STATUS_FILE:-$(mktemp "${TMPDIR:-/tmp}/t0_core_after_close_status.XXXXXX")}"

log() {
  echo "[$(date '+%F %T')] $*"
}

read_core_status() {
  if [[ -f "${CORE_STATUS_FILE}" ]]; then
    awk -F= '$1 == "status" { print $2; exit }' "${CORE_STATUS_FILE}"
  fi
}

log "兼容入口 scripts/run_after_close_pipeline.sh 已拆分：默认只运行核心交易链。"
log "辅助板块/轮动研究请单独运行 scripts/run_aux_research_pipeline.sh。"
PROJECT_DIR="${PROJECT_DIR}" CORE_STATUS_FILE="${CORE_STATUS_FILE}" "${PROJECT_DIR}/scripts/run_core_after_close_pipeline.sh" "$@"
CORE_STATUS="$(read_core_status)"
if [[ "${RUN_AUX_RESEARCH_AFTER_CORE}" == "1" ]]; then
  if [[ "${CORE_STATUS}" == "success" ]]; then
    log "RUN_AUX_RESEARCH_AFTER_CORE=1，核心链成功后运行辅助研究链。"
    PROJECT_DIR="${PROJECT_DIR}" "${PROJECT_DIR}/scripts/run_aux_research_pipeline.sh" "$@"
  else
    log "核心链状态为 ${CORE_STATUS:-unknown}，不运行辅助研究链。"
  fi
else
  log "RUN_AUX_RESEARCH_AFTER_CORE=${RUN_AUX_RESEARCH_AFTER_CORE}，本次不运行辅助研究链。"
fi
