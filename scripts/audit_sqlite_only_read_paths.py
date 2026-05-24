from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("overnight_bt", "scripts", "static")
EXCLUDE_PARTS = {"__pycache__", ".pytest_cache", ".git", "node_modules"}
LEGACY_PATTERNS: dict[str, re.Pattern[str]] = {
    "data_bundle": re.compile(r"data_bundle"),
    "processed_csv": re.compile(r"processed_qfq|processed-dir|processed_dir"),
    "pandas_read_csv": re.compile(r"pd\.read_csv|read_csv\("),
    "legacy_yaml": re.compile(r"configs/paper_accounts|\.ya?ml|safe_load"),
    "legacy_feature_fallback": re.compile(r"legacy_feature_fallback|legacy_db_path|DISABLE_LEGACY_FALLBACK"),
    "legacy_template_db": re.compile(r"stock_pool_templates\.sqlite"),
}


@dataclass(frozen=True)
class Finding:
    category: str
    path: str
    line: int
    text: str


def _iter_files(root: Path, scan_dirs: Iterable[str]) -> Iterable[Path]:
    for scan_dir in scan_dirs:
        base = root / scan_dir
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if any(part in EXCLUDE_PARTS for part in path.parts):
                continue
            if path.suffix.lower() not in {".py", ".sh", ".js", ".html", ".cmd"}:
                continue
            yield path


def audit(root: Path = ROOT, scan_dirs: Iterable[str] = SCAN_DIRS) -> list[Finding]:
    findings: list[Finding] = []
    for path in _iter_files(root, scan_dirs):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        rel = path.relative_to(root).as_posix()
        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            for category, pattern in LEGACY_PATTERNS.items():
                if pattern.search(stripped):
                    findings.append(Finding(category=category, path=rel, line=line_no, text=stripped[:240]))
    return findings


def _summary(findings: list[Finding]) -> dict[str, object]:
    categories: dict[str, int] = {}
    files: dict[str, int] = {}
    for item in findings:
        categories[item.category] = categories.get(item.category, 0) + 1
        files[item.path] = files.get(item.path, 0) + 1
    return {"finding_count": len(findings), "categories": categories, "files": files}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit legacy read paths that must be reviewed before SQLite-only cutover.")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    parser.add_argument("--fail-on-legacy", action="store_true", help="Exit 1 when findings are present")
    parser.add_argument("--root", default=str(ROOT), help="Repository root")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    findings = audit(root=root)
    payload = {
        "summary": _summary(findings),
        "findings": [item.__dict__ for item in findings],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        summary = payload["summary"]
        print(f"legacy_read_path_findings={summary['finding_count']}")
        for category, count in sorted(summary["categories"].items()):
            print(f"{category}: {count}")
        for item in findings[:200]:
            print(f"{item.path}:{item.line}: [{item.category}] {item.text}")
    return 1 if args.fail_on_legacy and findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
