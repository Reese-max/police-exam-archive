#!/usr/bin/env python3
"""驗證所有公開表面的語料題數與品質分母可追溯至 quality_summary.json。

受管表面：
  - 考古題庫/quality_summary.json     （artifact 本身；本腳本重建比對）
  - 考古題庫/dataset_manifest.json    （counts / coverage 欄位）
  - README.md                          （corpus-stats / corpus-quality 區塊與 scope 說明）
  - 考古題網站/quiz.html               （corpus-stats 區塊）
  - 考古題網站/search.html             （由 loadIndex().stats.total 動態顯示）
  - 考古題網站/index.html / search.html / quiz.html（可見的完整題庫與本頁範圍）
  - 考古題網站/data/home-stats.json    （內軌 17 類科投影，由 build_home_stats.py 產生）
  - 考古題網站/analytics.html          （統計卡片 data-target 與篩選提示）
  - 考古題網站/analytics-chart-data.js （STATS 常數）
  - 考古題網站/analytics-chart-bundle.js（實際載入的 code/data pair）

用法:
    python scripts/check_corpus_claims.py          # CI 檢查模式
    python scripts/check_corpus_claims.py --write  # 重建 artifact 並重填自有表面
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_quality_summary import (  # noqa: E402
    build_summary,
    find_git_repo_root,
    render_summary,
    semantic_diff,
    write_summary,
)
from scripts.sync_analytics_frontend import chart_bundle  # noqa: E402

DATA_DIR_NAME = "考古題庫"
SITE_DIR_NAME = "考古題網站"


@dataclass
class Finding:
    path: str
    expected: str
    actual: str

    def __str__(self) -> str:
        return f"{self.path}: expected {self.expected}, found {self.actual}"


# ── 受管區塊（marker region）──────────────────────────────

def _region_regex(name: str, syntax: str) -> re.Pattern:
    if syntax == "html":
        begin = r"<!--\s*" + name + r":begin[^\n]*-->"
        end = r"<!--\s*" + name + r":end[^\n]*-->"
    else:
        begin = r"//\s*" + name + r":begin[^\n]*"
        end = r"//\s*" + name + r":end[^\n]*"
    return re.compile(
        rf"(^[ \t]*{begin}\n)(.*?)(^[ \t]*{end}[^\n]*)$",
        re.DOTALL | re.MULTILINE,
    )


def _check_region(
    text: str, name: str, syntax: str, expected_body: str, path: str
) -> Finding | None:
    if text.count(f"{name}:begin") != 1 or text.count(f"{name}:end") != 1:
        return Finding(
            path, f"{name} 受管區塊 markers 各恰一組", "markers 數量異常"
        )
    m = _region_regex(name, syntax).search(text)
    if not m:
        return Finding(path, f"{name} 受管區塊", "markers 不存在")
    actual = m.group(2).strip("\n")
    if actual != expected_body.strip("\n"):
        return Finding(path, expected_body.strip("\n"), actual)
    return None


def _fill_region(text: str, name: str, syntax: str, body: str) -> str:
    pattern = _region_regex(name, syntax)
    m = pattern.search(text)
    if not m:
        raise RuntimeError(f"找不到受管區塊 markers：{name}（{syntax}）")
    return text[: m.start()] + m.group(1) + body.strip("\n") + "\n" + m.group(3) + text[m.end():]


# ── 各表面的期望內容 ─────────────────────────────────────

def render_readme_inventory(summary: dict) -> str:
    c = summary["counts"]
    cov = summary["coverage"]
    year_span = (
        f"{cov['first_year']}-{cov['last_year']} 年"
        f"（{len(cov['years'])} 年）"
    )
    return "\n".join([
        "| 項目 | 數量 |",
        "|------|------|",
        f"| 學系/類別 | {c['categories']} 個 |",
        f"| 年份 | {year_span} |",
        f"| 科目 | {c['subjects']} 個 |",
        f"| JSON 檔案 | {c['json_files']:,} 個（非重複） |",
        f"| 重複副本 | {c['duplicate_files']:,} 份"
        f"（共 {c['duplicate_questions']:,} 題，不計入題數） |",
        f"| 選擇題 | {c['choice']:,} 題 |",
        f"| 申論題 | {c['essay']:,} 題 |",
        f"| 總題數 | {c['questions']:,} 題 |",
    ])


def _pct(rate) -> str:
    if rate is None:
        return "n/a"
    return f"{rate * 100:.2f}".rstrip("0").rstrip(".") + "%"


def render_readme_quality(summary: dict) -> str:
    c = summary["counts"]
    q = summary["quality"]
    ly = summary["coverage"]["last_year"]
    ly_choice = summary["by_year"].get(str(ly), {}).get("choice", 0)
    img = summary["image_placeholders"]["choice_questions"]
    oc = q["option_completeness"]
    av = q["answer_validity"]
    search = summary["projections"]["search"]["stats"]
    home = summary["projections"]["site"]
    analytics = summary["projections"]["analytics"]["stats"]
    return "\n".join([
        f"- **選項完整率**: {oc['numerator']:,}/{oc['denominator']:,}"
        f" = {_pct(oc['rate'])}",
        f"- **答案合法率**: {av['numerator']:,}/{av['denominator']:,}"
        f" = {_pct(av['rate'])}",
        f"- **驗證範圍**: {c['json_files']:,} 份非重複試題 JSON、"
        f"{c['choice']:,} 道選擇題（含 {ly} 年 {ly_choice:,} 題；另有 "
        f"{c['duplicate_files']:,} 份重複副本共 "
        f"{c['duplicate_questions']:,} 題另行列出，不混入唯一題數）",
        f"- **Canonical scope**: 只排除 `metadata._is_duplicate=true`；"
        f"{c['questions']:,} 題（{c['choice']:,} 選擇 / {c['essay']:,} 申論）、"
        f"{c['categories']} 類科",
        f"- **Search scope**: 同時排除頂層與 `metadata._is_duplicate=true`；"
        f"由 `loadIndex().stats.total` 動態顯示，離線生成值為 "
        f"{search['total']:,} 題（{search['choice']:,} 選擇 / "
        f"{search['essay']:,} 申論）",
        f"- **Homepage scope**: 內軌 {home['category_count']} 類科投影；"
        f"{home['question_count']:,} 題",
        f"- **Analytics scope**: 與 canonical 相同；"
        f"{analytics['total']:,} 題、{analytics['categories']} 類科",
        f"- **圖片佔位題**: {img} 題以 `[圖片選項]` 佔位，"
        "僅驗證選項鍵存在（詳見下方已知限制）",
        "- **統計基準**: `考古題庫/quality_summary.json`"
        "（含資料指紋與納入/排除規則）",
    ])


def render_quiz_block(summary: dict) -> str:
    choice = summary["projections"]["search"]["stats"]["choice"]
    return (
        "/* ===== 真實題庫（minisearch + search-engine.js，"
        f"搜尋索引排除頂層與 metadata 重複旗標後含 "
        f"{choice:,} 道選擇題） ===== */"
    )


def _load_json(path: Path):
    """回傳 (obj, None) 或 (None, 錯誤訊息)。"""
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        return None, str(e)


def _read_text(path: Path) -> str:
    """正規化 CRLF/CR（含 Windows 測試寫入產生的 CRCRLF）。"""
    text = path.read_bytes().decode("utf-8")
    return re.sub(r"\r+\n", "\n", text).replace("\r", "\n")


def _check_inline_patterns(
    text: str, patterns: list[tuple[str, str]], path: str
) -> list[Finding]:
    """比對行內數值宣告：每個 pattern 需存在且所有匹配皆等於期望值。"""
    findings = []
    for pattern, expected in patterns:
        matches = re.findall(pattern, text)
        if not matches:
            findings.append(Finding(path, expected, "找不到該句"))
        else:
            for m in matches:
                if m != expected:
                    findings.append(Finding(path, expected, m))
    return findings


# ── 個別表面檢查 ─────────────────────────────────────────

def _check_artifact(root: Path, summary: dict) -> list[Finding]:
    path = root / DATA_DIR_NAME / "quality_summary.json"
    data_dir = root / DATA_DIR_NAME
    rel = f"{DATA_DIR_NAME}/quality_summary.json"
    if not path.exists():
        return [Finding(rel, "已提交的品質摘要", "檔案不存在")]
    committed, err = _load_json(path)
    if err:
        return [Finding(rel, "有效 JSON", err)]
    return [
        Finding(f"{rel}:{p}", e, a)
        for p, e, a in semantic_diff(
            summary,
            committed,
            repo_root=find_git_repo_root(data_dir),
            data_dir=data_dir,
        )
    ]


def _readme_expected_patterns(summary: dict) -> list[tuple[str, str]]:
    """README 內需與 artifact 一致的行內數值。(regex, 期望完整字串)。"""
    cov = summary["coverage"]
    fy, ly = cov["first_year"], cov["last_year"]
    sv = summary["special_values"]
    img = summary["image_placeholders"]["choice_questions"]
    return [
        (
            r"涵蓋 \d+-\d+ 年（\d+-\d+）",
            f"涵蓋 {fy}-{ly} 年（{fy + 1911}-{ly + 1911}）",
        ),
        (
            r"均給分（[\d,]+ 題）",
            f"均給分（{sv['free_score_questions']:,} 題）",
        ),
        (
            r"皆給分（[\d,]+ 題）",
            f"皆給分（{sv['multi_answer_questions']:,} 題）",
        ),
        (
            r"無法文字化（[\d,]+ 題）",
            f"無法文字化（{img:,} 題）",
        ),
        (
            r"圖片題（[\d,]+ 題）",
            f"圖片題（{img:,} 題）",
        ),
        (
            r"(?:查詢速度依執行環境而異（目前 [\d,]+ 題全文搜尋）。|"
            r"全文搜尋題數由載入後的 `search-index\.json` "
            r"`stats\.total` 動態顯示；搜尋同時排除頂層與 metadata "
            r"重複旗標。)",
            "全文搜尋題數由載入後的 `search-index.json` "
            "`stats.total` 動態顯示；搜尋同時排除頂層與 metadata "
            "重複旗標。",
        ),
    ]


def _check_readme(root: Path, summary: dict) -> list[Finding]:
    path = root / "README.md"
    if not path.exists():
        return [Finding("README.md", "README", "檔案不存在")]
    text = _read_text(path)
    findings = []
    for name, body in (
        ("corpus-stats", render_readme_inventory(summary)),
        ("corpus-quality", render_readme_quality(summary)),
    ):
        f = _check_region(text, name, "html", body, "README.md")
        if f:
            findings.append(f)
    findings += _check_inline_patterns(
        text, _readme_expected_patterns(summary), "README.md"
    )
    return findings


def _check_quiz(root: Path, summary: dict) -> list[Finding]:
    path = root / SITE_DIR_NAME / "quiz.html"
    rel = f"{SITE_DIR_NAME}/quiz.html"
    if not path.exists():
        return [Finding(rel, "quiz.html", "檔案不存在")]
    text = _read_text(path)
    f = _check_region(
        text, "corpus-stats", "js", render_quiz_block(summary), rel
    )
    return [f] if f else []


def _check_search(root: Path, summary: dict) -> list[Finding]:
    path = root / SITE_DIR_NAME / "search.html"
    rel = f"{SITE_DIR_NAME}/search.html"
    if not path.exists():
        return [Finding(rel, "search.html", "檔案不存在")]
    text = _read_text(path)
    findings = []
    for expected in (
        "SearchEngine.loadIndex().then(function(stats){",
        "document.getElementById('statTotal').textContent=stats.total.toLocaleString();",
    ):
        if expected not in text:
            findings.append(Finding(rel, expected, "找不到動態搜尋統計契約"))
    if re.search(r"跨(?:部門|類科)搜尋\s*[\d,]+\s*道(?:歷年)?警察特考考古題", text):
        findings.append(
            Finding(rel, "不含固定總題數的搜尋說明", "找到固定搜尋題數")
        )
    return findings


def _check_search_index(root: Path, summary: dict) -> list[Finding]:
    """Pages 產物若存在就核對；repo 不提交大型 search index 時允許缺檔。"""
    path = root / SITE_DIR_NAME / "data" / "search-index.json"
    rel = f"{SITE_DIR_NAME}/data/search-index.json"
    if not path.exists():
        return []
    current, err = _load_json(path)
    if err:
        return [Finding(rel, "有效 JSON", err)]
    expected = summary["projections"]["search"]["stats"]
    actual = current.get("stats") if isinstance(current, dict) else None
    return [
        Finding(f"{rel}:stats.{key}", repr(value), repr((actual or {}).get(key)))
        for key, value in expected.items()
        if (actual or {}).get(key) != value
    ]


SCOPE_PAGES = ("index.html", "search.html", "quiz.html")


def render_visible_scope(summary: dict, page: str) -> str:
    """完整語料與本頁投影並列；不把完整總數冒充搜尋或練習池大小。"""
    counts = summary["counts"]
    canonical = (
        f"完整題庫：{counts['choice']:,} 道選擇題、"
        f"{counts['essay']:,} 道申論題，共 {counts['questions']:,} 題。"
    )
    search = summary["projections"]["search"]["stats"]
    home = summary["projections"]["site"]
    scopes = {
        "index.html": (
            f"本頁呈現內軌 {home['category_count']} 類科、"
            f"{home['question_count']:,} 題。"
        ),
        "search.html": (
            f"本頁依搜尋排除規則索引 {search['total']:,} 題；"
            "重複試卷排除範圍見統計依據。"
        ),
        "quiz.html": f"本頁練習題池包含 {search['choice']:,} 道選擇題。",
    }
    return (
        '<p class="lead corpus-scope">' + canonical + "<br>" + scopes[page]
        + ' <a href="https://github.com/Reese-max/police-exam-archive/blob/master/'
        + '考古題庫/quality_summary.json">統計依據</a></p>\n'
    )


def _check_visible_scopes(root: Path, summary: dict) -> list[Finding]:
    findings = []
    for page in SCOPE_PAGES:
        path = root / SITE_DIR_NAME / page
        rel = f"{SITE_DIR_NAME}/{page}"
        if not path.exists():
            findings.append(Finding(rel, "完整題庫與本頁範圍", "檔案不存在"))
            continue
        finding = _check_region(
            _read_text(path), "corpus-scope", "html",
            render_visible_scope(summary, page), rel,
        )
        if finding:
            findings.append(finding)
    return findings


_MANIFEST_COUNT_KEYS = (
    "json_files", "questions", "choice", "essay", "categories", "subjects",
)


def _check_manifest(root: Path, summary: dict) -> list[Finding]:
    path = root / DATA_DIR_NAME / "dataset_manifest.json"
    rel = f"{DATA_DIR_NAME}/dataset_manifest.json"
    if not path.exists():
        return [Finding(rel, "dataset_manifest.json", "檔案不存在")]
    manifest, err = _load_json(path)
    if err:
        return [Finding(rel, "有效 JSON", err)]
    findings = []
    counts = manifest.get("counts") or {}
    for key in _MANIFEST_COUNT_KEYS:
        expected = summary["counts"][key]
        if counts.get(key) != expected:
            findings.append(
                Finding(rel, f"counts.{key}={expected}", repr(counts.get(key)))
            )
    coverage = manifest.get("coverage") or {}
    cov = summary["coverage"]
    for key, expected in (
        ("first_year", cov["first_year"]),
        ("last_year", cov["last_year"]),
        ("years", cov["years"]),
    ):
        if coverage.get(key) != expected:
            findings.append(
                Finding(rel, f"coverage.{key}={expected!r}", repr(coverage.get(key)))
            )
    return findings


def _check_home_stats(root: Path, summary: dict) -> list[Finding]:
    path = root / SITE_DIR_NAME / "data" / "home-stats.json"
    rel = f"{SITE_DIR_NAME}/data/home-stats.json"
    if not path.exists():
        return [Finding(rel, "home-stats.json", "檔案不存在")]
    current, err = _load_json(path)
    if err:
        return [Finding(rel, "有效 JSON", err)]
    expected = summary["projections"]["site"]
    return [
        Finding(f"{rel}:{p}", e, a)
        for p, e, a in semantic_diff(expected, current)
    ]


def _check_analytics_html(root: Path, summary: dict) -> list[Finding]:
    path = root / SITE_DIR_NAME / "analytics.html"
    rel = f"{SITE_DIR_NAME}/analytics.html"
    if not path.exists():
        return [Finding(rel, "analytics.html", "檔案不存在")]
    text = _read_text(path)
    stats = summary["projections"]["analytics"]["stats"]
    cov = summary["coverage"]
    findings = []

    for label, value in (
        ("總題數", stats["total"]),
        ("選擇題", stats["choice"]),
        ("申論題", stats["essay"]),
        ("類科", stats["categories"]),
        ("科目", stats["subjects"]),
    ):
        m = re.search(
            rf'<div class="label">{re.escape(label)}</div><div>'
            rf'<span class="num" data-target="(\d+)">',
            text,
        )
        if not m:
            findings.append(Finding(rel, f"{label} data-target={value}", "找不到卡片"))
        elif int(m.group(1)) != value:
            findings.append(
                Finding(rel, f"{label} data-target={value}", m.group(1))
            )

    m = re.search(
        r'<div class="label">年份</div><div><span class="num">(\d+)–(\d+)</span>',
        text,
    )
    expected_span = (str(cov["first_year"]), str(cov["last_year"]))
    if not m:
        findings.append(Finding(rel, f"年份卡片 {expected_span[0]}–{expected_span[1]}", "找不到年份卡片"))
    elif (m.group(1), m.group(2)) != expected_span:
        findings.append(
            Finding(rel, f"年份卡片 {expected_span[0]}–{expected_span[1]}", m.group(0))
        )

    m = re.search(r'id="filterTag">全部類科 · ([\d,]+) 題', text)
    if not m:
        findings.append(Finding(rel, f"filterTag={stats['total']:,} 題", "找不到 filterTag"))
    elif m.group(1) != f"{stats['total']:,}":
        findings.append(
            Finding(rel, f"filterTag={stats['total']:,} 題", m.group(0))
        )

    m = re.search(r'<span class="hint">資料更新至 (\d+) 年', text)
    if not m:
        findings.append(Finding(rel, f"資料更新至 {cov['last_year']} 年", "找不到 hint"))
    elif int(m.group(1)) != cov["last_year"]:
        findings.append(
            Finding(rel, f"資料更新至 {cov['last_year']} 年", m.group(0))
        )

    badges = re.findall(
        r'<h3>(?:各年度出題數|趨勢比較)</h3><span class="badge">(\d+)–(\d+)',
        text,
    )
    expected_span = (str(cov["first_year"]), str(cov["last_year"]))
    if len(badges) != 2:
        findings.append(Finding(rel, f"2 個年份 badge {expected_span}", repr(badges)))
    elif any(tuple(b) != expected_span for b in badges):
        findings.append(Finding(rel, repr(expected_span), repr(badges)))
    return findings


def _check_chart_data(root: Path, summary: dict) -> list[Finding]:
    path = root / SITE_DIR_NAME / "analytics-chart-data.js"
    rel = f"{SITE_DIR_NAME}/analytics-chart-data.js"
    if not path.exists():
        return [Finding(rel, "analytics-chart-data.js", "檔案不存在")]
    text = _read_text(path)
    m = re.search(r"const STATS = (\{.*?\});", text)
    if not m:
        return [Finding(rel, "const STATS = {...}", "找不到 STATS")]
    try:
        stats = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        return [Finding(rel, "STATS 為有效 JSON", str(e))]
    stats_expected = summary["projections"]["analytics"]["stats"]
    cov = summary["coverage"]
    expected = {
        "total": stats_expected["total"],
        "choice": stats_expected["choice"],
        "essay": stats_expected["essay"],
        "categories": stats_expected["categories"],
        "subjects": stats_expected["subjects"],
        "firstYear": cov["first_year"],
        "lastYear": cov["last_year"],
        "yearCount": len(cov["years"]),
    }
    return [
        Finding(rel, f"STATS.{k}={v}", repr(stats.get(k)))
        for k, v in expected.items()
        if stats.get(k) != v
    ]


def _check_chart_bundle(root: Path, summary: dict) -> list[Finding]:
    site = root / SITE_DIR_NAME
    bundle_path = site / "analytics-chart-bundle.js"
    data_path = site / "analytics-chart-data.js"
    chart_path = site / "analytics-chart.js"
    rel = f"{SITE_DIR_NAME}/analytics-chart-bundle.js"
    missing = [
        path.name for path in (bundle_path, data_path, chart_path)
        if not path.exists()
    ]
    if missing:
        return [Finding(rel, "完整 analytics code/data pair", repr(missing))]
    expected = chart_bundle(_read_text(data_path), _read_text(chart_path))
    actual = _read_text(bundle_path)
    if actual != expected:
        return [Finding(rel, "由目前 chart-data + chart 生成的 bundle", "內容或 digest 漂移")]
    html_path = site / "analytics.html"
    if not html_path.exists() or '<script src="analytics-chart-bundle.js"></script>' not in _read_text(html_path):
        return [Finding(rel, "analytics.html 實際載入 bundle", "找不到 script src")]
    return []


# ── 入口 ─────────────────────────────────────────────────

def check_all(root: Path, summary: dict | None = None) -> list[Finding]:
    root = Path(root)
    if summary is None:
        summary = build_summary(root / DATA_DIR_NAME)
    findings: list[Finding] = []
    findings += _check_artifact(root, summary)
    findings += _check_readme(root, summary)
    findings += _check_quiz(root, summary)
    findings += _check_search(root, summary)
    findings += _check_visible_scopes(root, summary)
    findings += _check_search_index(root, summary)
    findings += _check_manifest(root, summary)
    findings += _check_home_stats(root, summary)
    findings += _check_analytics_html(root, summary)
    findings += _check_chart_data(root, summary)
    findings += _check_chart_bundle(root, summary)
    return findings


def write_surfaces(root: Path, summary: dict) -> list[Path]:
    """重建 artifact 並重填自有的 README、頁面範圍、quiz、manifest 表面。

    先於記憶體算好所有新內容（缺 markers 會在寫檔前失敗），再落盤。
    home-stats / search-index / analytics 由各自的產生器擁有；漂移時請執行
    scripts/build_home_stats.py、scripts/build_search_index.py
    與 scripts/sync_analytics_frontend.py。
    """
    root = Path(root)

    readme = root / "README.md"
    readme_text = _read_text(readme)
    readme_text = _fill_region(
        readme_text, "corpus-stats", "html", render_readme_inventory(summary)
    )
    readme_text = _fill_region(
        readme_text, "corpus-quality", "html", render_readme_quality(summary)
    )
    for pattern, expected in _readme_expected_patterns(summary):
        readme_text = re.sub(pattern, expected, readme_text)

    quiz = root / SITE_DIR_NAME / "quiz.html"
    quiz_text = _read_text(quiz)
    quiz_text = _fill_region(
        quiz_text, "corpus-stats", "js", render_quiz_block(summary)
    )

    scope_texts = {}
    for page in SCOPE_PAGES:
        path = root / SITE_DIR_NAME / page
        text = quiz_text if page == "quiz.html" else _read_text(path)
        scope_texts[path] = _fill_region(
            text, "corpus-scope", "html", render_visible_scope(summary, page)
        )

    manifest_path = root / DATA_DIR_NAME / "dataset_manifest.json"
    manifest, err = _load_json(manifest_path)
    if err:
        raise RuntimeError(f"{manifest_path}：{err}")
    expected_counts = {
        key: summary["counts"][key] for key in _MANIFEST_COUNT_KEYS
    }
    expected_coverage = {
        "first_year": summary["coverage"]["first_year"],
        "last_year": summary["coverage"]["last_year"],
        "years": summary["coverage"]["years"],
    }
    manifest_dirty = (
        {k: (manifest.get("counts") or {}).get(k) for k in _MANIFEST_COUNT_KEYS}
        != expected_counts
        or {k: (manifest.get("coverage") or {}).get(k) for k in expected_coverage}
        != expected_coverage
    )
    manifest_text = None
    if manifest_dirty:
        if not isinstance(manifest.get("counts"), dict):
            manifest["counts"] = {}
        if not isinstance(manifest.get("coverage"), dict):
            manifest["coverage"] = {}
        manifest["counts"].update(expected_counts)
        manifest["coverage"].update(expected_coverage)
        manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
        manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"

    artifact = root / DATA_DIR_NAME / "quality_summary.json"
    write_summary(summary, artifact)
    readme.write_text(readme_text, encoding="utf-8")
    for path, text in scope_texts.items():
        path.write_text(text, encoding="utf-8")
    written = [artifact, readme, *scope_texts]
    if manifest_text is not None:
        manifest_path.write_text(manifest_text, encoding="utf-8")
        written.append(manifest_path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="驗證公開語料題數無漂移")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--write",
        action="store_true",
        help="重建 quality_summary.json 並重填 README/頁面範圍/quiz/manifest",
    )
    args = parser.parse_args()

    root = Path(args.root)
    summary = build_summary(root / DATA_DIR_NAME)

    if args.write:
        for p in write_surfaces(root, summary):
            print(f"已更新 {p.relative_to(root)}")

    findings = check_all(root, summary)
    if findings:
        print("語料統計漂移偵測失敗：")
        for f in findings:
            print(f"  {f}")
        print(
            "\n若是合法的語料更新，請依序執行：\n"
            "  python scripts/check_corpus_claims.py --write\n"
            "  python scripts/build_home_stats.py\n"
            "  python scripts/build_search_index.py\n"
            "  python scripts/build_analytics.py\n"
            "  python scripts/sync_analytics_frontend.py --analytics "
            "考古題網站/data/analytics.json\n"
            "再提交所有變更。"
        )
        return 1
    print("所有公開表徵與 quality_summary.json 一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
