#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/T_0_system}"
VENV_ACTIVATE="${VENV_ACTIVATE:-/home/ubuntu/TencentCloud/myenv/bin/activate}"
LOG_DIR="${LOG_DIR:-${PROJECT_DIR}/logs/top100_daily_update}"
LOCK_DIR="${LOCK_DIR:-/tmp/t0_top100_daily_update.lock}"

CHECK_ONLY=0
if [[ "${1:-}" == "--check-only" ]]; then
  CHECK_ONLY=1
  shift
fi

RUN_DATE="${1:-$(TZ=Asia/Shanghai date +%Y%m%d)}"

mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/${RUN_DATE}.log"

exec > >(tee -a "${LOG_FILE}") 2>&1

echo "[$(date '+%F %T')] 开始检查主题前100日常更新，目标日期：${RUN_DATE}"

if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  echo "[$(date '+%F %T')] 已有更新任务在运行，本次跳过。"
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

import tushare as ts

from overnight_bt.utils import load_env

run_date = sys.argv[1]
token = load_env(Path(".env")).get("TUSHARE_TOKEN", "").strip()
if not token:
    raise SystemExit("TUSHARE_TOKEN is empty in .env")

pro = ts.pro_api(token)
cal = pro.trade_cal(exchange="", start_date=run_date, end_date=run_date, fields="cal_date,is_open")
is_open = cal is not None and not cal.empty and str(cal.iloc[0].get("is_open", "")).strip() == "1"
print("1" if is_open else "0")
PY
)"

if [[ "${IS_TRADE_DAY}" != "1" ]]; then
  echo "[$(date '+%F %T')] ${RUN_DATE} 不是股票交易日，跳过更新。"
  exit 0
fi

echo "[$(date '+%F %T')] ${RUN_DATE} 是股票交易日。"

if [[ "${CHECK_ONLY}" == "1" ]]; then
  echo "[$(date '+%F %T')] 检查模式通过，不执行拉数和重建。"
  exit 0
fi

echo "[$(date '+%F %T')] 1/6 更新股票池快照"
python scripts/build_universe_snapshot.py --env .env --out data_bundle/universe_snapshot.csv --as-of "${RUN_DATE}"

echo "[$(date '+%F %T')] 2/6 同步 Tushare 原始数据"
python scripts/sync_tushare_bundle.py \
  --env .env \
  --bundle-dir data_bundle \
  --snapshot-csv data_bundle/universe_snapshot.csv \
  --start-date 20160101 \
  --end-date "${RUN_DATE}" \
  --sleep-seconds 0.2

echo "[$(date '+%F %T')] 3/6 重建全量 processed_qfq"
python scripts/build_processed_data.py \
  --bundle-dir data_bundle \
  --output-dir data_bundle/processed_qfq \
  --snapshot-csv data_bundle/universe_snapshot.csv

echo "[$(date '+%F %T')] 4/6 清理并重建主题前100目录"
TOP100_DIR="${PROJECT_DIR}/data_bundle/processed_qfq_theme_focus_top100"
EXPECTED_TOP100_DIR="${PROJECT_DIR}/data_bundle/processed_qfq_theme_focus_top100"
if [[ "${TOP100_DIR}" != "${EXPECTED_TOP100_DIR}" ]]; then
  echo "拒绝清理非预期目录：${TOP100_DIR}"
  exit 1
fi
mkdir -p "${TOP100_DIR}"
find "${TOP100_DIR}" -maxdepth 1 -type f -name "*.csv" -delete

python scripts/build_theme_focus_universe.py \
  --snapshot-csv data_bundle/universe_snapshot.csv \
  --processed-dir data_bundle/processed_qfq \
  --out-snapshot data_bundle/universe_snapshot_theme_focus_top100.csv \
  --out-processed-dir data_bundle/processed_qfq_theme_focus_top100 \
  --top-k 100

echo "[$(date '+%F %T')] 5/6 重算行业强度"
python scripts/build_industry_strength.py --processed-dir data_bundle/processed_qfq_theme_focus_top100

echo "[$(date '+%F %T')] 6/6 校验主题前100最新日期"
python - "${RUN_DATE}" <<'PY'
from pathlib import Path
import sys

import pandas as pd

run_date = sys.argv[1]
target = Path("data_bundle/processed_qfq_theme_focus_top100")
files = sorted(path for path in target.glob("*.csv") if "manifest" not in path.name)
if len(files) != 100:
    raise SystemExit(f"主题前100文件数不是100：{len(files)}")

latest_dates: list[tuple[str, str]] = []
for path in files:
    frame = pd.read_csv(path, usecols=["trade_date"], dtype=str, encoding="utf-8-sig")
    latest_dates.append((path.name, str(frame["trade_date"].max())))

not_latest = [(name, date) for name, date in latest_dates if date != run_date]
print(f"文件数：{len(files)}")
print(f"最晚日期：{max(date for _, date in latest_dates)}")
print(f"非目标日期文件数：{len(not_latest)}")
if not_latest:
    raise SystemExit(f"存在未更新到 {run_date} 的文件：{not_latest[:10]}")
PY

SUCCESS_FILE="${LOG_DIR}/latest_success.txt"
{
  echo "success_date=${RUN_DATE}"
  echo "finished_at=$(date '+%F %T')"
  echo "log_file=${LOG_FILE}"
} > "${SUCCESS_FILE}"

echo "[$(date '+%F %T')] 主题前100日常更新完成。"
