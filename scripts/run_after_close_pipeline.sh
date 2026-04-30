#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/T_0_system}"
VENV_ACTIVATE="${VENV_ACTIVATE:-/home/ubuntu/TencentCloud/myenv/bin/activate}"
LOG_DIR="${LOG_DIR:-${PROJECT_DIR}/logs/after_close_pipeline}"
LOCK_DIR="${LOCK_DIR:-/tmp/t0_after_close_pipeline.lock}"

TOP100_DIR="${TOP100_DIR:-data_bundle/processed_qfq_theme_focus_top100}"
SECTOR_START_DATE="${SECTOR_START_DATE:-20230101}"
SECTOR_PROCESSED_DIR="${SECTOR_PROCESSED_DIR:-sector_research/data/processed}"
SECTOR_REPORT_DIR="${SECTOR_REPORT_DIR:-sector_research/reports}"
SECTOR_OUTPUT_DIR="${SECTOR_OUTPUT_DIR:-data_bundle/processed_qfq_theme_focus_top100_sector}"
PAPER_CONFIG_DIR="${PAPER_CONFIG_DIR:-configs/paper_accounts}"
RUN_PAPER_AFTER_CLOSE="${RUN_PAPER_AFTER_CLOSE:-1}"

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

log "开始收盘后统一调度：date=${RUN_DATE}, check_only=${CHECK_ONLY}"

if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  log "已有收盘后调度任务在运行，本次跳过。"
  exit 0
fi
trap 'rmdir "${LOCK_DIR}" 2>/dev/null || true' EXIT

cd "${PROJECT_DIR}"
[[ -f "${VENV_ACTIVATE}" ]] || fail "虚拟环境不存在：${VENV_ACTIVATE}"
source "${VENV_ACTIVATE}"

is_trade_day() {
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
    print(f"Tushare 交易日判断失败，尝试本地交易日历：{exc}", file=sys.stderr)

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
}

assert_under_project() {
  local target="$1"
  python - "${PROJECT_DIR}" "${target}" <<'PY'
from pathlib import Path
import sys

project = Path(sys.argv[1]).resolve()
target = Path(sys.argv[2])
if not target.is_absolute():
    target = project / target
resolved = target.resolve(strict=False)
try:
    resolved.relative_to(project)
except ValueError as exc:
    raise SystemExit(f"路径不在项目目录内: {resolved}") from exc
print(resolved)
PY
}

validate_processed_dir() {
  local dir_path="$1"
  local min_files="$2"
  shift 2
  python - "${RUN_DATE}" "${dir_path}" "${min_files}" "$@" <<'PY'
from pathlib import Path
import sys

import pandas as pd

run_date = sys.argv[1]
dir_path = Path(sys.argv[2])
min_files = int(sys.argv[3])
required_cols = [item for item in sys.argv[4:] if item]

files = sorted(path for path in dir_path.glob("*.csv") if "manifest" not in path.name)
if len(files) < min_files:
    raise SystemExit(f"{dir_path} CSV 文件数不足，期望至少 {min_files}，实际 {len(files)}")

latest_dates: list[tuple[str, str]] = []
missing_cols: list[tuple[str, list[str]]] = []
for path in files:
    frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    if "trade_date" not in frame.columns:
        raise SystemExit(f"{path.name} 缺少 trade_date")
    latest_dates.append((path.name, str(frame["trade_date"].max())))
    missing = [col for col in required_cols if col not in frame.columns]
    if missing:
        missing_cols.append((path.name, missing))

not_latest = [(name, date) for name, date in latest_dates if date != run_date]
print(f"{dir_path} 文件数：{len(files)}")
print(f"{dir_path} 最新日期范围：{min(date for _, date in latest_dates)} - {max(date for _, date in latest_dates)}")
if missing_cols:
    raise SystemExit(f"{dir_path} 存在缺失字段：{missing_cols[:5]}")
if not_latest:
    raise SystemExit(f"{dir_path} 存在未更新到 {run_date} 的文件：{not_latest[:10]}")
PY
}

validate_sector_research() {
  python - "${RUN_DATE}" "${SECTOR_PROCESSED_DIR}" "${SECTOR_REPORT_DIR}" <<'PY'
from pathlib import Path
import json
import sys

import pandas as pd

run_date = sys.argv[1]
processed_dir = Path(sys.argv[2])
report_dir = Path(sys.argv[3])
theme_path = processed_dir / "theme_strength_daily.csv"
board_path = processed_dir / "sector_board_daily.csv"
summary_path = report_dir / "sector_research_summary.json"
for path in [theme_path, board_path, summary_path]:
    if not path.exists():
        raise SystemExit(f"缺少板块研究文件: {path}")

theme = pd.read_csv(theme_path, dtype=str, encoding="utf-8-sig")
board = pd.read_csv(board_path, dtype=str, encoding="utf-8-sig")
summary = json.loads(summary_path.read_text(encoding="utf-8"))
theme_latest = str(theme["trade_date"].max())
board_latest = str(board["trade_date"].max())
print(f"板块研究最新日期：theme={theme_latest}, board={board_latest}, summary={summary.get('latest_trade_date')}")
print(f"板块研究行数：theme={len(theme)}, board={len(board)}, error_count={summary.get('error_count')}")
if theme_latest != run_date or board_latest != run_date:
    raise SystemExit(f"板块研究未更新到 {run_date}")
PY
}

IS_TRADE_DAY="$(is_trade_day)"
if [[ "${IS_TRADE_DAY}" != "1" ]]; then
  log "${RUN_DATE} 不是股票交易日，跳过收盘后统一调度。"
  exit 0
fi
log "${RUN_DATE} 是股票交易日。"

if [[ "${CHECK_ONLY}" == "1" ]]; then
  log "检查模式：依赖文件存在，交易日判断通过，不执行重任务。"
  [[ -x "scripts/run_daily_top100_update.sh" ]] || fail "缺少 scripts/run_daily_top100_update.sh 执行权限"
  [[ -x "scripts/run_paper_trading_cron.sh" ]] || fail "缺少 scripts/run_paper_trading_cron.sh 执行权限"
  [[ -f "scripts/run_sector_research.py" ]] || fail "缺少 scripts/run_sector_research.py"
  [[ -f "scripts/build_sector_research_features.py" ]] || fail "缺少 scripts/build_sector_research_features.py"
  exit 0
fi

log "1/6 更新股票主数据和主题前100目录"
scripts/run_daily_top100_update.sh "${RUN_DATE}"

log "2/6 校验主题前100目录"
validate_processed_dir "${TOP100_DIR}" 100

log "3/6 更新独立板块研究"
python scripts/run_sector_research.py \
  --start-date "${SECTOR_START_DATE}" \
  --end-date "${RUN_DATE}" \
  --processed-dir "${SECTOR_PROCESSED_DIR}" \
  --report-dir "${SECTOR_REPORT_DIR}"

log "4/6 校验板块研究结果"
validate_sector_research

log "5/6 生成带板块字段的增强 processed 目录"
SECTOR_OUTPUT_ABS="$(assert_under_project "${SECTOR_OUTPUT_DIR}")"
EXPECTED_OUTPUT_ABS="$(assert_under_project "data_bundle/processed_qfq_theme_focus_top100_sector")"
if [[ "${SECTOR_OUTPUT_ABS}" != "${EXPECTED_OUTPUT_ABS}" ]]; then
  fail "拒绝清理非预期增强目录：${SECTOR_OUTPUT_ABS}"
fi
mkdir -p "${SECTOR_OUTPUT_ABS}"
find "${SECTOR_OUTPUT_ABS}" -maxdepth 1 -type f -name "*.csv" -delete

python scripts/build_sector_research_features.py \
  --processed-dir "${TOP100_DIR}" \
  --sector-processed-dir "${SECTOR_PROCESSED_DIR}" \
  --output-dir "${SECTOR_OUTPUT_DIR}"

validate_processed_dir \
  "${SECTOR_OUTPUT_DIR}" \
  100 \
  sector_exposure_score \
  sector_strongest_theme_score \
  sector_strongest_theme_rank_pct

log "6/6 运行模拟账户收盘估值和生成 T+1 待执行订单"
if [[ "${RUN_PAPER_AFTER_CLOSE}" == "1" ]]; then
  CONFIG_DIR="${PAPER_CONFIG_DIR}" PROCESSED_CHECK_DIR="${SECTOR_OUTPUT_DIR}" scripts/run_paper_trading_cron.sh after-close "${RUN_DATE}"
else
  log "RUN_PAPER_AFTER_CLOSE=${RUN_PAPER_AFTER_CLOSE}，跳过模拟账户 after-close。"
fi

SUCCESS_FILE="${LOG_DIR}/latest_success.txt"
{
  echo "success_date=${RUN_DATE}"
  echo "finished_at=$(date '+%F %T')"
  echo "top100_dir=${TOP100_DIR}"
  echo "sector_processed_dir=${SECTOR_PROCESSED_DIR}"
  echo "sector_output_dir=${SECTOR_OUTPUT_DIR}"
  echo "paper_config_dir=${PAPER_CONFIG_DIR}"
  echo "log_file=${LOG_FILE}"
} > "${SUCCESS_FILE}"

log "收盘后统一调度完成：date=${RUN_DATE}"
