from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from overnight_bt.models import PaperTradingRunRequest
from overnight_bt.paper_trading import run_all_paper_accounts, run_paper_trading


def main() -> None:
    parser = argparse.ArgumentParser(description="运行多账户模拟交易系统")
    parser.add_argument("--config", default="", help="单个中文 YAML 模拟账户模板路径")
    parser.add_argument("--config-dir", default="configs/paper_accounts", help="模板目录；配合 --all 使用")
    parser.add_argument("--account-id", default="", help="账户编号；config 为空时从模板目录匹配")
    parser.add_argument(
        "--action",
        choices=["generate", "execute", "mark", "refresh"],
        default="generate",
        help="generate=收盘生成待执行订单，execute=开盘执行待成交订单，mark=收盘估值，refresh=实时刷新当前持仓估值",
    )
    parser.add_argument("--date", default="", help="动作日期 YYYYMMDD；留空时使用数据最新日期")
    parser.add_argument("--all", action="store_true", help="运行模板目录下所有模拟账户")
    args = parser.parse_args()

    if args.all:
        result = run_all_paper_accounts(Path(args.config_dir), args.action, args.date)
    else:
        result = run_paper_trading(
            PaperTradingRunRequest(
                config_path=args.config,
                config_dir=args.config_dir,
                account_id=args.account_id,
                action=args.action,
                trade_date=args.date,
            )
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
