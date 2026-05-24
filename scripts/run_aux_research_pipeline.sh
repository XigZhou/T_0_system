#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/T_0_system}"
VENV_ACTIVATE="${VENV_ACTIVATE:-/home/ubuntu/TencentCloud/myenv/bin/activate}"
LOG_DIR="${LOG_DIR:-${PROJECT_DIR}/logs/aux_research_pipeline}"
LOCK_DIR="${LOCK_DIR:-/tmp/t0_aux_research_pipeline.lock}"
SECTOR_START_DATE="${SECTOR_START_DATE:-20230101}"
SECTOR_PROCESSED_DIR="${SECTOR_PROCESSED_DIR:-sector_research/data/processed}"
SECTOR_REPORT_DIR="${SECTOR_REPORT_DIR:-sector_research/reports}"
MARKET_DB_PATH="${MARKET_DB_PATH:-data_store/market_data.sqlite}"
BUILD_LEGACY_CSV_FEATURES="${BUILD_LEGACY_CSV_FEATURES:-0}"
SCHEDULER_JOB_NAME="${SCHEDULER_JOB_NAME:-aux_research_pipeline}"

CHECK_ONLY=0
if [[ "${1:-}" == "--check-only" ]]; then
  CHECK_ONLY=1
  shift
fi
RUN_DATE="${1:-$(TZ=Asia/Shanghai date +%Y%m%d)}"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/${RUN_DATE}.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

log() { echo "[$(date '+%F %T')] $*"; }
fail() { log "失败：$*"; exit 1; }

record_start() {
  python - "${SCHEDULER_JOB_NAME}" "${RUN_DATE}" "${LOG_FILE}" <<'PY'
import sys
from overnight_bt.scheduler import record_run_start
print(record_run_start(sys.argv[1], target_date=sys.argv[2], log_file=sys.argv[3])["run_id"])
PY
}
record_end() {
  local status="$1"; local failed_stage="${2:-}"; local error_summary="${3:-}"
  [[ -n "${RUN_ID:-}" ]] || return 0
  python - "${RUN_ID}" "${status}" "${failed_stage}" "${error_summary}" "${LOG_FILE}" <<'PY'
import sys
from overnight_bt.scheduler import record_run_end
record_run_end(sys.argv[1], status=sys.argv[2], failed_stage=sys.argv[3], error_summary=sys.argv[4], log_file=sys.argv[5])
PY
}
CURRENT_STAGE="bootstrap"; RUN_ID=""
on_error() {
  local exit_code=$?
  record_end "failed" "${CURRENT_STAGE}" "aux research failed at ${CURRENT_STAGE} (exit ${exit_code})" || true
  exit "${exit_code}"
}
trap on_error ERR

assert_under_project() {
  python - "${PROJECT_DIR}" "$1" <<'PY'
from pathlib import Path
import sys
project = Path(sys.argv[1]).resolve()
target = Path(sys.argv[2])
if not target.is_absolute():
    target = project / target
resolved = target.resolve(strict=False)
resolved.relative_to(project)
print(resolved)
PY
}
validate_processed_dir() {
  local dir_path="$1"; local min_files="$2"; shift 2
  python - "${RUN_DATE}" "${dir_path}" "${min_files}" "$@" <<'PY'
from pathlib import Path
import sys
import pandas as pd
run_date, dir_text, min_files = sys.argv[1], sys.argv[2], int(sys.argv[3])
required = [item for item in sys.argv[4:] if item]
files = sorted(path for path in Path(dir_text).glob("*.csv") if "manifest" not in path.name)
if len(files) < min_files:
    raise SystemExit(f"{dir_text} CSV 文件数不足，期望至少 {min_files}，实际 {len(files)}")
for path in files:
    frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    if str(frame["trade_date"].max()) != run_date:
        raise SystemExit(f"{path.name} 未更新到 {run_date}")
    missing = [col for col in required if col not in frame.columns]
    if missing:
        raise SystemExit(f"{path.name} 缺少字段 {missing}")
print(f"{dir_text} 研究特征校验通过：{len(files)} files")
PY
}
validate_same_stock_pool() {
  python - "$@" <<'PY'
from pathlib import Path
import sys
pairs = []
for raw in sys.argv[1:]:
    label, sep, path_text = raw.partition("=")
    if not sep:
        raise SystemExit(f"bad argument: {raw}")
    pairs.append((label, Path(path_text)))
sets = {}
for label, folder in pairs:
    symbols = set()
    for path in folder.glob("*.csv"):
        if "manifest" in path.name:
            continue
        digits = "".join(ch for ch in path.stem.split(".", 1)[0] if ch.isdigit())
        if digits:
            symbols.add(digits[-6:].zfill(6))
    sets[label] = symbols
    print(f"{label} stock pool count: {len(symbols)}")
base_label, base_symbols = next(iter(sets.items()))
for label, symbols in list(sets.items())[1:]:
    if symbols != base_symbols:
        raise SystemExit(
            f"stock pool mismatch: {base_label} only={sorted(base_symbols - symbols)[:20]}; "
            f"{label} only={sorted(symbols - base_symbols)[:20]}"
        )
PY
}
validate_sector_research() {
  python - "${RUN_DATE}" "${SECTOR_PROCESSED_DIR}" "${SECTOR_REPORT_DIR}" <<'PY'
from pathlib import Path
import json
import sys
import pandas as pd
run_date, processed_dir, report_dir = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
theme = pd.read_csv(processed_dir / "theme_strength_daily.csv", dtype=str, encoding="utf-8-sig")
board = pd.read_csv(processed_dir / "sector_board_daily.csv", dtype=str, encoding="utf-8-sig")
summary = json.loads((report_dir / "sector_research_summary.json").read_text(encoding="utf-8"))
if str(theme["trade_date"].max()) != run_date or str(board["trade_date"].max()) != run_date:
    raise SystemExit(f"板块研究未更新到 {run_date}")
print(f"板块研究校验通过：latest={summary.get('latest_trade_date')}")
PY
}

log "开始辅助研究调度：date=${RUN_DATE}, check_only=${CHECK_ONLY}"
if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  log "已有辅助研究调度任务在运行，本次跳过。"
  exit 0
fi
trap 'rmdir "${LOCK_DIR}" 2>/dev/null || true' EXIT
cd "${PROJECT_DIR}"
[[ -f "${VENV_ACTIVATE}" ]] || fail "虚拟环境不存在：${VENV_ACTIVATE}"
source "${VENV_ACTIVATE}"
if [[ "${CHECK_ONLY}" == "1" ]]; then
  [[ -f "scripts/run_sector_research.py" ]] || fail "缺少 scripts/run_sector_research.py"
  [[ -f "scripts/run_sector_research.py" ]] || fail "缺少 scripts/run_sector_research.py"
  log "检查模式通过：辅助研究链将板块结果写入 SQLite 主库，不再要求 data_bundle 增强目录。"
  exit 0
fi
RUN_ID="$(record_start)"
CURRENT_STAGE="sector_research"
python scripts/run_sector_research.py --start-date "${SECTOR_START_DATE}" --end-date "${RUN_DATE}" --processed-dir "${SECTOR_PROCESSED_DIR}" --report-dir "${SECTOR_REPORT_DIR}" --market-db "${MARKET_DB_PATH}"
validate_sector_research
if [[ "${BUILD_LEGACY_CSV_FEATURES}" == "1" ]]; then
  fail "BUILD_LEGACY_CSV_FEATURES=1 已不属于 SQLite-only 主链路；请单独迁移旧增强特征后再启用。"
fi
CURRENT_STAGE="record_success"
record_end "success"
log "辅助研究调度完成：date=${RUN_DATE}, run_id=${RUN_ID}"
