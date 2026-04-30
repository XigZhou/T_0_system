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
    Path("docs/backtest-data-dictionary.md"),
    Path("docs/indicator-reference.md"),
    Path("docs/system-documentation.md"),
    Path("docs/sector-research-system-guide.md"),
    Path("static/index.html"),
    Path("static/single.html"),
    Path("static/sector.html"),
    Path("static/app.js"),
    Path("static/single.js"),
    Path("static/sector.js"),
    Path("static/style.css"),
    Path("overnight_bt/app.py"),
    Path("overnight_bt/single_stock.py"),
    Path("overnight_bt/sector_dashboard.py"),
)
PROJECT_README_PHRASES = (
    "TUSHARE_TOKEN",
    "scripts/build_universe_snapshot.py",
    "scripts/sync_tushare_bundle.py",
    "scripts/build_processed_data.py",
    "python -m uvicorn overnight_bt.app:app",
    "/sector",
)


def _detect_project_layout(root: Path) -> bool:
    return (root / "overnight_bt").exists() and (root / "static").exists()


def _build_project_extra_issues(root: Path) -> list[str]:
    issues: list[str] = []
    for rel_path in PROJECT_EXTRA_PATHS:
        if not (root / rel_path).exists():
            issues.append(f"缺少项目交付文件: {rel_path.as_posix()}")

    readme_path = root / "README.md"
    readme_text = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    for phrase in PROJECT_README_PHRASES:
        if phrase not in readme_text:
            issues.append(f"README 缺少关键说明: {phrase}")

    docs_dir = root / "docs"
    if docs_dir.exists() and len(list(docs_dir.glob("*.md"))) < 4:
        issues.append("docs/ 文档数量不足，至少应包含模板与正式说明文档")
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
