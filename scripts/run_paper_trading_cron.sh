#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/T_0_system}"
VENV_ACTIVATE="${VENV_ACTIVATE:-/home/ubuntu/TencentCloud/myenv/bin/activate}"
CONFIG_DIR="${CONFIG_DIR:-configs/paper_accounts}"
LOG_DIR="${LOG_DIR:-${PROJECT_DIR}/logs/paper_trading_cron}"
LOCK_ROOT="${LOCK_ROOT:-/tmp}"
PROCESSED_CHECK_DIR="${PROCESSED_CHECK_DIR:-data_bundle/processed_qfq_theme_focus_top100}"

ACTION="${1:-}"
if [[ -z "${ACTION}" ]]; then
  echo "用法：$0 execute|generate|mark|after-close|--check-only [YYYYMMDD]" >&2
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
    echo "未知动作：${ACTION}，可选 execute|generate|mark|after-close" >&2
    exit 2
    ;;
esac

mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/${RUN_DATE}_${ACTION}.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "[$(date '+%F %T')] 开始模拟交易定时任务：action=${ACTION}, date=${RUN_DATE}"

LOCK_DIR="${LOCK_ROOT}/t0_paper_trading_${ACTION}.lock"
if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  echo "[$(date '+%F %T')] 已有 ${ACTION} 任务在运行，本次跳过。"
  exit 0
fi
trap 'rmdir "${LOCK_DIR}" 2>/dev/null || true' EXIT

cd "${PROJECT_DIR}"
if [[ ! -f "${VENV_ACTIVATE}" ]]; then
  echo "虚拟环境不存在：${VENV_ACTIVATE}"
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
)"

if [[ "${IS_TRADE_DAY}" != "1" ]]; then
  echo "[$(date '+%F %T')] ${RUN_DATE} 不是股票交易日，跳过模拟交易任务。"
  exit 0
fi

echo "[$(date '+%F %T')] ${RUN_DATE} 是股票交易日。"

if [[ "${CHECK_ONLY}" == "1" ]]; then
  echo "[$(date '+%F %T')] 检查模式通过，不执行模拟交易。"
  exit 0
fi

ensure_processed_latest() {
  python - "${RUN_DATE}" "${PROCESSED_CHECK_DIR}" <<'PY'
from pathlib import Path
import sys

import pandas as pd

run_date = sys.argv[1]
target = Path(sys.argv[2])
files = sorted(path for path in target.glob("*.csv") if "manifest" not in path.name)
if not files:
    raise SystemExit(f"{target} 处理后目录没有 CSV 文件")

latest_dates = []
for path in files:
    frame = pd.read_csv(path, usecols=["trade_date"], dtype=str, encoding="utf-8-sig")
    if frame.empty:
        raise SystemExit(f"{path.name} 为空")
    latest_dates.append(str(frame["trade_date"].max()))

min_latest = min(latest_dates)
max_latest = max(latest_dates)
print(f"处理后校验目录：{target}，文件数：{len(files)}，最小最新日期：{min_latest}，最大最新日期：{max_latest}")
if min_latest < run_date:
    raise SystemExit(f"处理后数据尚未全部更新到 {run_date}，跳过生成下一交易日订单")
PY
}

run_all_accounts() {
  local action_name="$1"
  echo "[$(date '+%F %T')] 运行所有模拟账户：${action_name}"
  python scripts/run_paper_trading.py --config-dir "${CONFIG_DIR}" --all --action "${action_name}" --date "${RUN_DATE}"
}

case "${ACTION}" in
  execute)
    run_all_accounts execute
    ;;
  generate)
    ensure_processed_latest
    run_all_accounts generate
    ;;
  mark)
    ensure_processed_latest
    run_all_accounts mark
    ;;
  after-close)
    ensure_processed_latest
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

echo "[$(date '+%F %T')] 模拟交易定时任务完成：action=${ACTION}, date=${RUN_DATE}"
