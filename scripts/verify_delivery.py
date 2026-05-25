from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overnight_bt.delivery_checks import (  # noqa: E402
    build_delivery_report,
    parse_args,
)


PROJECT_EXTRA_PATHS = (
    Path("AGENTS.md"),
    Path("PROJECT_MAP.md"),
    Path("docs/system-documentation.md"),
    Path("docs/sqlite-data-dictionary.md"),
    Path("docs/backtest-data-dictionary.md"),
    Path("docs/indicator-reference.md"),
    Path("docs/expression-reference.md"),
    Path("docs/paper-trading-system.md"),
    Path("docs/after-close-pipeline.md"),
    Path("docs/data-dictionary-template.md"),
    Path("docs/indicator-documentation-template.md"),
    Path("static/index.html"),
    Path("static/daily.html"),
    Path("static/single.html"),
    Path("static/paper.html"),
    Path("static/paper_templates.html"),
    Path("static/stock_pools.html"),
    Path("static/admin.html"),
    Path("static/users.html"),
    Path("static/sector.html"),
    Path("static/app.js"),
    Path("static/daily.js"),
    Path("static/single.js"),
    Path("static/paper.js"),
    Path("static/paper_templates.js"),
    Path("static/stock_pools.js"),
    Path("static/admin.js"),
    Path("static/users.js"),
    Path("static/sector.js"),
    Path("static/style.css"),
    Path("overnight_bt/app.py"),
    Path("overnight_bt/main_universe.py"),
    Path("overnight_bt/market_data_store.py"),
    Path("overnight_bt/stock_pool_feature_store.py"),
    Path("overnight_bt/backtest.py"),
    Path("overnight_bt/daily_plan.py"),
    Path("overnight_bt/single_stock.py"),
    Path("overnight_bt/paper_trading.py"),
    Path("overnight_bt/scheduler.py"),
    Path("scripts/init_main_universe_from_tushare.py"),
    Path("scripts/collect_stock_daily_raw.py"),
    Path("scripts/compute_stock_daily_features.py"),
    Path("scripts/run_core_after_close_pipeline.sh"),
    Path("scripts/run_after_close_pipeline.sh"),
    Path("scripts/run_paper_trading.py"),
    Path("scripts/run_paper_trading_cron.sh"),
)
PROJECT_README_PHRASES = (
    "TUSHARE_TOKEN",
    "T0_ADMIN_DEFAULT_PASSWORD",
    "scripts/init_main_universe_from_tushare.py",
    "scripts/collect_stock_daily_raw.py",
    "scripts/compute_stock_daily_features.py",
    "scripts/run_core_after_close_pipeline.sh",
    "python -m uvicorn overnight_bt.app:app",
    "source=all",
    "market_data.sqlite",
    "stock_daily_features",
    "/admin",
    "/paper",
    "/sector",
    "/stock-pools",
)
PROJECT_REMOVED_PATHS = (
    Path("docs/superpowers"),
    Path("docs/sector-dashboard-sqlite-data-dictionary.md"),
    Path("docs/sector-research-system-guide.md"),
    Path("docs/sector-parameter-grid-data-dictionary.md"),
    Path("docs/sector-rotation-diagnosis-data-dictionary.md"),
    Path("docs/sector-rotation-grid-data-dictionary.md"),
    Path("docs/stock-pool-layer-grid-data-dictionary.md"),
    Path("docs/stock-pool-template-data-dictionary.md"),
    Path("docs/stock-pool-template-system-plan.md"),
    Path("docs/theme-focus-universe-data-dictionary.md"),
    Path("docs/theme-tradeable-universe-data-dictionary.md"),
)


def _detect_project_layout(root: Path) -> bool:
    return (root / "overnight_bt").exists() and (root / "static").exists()


def _build_project_extra_issues(root: Path) -> list[str]:
    issues: list[str] = []
    for rel_path in PROJECT_EXTRA_PATHS:
        if not (root / rel_path).exists():
            issues.append(f"缺少项目交付文件: {rel_path.as_posix()}")

    for rel_path in PROJECT_REMOVED_PATHS:
        if (root / rel_path).exists():
            issues.append(f"历史文档未清理: {rel_path.as_posix()}")

    readme_path = root / "README.md"
    readme_text = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    for phrase in PROJECT_README_PHRASES:
        if phrase not in readme_text:
            issues.append(f"README 缺少关键说明: {phrase}")

    docs_dir = root / "docs"
    if docs_dir.exists() and len(list(docs_dir.glob("*.md"))) < 9:
        issues.append("docs/ 文档数量不足，至少应包含当前系统说明、数据字典、指标、表达式、模拟交易、调度和模板文档")
    return issues


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    readme_path = Path(args.readme)
    required_sections = tuple(args.sections or ("准备工作", "启动方式", "复现结果"))
    required_paths = tuple(Path(path) for path in (args.required_paths or ("README.md", "docs/data-dictionary-template.md", "docs/indicator-documentation-template.md")))

    issues = build_delivery_report(root, readme_path, required_sections, required_paths)
    if _detect_project_layout(root):
        issues.extend(_build_project_extra_issues(root))

    if issues:
        print("交付检查未通过：")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("交付检查通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())