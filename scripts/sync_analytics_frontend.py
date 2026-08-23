#!/usr/bin/env python3
"""同步 Analytics 前端衍生資料，避免年份與總題數硬編碼過期。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "考古題網站"
DEFAULT_ANALYTICS = Path("/tmp/analytics.json")
HTML = SITE / "analytics.html"
CHART_JS = SITE / "analytics-chart.js"
CHART_DATA = SITE / "analytics-chart-data.js"
GEN = SITE / "_gen_data.js"


def sync_text(text: str, stats: dict) -> str:
    first_year = min(stats["years"])
    last_year = max(stats["years"])
    year_range = f"{first_year}–{last_year}"
    total = stats["total_questions"]
    choice = stats["choice_questions"]
    essay = stats["essay_questions"]
    categories = stats["categories"]
    subjects = stats["subjects"]

    replacements = [
        (r'data-target="\d+">0</span></div></div>', None),
    ]
    # 依卡片標籤精準更新，避免碰到其他 data-target。
    for label, value in [
        ("總題數", total),
        ("選擇題", choice),
        ("申論題", essay),
        ("類科", categories),
        ("科目", subjects),
    ]:
        pattern = (
            rf'(<div class="label">{re.escape(label)}</div><div><span class="num" '
            rf'data-target=")\d+(">0</span>)'
        )
        text, n = re.subn(pattern, rf"\g<1>{value}\g<2>", text)
        if n != 1:
            raise RuntimeError(f"無法唯一更新 Analytics 卡片：{label}（匹配 {n}）")

    text, n = re.subn(
        r'(<div class="label">年份</div><div><span class="num">)\d+–\d+(</span>)',
        rf"\g<1>{year_range}\g<2>",
        text,
    )
    if n != 1:
        raise RuntimeError(f"無法唯一更新年份卡片（匹配 {n}）")

    text, n = re.subn(
        r'(id="filterTag">全部類科 · )[\d,]+( 題</span>)',
        rf"\g<1>{total:,}\g<2>",
        text,
    )
    if n != 1:
        raise RuntimeError(f"無法唯一更新 filterTag（匹配 {n}）")

    text, n = re.subn(
        r'<span class="hint">資料更新至 \d+ 年(?:第二次考試)?</span>',
        f'<span class="hint">資料更新至 {last_year} 年</span>',
        text,
    )
    if n != 1:
        raise RuntimeError(f"無法唯一更新資料年份提示（匹配 {n}）")

    text, n = re.subn(
        r'(<div class="card-title"><h3>各年度出題數</h3><span class="badge">)\d+–\d+(</span>)',
        rf"\g<1>{year_range}\g<2>",
        text,
    )
    if n != 1:
        raise RuntimeError(f"無法唯一更新年度圖 badge（匹配 {n}）")

    text, n = re.subn(
        r'(<div class="card-title"><h3>趨勢比較</h3><span class="badge">)\d+–\d+(</span>)',
        rf"\g<1>{year_range}\g<2>",
        text,
    )
    if n != 1:
        raise RuntimeError(f"無法唯一更新趨勢 badge（匹配 {n}）")

    text = re.sub(r'近[一二三四五六七八九十\d]+年每年命題量變化', '各年度命題量變化', text)
    return text


def sync_chart_js(text: str) -> str:
    text, n = re.subn(
        r'return \{ year: ALL_YEAR, donut: ALL_DONUT, total: \d+ \};',
        'return { year: ALL_YEAR, donut: ALL_DONUT, total: STATS.total };',
        text,
    )
    if n == 0 and 'total: STATS.total' not in text:
        raise RuntimeError("找不到 Analytics 全站總題數硬編碼")
    return text


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--analytics", type=Path, default=DEFAULT_ANALYTICS)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()

    payload = json.loads(args.analytics.read_text(encoding="utf-8"))
    stats = payload["stats"]

    html_before = HTML.read_text(encoding="utf-8")
    chart_before = CHART_JS.read_text(encoding="utf-8")
    html_after = sync_text(html_before, stats)
    chart_after = sync_chart_js(chart_before)

    with tempfile.TemporaryDirectory() as td:
        generated = Path(td) / "analytics-chart-data.js"
        subprocess.run(
            ["node", str(GEN), str(args.analytics), str(generated)],
            check=True,
        )
        data_after = generated.read_text(encoding="utf-8")

    if args.check:
        problems = []
        if html_before != html_after:
            problems.append("analytics.html 尚未同步")
        if chart_before != chart_after:
            problems.append("analytics-chart.js 尚未同步")
        if not CHART_DATA.exists() or CHART_DATA.read_text(encoding="utf-8") != data_after:
            problems.append("analytics-chart-data.js 尚未同步")
        if problems:
            raise SystemExit("；".join(problems))
        print("Analytics 前端與資料庫一致")
        return 0

    HTML.write_text(html_after, encoding="utf-8")
    CHART_JS.write_text(chart_after, encoding="utf-8")
    CHART_DATA.write_text(data_after, encoding="utf-8")
    print(
        f"Analytics 已同步：{stats['total_questions']:,} 題，"
        f"{min(stats['years'])}–{max(stats['years'])} 年"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
