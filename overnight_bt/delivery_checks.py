from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence


DEFAULT_REQUIRED_SECTIONS = ("准备工作", "启动方式", "复现结果")
DEFAULT_REQUIRED_PATHS = (
    Path("README.md"),
    Path("docs/data-dictionary-template.md"),
    Path("docs/indicator-documentation-template.md"),
)


def extract_markdown_headings(markdown_text: str) -> list[str]:
    headings: list[str] = []
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        heading = stripped.lstrip("#").strip()
        if heading:
            headings.append(heading)
    return headings


def check_missing_readme_sections(readme_text: str, required_sections: Sequence[str]) -> list[str]:
    headings = set(extract_markdown_headings(readme_text))
    return [section for section in required_sections if section not in headings]


def check_missing_required_paths(root: Path, required_paths: Sequence[Path]) -> list[Path]:
    return [path for path in required_paths if not (root / path).exists()]


def build_delivery_report(
    root: Path,
    readme_path: Path,
    required_sections: Sequence[str],
    required_paths: Sequence[Path],
) -> list[str]:
    issues: list[str] = []
    resolved_readme = root / readme_path
    if not resolved_readme.exists():
        issues.append(f"缺少 README 文件: {readme_path}")
    else:
        missing_sections = check_missing_readme_sections(
            resolved_readme.read_text(encoding="utf-8"),
            required_sections,
        )
        if missing_sections:
            issues.append(f"README 缺少章节: {', '.join(missing_sections)}")

    missing_paths = check_missing_required_paths(root, required_paths)
    if missing_paths:
        issues.append(
            "缺少交付必备文件: " + ", ".join(path.as_posix() for path in missing_paths)
        )

    return issues


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查回测项目交付前的基础文档约束。")
    parser.add_argument("--root", default=".", help="项目根目录，默认当前目录。")
    parser.add_argument("--readme", default="README.md", help="README 相对路径。")
    parser.add_argument(
        "--section",
        dest="sections",
        action="append",
        help="README 必须包含的章节标题，可重复传入。",
    )
    parser.add_argument(
        "--require-path",
        dest="required_paths",
        action="append",
        help="必须存在的相对路径，可重复传入。",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    readme_path = Path(args.readme)
    required_sections = tuple(args.sections or DEFAULT_REQUIRED_SECTIONS)
    required_paths = tuple(Path(path) for path in (args.required_paths or DEFAULT_REQUIRED_PATHS))

    issues = build_delivery_report(root, readme_path, required_sections, required_paths)
    if issues:
        print("交付检查未通过：")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("交付检查通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
