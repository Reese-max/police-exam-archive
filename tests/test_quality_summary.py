# -*- coding: utf-8 -*-
"""corpus quality summary artifact 與跨表徵漂移檢查的測試（issue #61）

驗證單一 machine-readable 品質摘要（考古題庫/quality_summary.json）
與所有公開表面的題數/品質分母一致，且漂移可被偵測。
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_home_stats import build_stats  # noqa: E402
from scripts.build_quality_summary import (  # noqa: E402
    build_summary,
    semantic_diff,
)
from scripts.check_corpus_claims import (  # noqa: E402
    check_all,
    write_surfaces,
)

DATA_DIR = ROOT / "考古題庫"
SUMMARY_PATH = DATA_DIR / "quality_summary.json"


def _choice(n, answer="A"):
    return {
        "number": n,
        "type": "choice",
        "stem": f"第 {n} 題題幹？",
        "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
        "answer": answer,
    }


def _essay(n):
    return {"number": n, "type": "essay", "stem": f"申論題 {n}"}


def _write_exam(data_dir, category, year, subject, questions, dup=False):
    d = data_dir / category / f"{year}年" / subject
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "category": category,
        "year": year,
        "subject": subject,
        "metadata": {"subject": subject, "_is_duplicate": dup},
        "questions": questions,
    }
    (d / "試題.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _skeleton_surfaces(root):
    """建立受管表面的骨架（含 marker），內容由 write_surfaces 填入。"""
    (root / "考古題網站" / "data").mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(
        "# 考古題\n\n涵蓋 106-114 年（2017-2025）\n\n## 資料規模\n\n"
        "<!-- corpus-stats:begin -->\nold\n<!-- corpus-stats:end -->\n\n"
        "## 特殊值\n\n- 均給分（0 題）\n- 皆給分（0 題）\n"
        "- 原卷為圖片題，無法文字化（0 題）\n\n"
        "## 資料品質\n\n- **結構完整性**: ok\n"
        "<!-- corpus-quality:begin -->\nold\n<!-- corpus-quality:end -->\n\n"
        "圖片題（0 題）以佔位\n\n"
        "查詢速度依執行環境而異（目前 1 題全文搜尋）。\n",
        encoding="utf-8",
    )
    (root / "考古題網站" / "quiz.html").write_text(
        "<script>\n// corpus-stats:begin\nold\n// corpus-stats:end\n</script>\n",
        encoding="utf-8",
    )
    (root / "考古題庫" / "dataset_manifest.json").write_text(
        json.dumps({"schema_version": 1, "coverage": {}, "counts": {}}),
        encoding="utf-8",
    )


def _write_foreign_surfaces(root, summary):
    """由其他產生器擁有的表面：測試中直接以 artifact 投影值寫入。"""
    site_dir = root / "考古題網站"
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "data").mkdir(exist_ok=True)
    (site_dir / "data" / "home-stats.json").write_text(
        json.dumps(summary["projections"]["site"], ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    c = summary["counts"]
    fy = summary["coverage"]["first_year"]
    ly = summary["coverage"]["last_year"]
    (site_dir / "analytics.html").write_text(
        f'<div class="label">總題數</div><div><span class="num" '
        f'data-target="{c["questions"]}">0</span></div>\n'
        f'<div class="label">選擇題</div><div><span class="num" '
        f'data-target="{c["choice"]}">0</span></div>\n'
        f'<div class="label">申論題</div><div><span class="num" '
        f'data-target="{c["essay"]}">0</span></div>\n'
        f'<div class="label">類科</div><div><span class="num" '
        f'data-target="{c["categories"]}">0</span></div>\n'
        f'<div class="label">科目</div><div><span class="num" '
        f'data-target="{c["subjects"]}">0</span></div>\n'
        f'<div class="label">年份</div>'
        f'<div><span class="num">{fy}–{ly}</span></div>\n'
        f'<span class="filter-tag" id="filterTag">全部類科 · '
        f'{c["questions"]:,} 題</span>\n'
        f'<span class="hint">資料更新至 {ly} 年</span>\n'
        f'<div class="card-title"><h3>各年度出題數</h3>'
        f'<span class="badge">{fy}–{ly}</span>\n'
        f'<div class="card-title"><h3>趨勢比較</h3>'
        f'<span class="badge">{fy}–{ly}</span>\n',
        encoding="utf-8",
    )
    (site_dir / "analytics-chart-data.js").write_text(
        'const STATS = {"total":%d,"choice":%d,"essay":%d,"categories":%d,'
        '"subjects":%d,"firstYear":%d,"lastYear":%d,"yearCount":%d};\n'
        % (
            c["questions"], c["choice"], c["essay"], c["categories"],
            c["subjects"], fy, ly, len(summary["coverage"]["years"]),
        ),
        encoding="utf-8",
    )


def _build_fixture_root(tmp_path):
    """最小語料庫 + 全部受管表面骨架。"""
    root = tmp_path
    data_dir = root / "考古題庫"
    _write_exam(
        data_dir, "行政警察學系", 115, "警察法規",
        [_choice(1), _choice(2), _essay(1)],
    )
    _write_exam(
        data_dir, "外事警察學系", 115, "國文",
        [_choice(1)], dup=True,
    )
    _skeleton_surfaces(root)
    return root


def _sync_fixture(root):
    summary = build_summary(root / "考古題庫")
    write_surfaces(root, summary)
    _write_foreign_surfaces(root, summary)
    return summary


# ══════════════════════════════════════════════
#  真實語料庫：artifact 內容
# ══════════════════════════════════════════════

@pytest.fixture(scope="module")
def summary():
    return build_summary(DATA_DIR)


class TestSummaryAgainstCorpus:
    """針對目前語料庫的 artifact 內容（對應 issue 驗收 1/2/4/5）。"""

    def test_counts(self, summary):
        c = summary["counts"]
        assert c["json_files"] == 2049
        assert c["questions"] == 42518
        assert c["choice"] == 36760
        assert c["essay"] == 5758
        assert c["categories"] == 49
        assert c["subjects"] == 101

    def test_duplicates_reported_separately(self, summary):
        c = summary["counts"]
        assert c["duplicate_files"] == 41
        assert c["total_files"] == 2090
        assert c["duplicate_questions"] == 1217
        # 重複副本不混入唯一題數
        assert c["total_files"] == c["json_files"] + c["duplicate_files"]

    def test_year115_choice_included_in_scope(self, summary):
        # 550 道 115 年選擇題必須計入品質分母範圍
        assert summary["by_year"]["115"]["choice"] == 550
        assert summary["coverage"]["last_year"] == 115

    def test_quality_denominators_cover_full_choice_scope(self, summary):
        q = summary["quality"]
        for metric in ("option_completeness", "answer_validity"):
            assert q[metric]["denominator"] == summary["counts"]["choice"]
            assert q[metric]["denominator"] == 36760
            assert q[metric]["numerator"] == q[metric]["denominator"]

    def test_image_placeholder_scope(self, summary):
        assert summary["image_placeholders"]["choice_questions"] == 4

    def test_special_values(self, summary):
        sv = summary["special_values"]
        assert sv["free_score_questions"] == 178
        assert sv["multi_answer_questions"] == 3

    def test_top_level_flag_divergence_disclosed(self, summary):
        # 9 份檔案僅在頂層標記 _is_duplicate；正典規則仍計入唯一題數，
        # 但 artifact 必須揭露此差異而非隱藏
        assert summary["counts"]["top_level_only_duplicate_flags"] == 9
        assert summary["counts"]["files_without_year"] == 0
        assert any(
            "頂層" in s
            for s in summary["dataset"]["known_inconsistencies"]
        )

    def test_identity_fields(self, summary):
        assert summary["schema_version"] == 1
        assert summary["dataset_fingerprint"].startswith("sha256:")
        assert len(summary["dataset_fingerprint"]) == len("sha256:") + 64
        assert summary["dataset"]["inclusion_rule"]
        assert summary["dataset"]["exclusion_rule"]

    def test_fingerprint_deterministic(self, summary):
        again = build_summary(DATA_DIR)
        assert again["dataset_fingerprint"] == summary["dataset_fingerprint"]

    def test_committed_artifact_in_sync(self, summary):
        assert SUMMARY_PATH.exists(), "quality_summary.json 未提交"
        committed = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        assert semantic_diff(summary, committed) == []

    def test_repo_surfaces_in_sync(self):
        findings = check_all(ROOT)
        assert findings == [], "\n".join(str(f) for f in findings)


# ══════════════════════════════════════════════
#  Fixture：年度匯入 / 重複副本 / 漂移偵測
# ══════════════════════════════════════════════

class TestFixtureImport:
    """對應 regression test 3/4：新年度匯入與重複副本行為。"""

    def test_new_import_moves_all_governed_counts(self, tmp_path):
        root = _build_fixture_root(tmp_path)
        s1 = _sync_fixture(root)
        assert check_all(root) == []

        # 模擬新年度匯入：116 年 1 道不重複選擇題
        _write_exam(root / "考古題庫", "行政警察學系", 116, "新科目", [_choice(1)])
        s2 = build_summary(root / "考古題庫")
        assert s2["counts"]["choice"] == s1["counts"]["choice"] + 1
        assert s2["counts"]["questions"] == s1["counts"]["questions"] + 1
        assert s2["counts"]["json_files"] == s1["counts"]["json_files"] + 1
        assert s2["by_year"]["116"]["choice"] == 1
        assert s2["quality"]["option_completeness"]["denominator"] == (
            s1["counts"]["choice"] + 1
        )
        assert s2["dataset_fingerprint"] != s1["dataset_fingerprint"]

        # 匯入後未重算的表面必須被判定漂移
        assert check_all(root) != []

        write_surfaces(root, s2)
        _write_foreign_surfaces(root, s2)
        assert check_all(root) == []

    def test_duplicate_copy_diverges_labeled(self, tmp_path):
        root = _build_fixture_root(tmp_path)
        s = build_summary(root / "考古題庫")
        # fixture：1 份唯一檔案（2 選擇 + 1 申論）與 1 份重複副本（1 選擇）
        assert s["counts"]["json_files"] == 1
        assert s["counts"]["duplicate_files"] == 1
        assert s["counts"]["total_files"] == 2
        assert s["counts"]["questions"] == 3
        assert s["counts"]["duplicate_questions"] == 1
        # 頂層獨有旗標在本 fixture 為 0
        assert s["counts"]["top_level_only_duplicate_flags"] == 0

    def test_quality_metrics_reconcile_in_fixture(self, tmp_path):
        root = _build_fixture_root(tmp_path)
        s = build_summary(root / "考古題庫")
        q = s["quality"]
        assert q["option_completeness"]["denominator"] == s["counts"]["choice"]
        assert q["answer_validity"]["denominator"] == s["counts"]["choice"]
        assert q["option_completeness"]["numerator"] == 2
        assert q["answer_validity"]["numerator"] == 2

    def test_volatile_fields_ignored_in_diff(self, tmp_path):
        root = _build_fixture_root(tmp_path)
        s = build_summary(root / "考古題庫")
        other = json.loads(json.dumps(s))
        other["generated_at"] = "1999-01-01T00:00:00+00:00"
        other["source_commit"] = "deadbeef"
        assert semantic_diff(s, other) == []


class TestDriftDetection:
    """對應 regression test 5：每個公開表面植入一處漂移都要被抓到。"""

    @pytest.mark.parametrize(
        "surface",
        [
            "quality_summary",
            "readme_inventory",
            "readme_quality",
            "readme_search_line",
            "readme_free_score",
            "readme_year_range",
            "readme_marker_removed",
            "quiz_html",
            "dataset_manifest",
            "home_stats",
            "analytics_html",
            "analytics_year_card",
            "analytics_chart_data",
        ],
    )
    def test_seeded_drift_fails_with_path_and_values(self, tmp_path, surface):
        root = _build_fixture_root(tmp_path)
        summary = _sync_fixture(root)
        assert check_all(root) == []

        if surface == "quality_summary":
            p = root / "考古題庫" / "quality_summary.json"
            d = json.loads(p.read_text(encoding="utf-8"))
            d["counts"]["choice"] += 1
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
        elif surface == "readme_inventory":
            p = root / "README.md"
            p.write_text(
                p.read_text(encoding="utf-8").replace(
                    f"{summary['counts']['choice']:,} 題",
                    f"{summary['counts']['choice'] - 1:,} 題",
                    1,
                ),
                encoding="utf-8",
            )
        elif surface == "readme_quality":
            p = root / "README.md"
            old = (
                f"{summary['counts']['choice']:,}/"
                f"{summary['counts']['choice']:,}"
            )
            p.write_text(
                p.read_text(encoding="utf-8").replace(
                    old, f"{summary['counts']['choice'] - 1:,}/"
                    f"{summary['counts']['choice']:,}", 1,
                ),
                encoding="utf-8",
            )
        elif surface == "readme_search_line":
            p = root / "README.md"
            p.write_text(
                p.read_text(encoding="utf-8").replace(
                    f"目前 {summary['counts']['questions']:,} 題全文搜尋",
                    f"目前 {summary['counts']['questions'] - 1:,} 題全文搜尋",
                    1,
                ),
                encoding="utf-8",
            )
        elif surface == "readme_free_score":
            p = root / "README.md"
            free = summary["special_values"]["free_score_questions"]
            p.write_text(
                p.read_text(encoding="utf-8").replace(
                    f"均給分（{free:,} 題）",
                    f"均給分（{free + 1:,} 題）",
                    1,
                ),
                encoding="utf-8",
            )
        elif surface == "readme_year_range":
            p = root / "README.md"
            fy = summary["coverage"]["first_year"]
            ly = summary["coverage"]["last_year"]
            p.write_text(
                p.read_text(encoding="utf-8").replace(
                    f"涵蓋 {fy}-{ly} 年（{fy + 1911}-{ly + 1911}）",
                    f"涵蓋 {fy}-{ly - 1} 年（{fy + 1911}-{ly + 1910}）",
                    1,
                ),
                encoding="utf-8",
            )
        elif surface == "readme_marker_removed":
            p = root / "README.md"
            p.write_text(
                p.read_text(encoding="utf-8").replace(
                    "corpus-stats:begin", "corpus-stats", 1
                ),
                encoding="utf-8",
            )
        elif surface == "quiz_html":
            p = root / "考古題網站" / "quiz.html"
            p.write_text(
                p.read_text(encoding="utf-8").replace(
                    f"{summary['counts']['choice']:,}",
                    f"{summary['counts']['choice'] - 1:,}",
                    1,
                ),
                encoding="utf-8",
            )
        elif surface == "dataset_manifest":
            p = root / "考古題庫" / "dataset_manifest.json"
            d = json.loads(p.read_text(encoding="utf-8"))
            d["counts"]["choice"] += 1
            p.write_text(json.dumps(d, ensure_ascii=False),
                         encoding="utf-8")
        elif surface == "home_stats":
            p = root / "考古題網站" / "data" / "home-stats.json"
            d = json.loads(p.read_text(encoding="utf-8"))
            d["question_count"] += 1
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
        elif surface == "analytics_html":
            p = root / "考古題網站" / "analytics.html"
            p.write_text(
                p.read_text(encoding="utf-8").replace(
                    f'data-target="{summary["counts"]["questions"]}"',
                    f'data-target="{summary["counts"]["questions"] + 1}"',
                    1,
                ),
                encoding="utf-8",
            )
        elif surface == "analytics_year_card":
            p = root / "考古題網站" / "analytics.html"
            fy = summary["coverage"]["first_year"]
            ly = summary["coverage"]["last_year"]
            p.write_text(
                p.read_text(encoding="utf-8").replace(
                    f'<div class="label">年份</div>'
                    f'<div><span class="num">{fy}–{ly}</span>',
                    f'<div class="label">年份</div>'
                    f'<div><span class="num">{fy}–{ly - 1}</span>',
                    1,
                ),
                encoding="utf-8",
            )
        elif surface == "analytics_chart_data":
            p = root / "考古題網站" / "analytics-chart-data.js"
            p.write_text(
                p.read_text(encoding="utf-8").replace(
                    f'"total":{summary["counts"]["questions"]}',
                    f'"total":{summary["counts"]["questions"] + 1}',
                    1,
                ),
                encoding="utf-8",
            )

        findings = check_all(root)
        assert findings, f"{surface} 漂移未被偵測"
        # 每筆 finding 必須指出檔案與期望/實際值
        for f in findings:
            rendered = str(f)
            assert "expected" in rendered and "found" in rendered
        # 至少一筆 finding 指向被竄改的檔案
        target_names = {
            "quality_summary": "quality_summary.json",
            "readme_inventory": "README.md",
            "readme_quality": "README.md",
            "readme_search_line": "README.md",
            "readme_free_score": "README.md",
            "readme_year_range": "README.md",
            "readme_marker_removed": "README.md",
            "quiz_html": "quiz.html",
            "dataset_manifest": "dataset_manifest.json",
            "home_stats": "home-stats.json",
            "analytics_html": "analytics.html",
            "analytics_year_card": "analytics.html",
            "analytics_chart_data": "analytics-chart-data.js",
        }
        assert any(target_names[surface] in f.path for f in findings)
