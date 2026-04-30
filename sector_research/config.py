from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SubTheme:
    name: str
    keywords: list[str]


@dataclass(frozen=True)
class Theme:
    name: str
    description: str
    subthemes: list[SubTheme]


@dataclass(frozen=True)
class ThemeConfig:
    themes: list[Theme]


def load_theme_config(path: str | Path) -> ThemeConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"板块主题配置不存在: {config_path}")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    raw_themes = data.get("themes") or {}
    if not isinstance(raw_themes, dict) or not raw_themes:
        raise ValueError("主题配置必须包含非空 themes 映射")

    themes: list[Theme] = []
    for theme_name, raw_theme in raw_themes.items():
        raw_theme = raw_theme or {}
        raw_subthemes = raw_theme.get("subthemes") or {}
        if not isinstance(raw_subthemes, dict) or not raw_subthemes:
            raise ValueError(f"主题 {theme_name} 必须配置 subthemes")
        subthemes = []
        for sub_name, raw_keywords in raw_subthemes.items():
            keywords = _normalize_keywords(raw_keywords)
            if not keywords:
                raise ValueError(f"主题 {theme_name}/{sub_name} 的关键词为空")
            subthemes.append(SubTheme(name=str(sub_name).strip(), keywords=keywords))
        themes.append(
            Theme(
                name=str(theme_name).strip(),
                description=str(raw_theme.get("description") or "").strip(),
                subthemes=subthemes,
            )
        )
    return ThemeConfig(themes=themes)


def _normalize_keywords(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        raise ValueError(f"关键词必须是字符串或列表: {value!r}")
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result
