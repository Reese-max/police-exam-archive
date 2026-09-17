#!/usr/bin/env python3
"""驗證所有公開表面的語料題數與品質分母可追溯至 quality_summary.json。

受管表面：
  - 考古題庫/quality_summary.json     （artifact 本身；本腳本重建比對）
  - 考古題庫/dataset_manifest.json    （counts / coverage 欄位）
  - README.md                          （corpus-stats / corpus-quality 區塊與搜尋題數行）
  - 考古題網站/quiz.html               （corpus-stats 區塊）
  - 考古題網站/data/home-stats.json    （內軌 17 類科投影，由 build_home_stats.py 產生）
  - 考古題網站/analytics.html          （統計卡片 data-target 與篩選提示）
  - 考古題網站/analytics-chart-data.js （STATS 常數）

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
    render_summary,
    semantic_diff,
    write_summary,
)

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
    return "\n".join([
        f"- **選項完整率**: {oc['numerator']:,}/{oc['denominator']:,}"
        f" = {_pct(oc['rate'])}",
        f"- **答案合法率**: {av['numerator']:,}/{av['denominator']:,}"
        f" = {_pct(av['rate'])}",
        f"- **驗證範圍**: {c['json_files']:,} 份非重複試題 JSON、"
        f"{c['choice']:,} 道選擇題（含 {ly} 年 {ly_choice:,} 題；另有 "
        f"{c['duplicate_files']:,} 份重複副本共 "
        f"{c['duplicate_questions']:,} 題另行列出，不混入唯一題數）",
        f"- **圖片佔位題**: {img} 題以 `[圖片選項]` 佔位，"
        "僅驗證選項鍵存在（詳見下方已知限制）",
        "- **統計基準**: `考古題庫/quality_summary.json`"
        "（含資料指紋與納入/排除規則）",
    ])


def render_quiz_block(summary: dict) -> str:
    choice = summary["counts"]["choice"]
    return (
        "/* ===== 真實題庫（minisearch + search-engine.js，"
        f"搜尋索引含 {choice:,} 道非重複選擇題） ===== */"
    )


def _load_json(path: Path):
    """回傳 (obj, None) 或 (None, 錯誤訊息)。"""
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        return None, str(e)


# ── 個別表面檢查 ─────────────────────────────────────────

def _check_artifact(root: Path, summary: dict) -> list[Finding]:
    path = root / DATA_DIR_NAME / "quality_summary.json"
    rel = f"{DATA_DIR_NAME}/quality_summary.json"
    if not path.exists():
        return [Finding(rel, "已提交的品質摘要", "檔案不存在")]
    committed, err = _load_json(path)
    if err:
        return [Finding(rel, "有效 JSON", err)]
    return [
        Finding(f"{rel}:{p}", e, a)
        for p, e, a in semantic_diff(summary, committed)
    ]


def _readme_expected_patterns(summary: dict) -> list[tuple[str, str]]:
    """README 內需與 artifact 一致的行內數值。(regex, 期望完整字串)。"""
    c = summary["counts"]
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
            r"目前 [\d,]+ 題全文搜尋",
            f"目前 {c['questions']:,} 題全文搜尋",
        ),
    ]


def _check_readme(root: Path, summary: dict) -> list[Finding]:
    path = root / "README.md"
    if not path.exists():
        return [Finding("README.md", "README", "檔案不存在")]
    text = path.read_text(encoding="utf-8")
    findings = []
    for name, body in (
        ("corpus-stats", render_readme_inventory(summary)),
        ("corpus-quality", render_readme_quality(summary)),
    ):
        f = _check_region(text, name, "html", body, "README.md")
        if f:
            findings.append(f)
    for pattern, expected in _readme_expected_patterns(summary):
        matches = re.findall(pattern, text)
        if not matches:
            findings.append(Finding("README.md", expected, "找不到該句"))
        else:
            for m in matches:
                if m != expected:
                    findings.append(Finding("README.md", expected, m))
    return findings


def _check_quiz(root: Path, summary: dict) -> list[Finding]:
    path = root / SITE_DIR_NAME / "quiz.html"
    rel = f"{SITE_DIR_NAME}/quiz.html"
    if not path.exists():
        return [Finding(rel, "quiz.html", "檔案不存在")]
    text = path.read_text(encoding="utf-8")
    f = _check_region(
        text, "corpus-stats", "js", render_quiz_block(summary), rel
    )
    return [f] if f else []


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
    text = path.read_text(encoding="utf-8")
    c = summary["counts"]
    cov = summary["coverage"]
    findings = []

    for label, value in (
        ("總題數", c["questions"]),
        ("選擇題", c["choice"]),
        ("申論題", c["essay"]),
        ("類科", c["categories"]),
        ("科目", c["subjects"]),
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
        findings.append(Finding(rel, f"filterTag={c['questions']:,} 題", "找不到 filterTag"))
    elif m.group(1) != f"{c['questions']:,}":
        findings.append(
            Finding(rel, f"filterTag={c['questions']:,} 題", m.group(0))
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
    text = path.read_text(encoding="utf-8")
    m = re.search(r"const STATS = (\{.*?\});", text)
    if not m:
        return [Finding(rel, "const STATS = {...}", "找不到 STATS")]
    try:
        stats = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        return [Finding(rel, "STATS 為有效 JSON", str(e))]
    c = summary["counts"]
    cov = summary["coverage"]
    expected = {
        "total": c["questions"],
        "choice": c["choice"],
        "essay": c["essay"],
        "categories": c["categories"],
        "subjects": c["subjects"],
        "firstYear": cov["first_year"],
        "lastYear": cov["last_year"],
        "yearCount": len(cov["years"]),
    }
    return [
        Finding(rel, f"STATS.{k}={v}", repr(stats.get(k)))
        for k, v in expected.items()
        if stats.get(k) != v
    ]


# ── 入口 ─────────────────────────────────────────────────

def check_all(root: Path, summary: dict | None = None) -> list[Finding]:
    root = Path(root)
    if summary is None:
        summary = build_summary(root / DATA_DIR_NAME)
    findings: list[Finding] = []
    findings += _check_artifact(root, summary)
    findings += _check_readme(root, summary)
    findings += _check_quiz(root, summary)
    findings += _check_manifest(root, summary)
    findings += _check_home_stats(root, summary)
    findings += _check_analytics_html(root, summary)
    findings += _check_chart_data(root, summary)
    return findings


def write_surfaces(root: Path, summary: dict) -> list[Path]:
    """重建 artifact 並重填本腳本擁有的表面（README、quiz.html、manifest）。

    先於記憶體算好所有新內容（缺 markers 會在寫檔前失敗），再落盤。
    home-stats / analytics 由各自的產生器擁有；漂移時請執行
    scripts/build_home_stats.py 與 scripts/sync_analytics_frontend.py。
    """
    root = Path(root)

    readme = root / "README.md"
    readme_text = readme.read_text(encoding="utf-8")
    readme_text = _fill_region(
        readme_text, "corpus-stats", "html", render_readme_inventory(summary)
    )
    readme_text = _fill_region(
        readme_text, "corpus-quality", "html", render_readme_quality(summary)
    )
    for pattern, expected in _readme_expected_patterns(summary):
        readme_text = re.sub(pattern, expected, readme_text)

    quiz = root / SITE_DIR_NAME / "quiz.html"
    quiz_text = quiz.read_text(encoding="utf-8")
    quiz_text = _fill_region(
        quiz_text, "corpus-stats", "js", render_quiz_block(summary)
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
        manifest.setdefault("counts", {}).update(expected_counts)
        manifest.setdefault("coverage", {}).update(expected_coverage)
        manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
        manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"

    artifact = root / DATA_DIR_NAME / "quality_summary.json"
    write_summary(summary, artifact)
    readme.write_text(readme_text, encoding="utf-8")
    quiz.write_text(quiz_text, encoding="utf-8")
    written = [artifact, readme, quiz]
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
        help="重建 quality_summary.json 並重填 README/quiz/manifest",
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
