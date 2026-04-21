from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from shutil import copy2

import pandas as pd


DIRECT_INDUSTRY_THEME_TAGS: dict[str, str] = {
    "半导体": "ai_chip",
    "元器件": "ai_pcb_electronics",
    "通信设备": "ai_cpo_connectivity",
    "电气设备": "new_energy_and_grid",
    "电器仪表": "grid_automation",
    "铜": "nonferrous_metals",
    "铝": "nonferrous_metals",
    "黄金": "precious_metals",
    "小金属": "rare_metal_battery",
    "铅锌": "nonferrous_metals",
    "新型电力": "new_energy_power",
}

KEYWORD_THEME_TAGS: dict[str, tuple[str, ...]] = {
    "ai_compute_platform": (
        "工业富联",
        "浪潮信息",
        "中科曙光",
        "紫光股份",
        "海康威视",
        "大华股份",
        "协创数据",
    ),
    "ai_software_data": (
        "科大讯飞",
        "润泽科技",
        "中科星图",
        "南网数字",
    ),
    "robotics_automation": (
        "汇川技术",
        "拓普集团",
        "三花智控",
        "机器人",
        "埃斯顿",
        "大族激光",
        "大族数控",
        "华工科技",
        "罗博特科",
        "先导智能",
        "迈为股份",
        "晶盛机电",
        "中控技术",
    ),
    "ai_liquidcooling_power": (
        "英维克",
        "麦格米特",
        "中际旭创",
        "新易盛",
        "天孚通信",
        "光迅科技",
        "沪电股份",
        "胜宏科技",
        "景旺电子",
        "生益科技",
        "生益电子",
        "深南电路",
        "鹏鼎控股",
        "东山精密",
        "立讯精密",
    ),
    "new_energy_battery_pv": (
        "阳光电源",
        "宁德时代",
        "亿纬锂能",
        "国轩高科",
        "恩捷股份",
        "中伟新材",
        "湖南裕能",
        "隆基绿能",
        "晶科能源",
        "大全能源",
        "阿特斯",
        "德业股份",
        "特变电工",
        "金风科技",
        "比亚迪",
        "赛力斯",
    ),
    "metals_resources": (
        "华友钴业",
        "洛阳钼业",
        "紫金矿业",
        "赣锋锂业",
        "天齐锂业",
        "中矿资源",
        "中国稀土",
        "北方稀土",
        "山金国际",
        "湖南黄金",
        "中金黄金",
        "山东黄金",
        "赤峰黄金",
        "云铝股份",
        "中国铝业",
        "神火股份",
        "天山铝业",
        "铜陵有色",
        "江西铜业",
        "云南铜业",
        "白银有色",
    ),
    "power_grid": (
        "国电南瑞",
        "许继电气",
        "平高电气",
        "思源电气",
        "中国西电",
        "正泰电器",
        "上海电气",
        "东方电气",
    ),
}


@dataclass(frozen=True)
class ThemeUniverseBuildResult:
    snapshot_path: str
    processed_dir: str
    selected_count: int
    selected_symbols: list[str]


def build_theme_focus_frame(snapshot_df: pd.DataFrame, top_k: int | None = None) -> pd.DataFrame:
    work = snapshot_df.copy()
    work["symbol"] = work["symbol"].astype(str).str.strip().str.zfill(6)
    if "ts_code" in work.columns:
        work["ts_code"] = work["ts_code"].astype(str).str.strip()
    work["industry"] = work["industry"].fillna("").astype(str).str.strip()
    work["name"] = work["name"].fillna("").astype(str).str.strip()

    theme_tags: list[str] = []
    reasons: list[str] = []
    for _, row in work.iterrows():
        tags: set[str] = set()
        match_reasons: list[str] = []
        industry = row["industry"]
        name = row["name"]

        if industry in DIRECT_INDUSTRY_THEME_TAGS:
            tags.add(DIRECT_INDUSTRY_THEME_TAGS[industry])
            match_reasons.append(f"industry:{industry}")

        for tag, keywords in KEYWORD_THEME_TAGS.items():
            hits = [keyword for keyword in keywords if keyword in name]
            if hits:
                tags.add(tag)
                match_reasons.append(f"name:{'/'.join(hits)}")

        theme_tags.append(";".join(sorted(tags)))
        reasons.append(";".join(match_reasons))

    work["theme_tags"] = theme_tags
    work["filter_reason"] = reasons
    filtered = work[work["theme_tags"].astype(str).str.len() > 0].copy()
    filtered["total_mv"] = pd.to_numeric(filtered["total_mv"], errors="coerce")
    filtered = filtered.sort_values(["total_mv", "symbol"], ascending=[False, True]).reset_index(drop=True)
    if top_k is not None and int(top_k) > 0:
        filtered = filtered.head(int(top_k)).reset_index(drop=True)
    return filtered


def write_theme_focus_outputs(
    snapshot_df: pd.DataFrame,
    processed_source_dir: Path,
    out_snapshot_path: Path,
    out_processed_dir: Path,
    top_k: int | None = None,
) -> ThemeUniverseBuildResult:
    filtered = build_theme_focus_frame(snapshot_df, top_k=top_k)
    out_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    out_processed_dir.mkdir(parents=True, exist_ok=True)
    filtered.to_csv(out_snapshot_path, index=False, encoding="utf-8-sig")

    selected_symbols = filtered["symbol"].astype(str).tolist()
    for symbol in selected_symbols:
        source_path = processed_source_dir / f"{symbol}.csv"
        if source_path.exists():
            copy2(source_path, out_processed_dir / source_path.name)

    manifest_path = processed_source_dir / "processing_manifest.csv"
    if manifest_path.exists():
        manifest = pd.read_csv(manifest_path, encoding="utf-8-sig")
        manifest["symbol"] = manifest["symbol"].astype(str)
        manifest = manifest[manifest["symbol"].isin(selected_symbols)].copy()
        manifest.to_csv(out_processed_dir / "processing_manifest.csv", index=False, encoding="utf-8-sig")

    return ThemeUniverseBuildResult(
        snapshot_path=str(out_snapshot_path),
        processed_dir=str(out_processed_dir),
        selected_count=len(filtered),
        selected_symbols=selected_symbols,
    )
