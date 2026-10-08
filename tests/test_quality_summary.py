# -*- coding: utf-8 -*-
"""corpus quality summary artifact 與跨表徵漂移檢查的測試（issue #61）

驗證單一 machine-readable 品質摘要（考古題庫/quality_summary.json）
與所有公開表面的題數/品質分母一致，且漂移可被偵測。
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from scripts.build_analytics import build_analytics, load_all_questions  # noqa: E402
    from scripts.build_home_stats import build_stats  # noqa: E402
    from scripts.build_quality_summary import (  # noqa: E402
        _fingerprint_at_commit,
        _source_commit,
        build_summary,
        semantic_diff,
    )
    from scripts.check_corpus_claims import (  # noqa: E402
        check_all,
        write_surfaces,
    )
    from scripts.build_search_index import build_index  # noqa: E402
    from scripts.sync_analytics_frontend import (  # noqa: E402
        chart_bundle,
        sync_chart_js,
        sync_text,
    )
except ModuleNotFoundError as exc:  # pragma: no cover - 模組尚未實作
    # 本檔需能在不含實作的基底上被 pytest 收集（TDD red 必須以測試失敗
    # 呈現而非 collection error），故把缺失模組延後到執行期才報錯。
    # 只吞掉「被測模組本身不存在」；模組內部缺依賴仍要爆出來。
    if exc.name not in {
        "scripts.build_home_stats",
        "scripts.build_quality_summary",
        "scripts.check_corpus_claims",
    }:
        raise

    def _missing(*_args, **_kwargs):
        pytest.fail(f"品質摘要模組尚未實作：{exc}")

    build_analytics = load_all_questions = build_index = _missing
    _fingerprint_at_commit = _source_commit = _missing
    build_stats = build_summary = semantic_diff = _missing
    chart_bundle = sync_chart_js = sync_text = _missing
    check_all = write_surfaces = _missing

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


def _write_exam(
    data_dir, category, year, subject, questions, dup=False, top_dup=False
):
    d = data_dir / category / f"{year}年" / subject
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "category": category,
        "year": year,
        "subject": subject,
        "metadata": {"subject": subject, "_is_duplicate": dup},
        "questions": questions,
    }
    if top_dup:
        payload["_is_duplicate"] = True
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
        "<!-- corpus-scope:begin -->\nold\n<!-- corpus-scope:end -->\n"
        "<script>\n// corpus-stats:begin\nold\n// corpus-stats:end\n</script>\n",
        encoding="utf-8",
    )
    (root / "考古題網站" / "search.html").write_text(
        '<p class="lead">跨類科搜尋歷年警察特考考古題與閱讀題組。</p>\n'
        "<!-- corpus-scope:begin -->\nold\n<!-- corpus-scope:end -->\n"
        "<script>\nSearchEngine.loadIndex().then(function(stats){\n"
        "document.getElementById('statTotal').textContent="
        "stats.total.toLocaleString();\n});\n</script>\n",
        encoding="utf-8",
    )
    (root / "考古題網站" / "index.html").write_text(
        "<!-- corpus-scope:begin -->\nold\n<!-- corpus-scope:end -->\n",
        encoding="utf-8",
    )
    (root / "考古題庫" / "dataset_manifest.json").write_text(
        json.dumps({"schema_version": 1, "coverage": {}, "counts": {}}),
        encoding="utf-8",
    )


def _write_foreign_surfaces(root, summary):
    """以 repo 的真正 home/search/analytics generators 建立外部表面。"""
    site_dir = root / "考古題網站"
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "data").mkdir(exist_ok=True)
    data_dir = root / "考古題庫"

    home = build_stats(data_dir)
    (site_dir / "data" / "home-stats.json").write_text(
        json.dumps(home, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    search_index = build_index(data_dir)
    (site_dir / "data" / "search-index.json").write_text(
        json.dumps(search_index, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    analytics = build_analytics(load_all_questions(data_dir))
    analytics_path = site_dir / "data" / "analytics.json"
    analytics_path.write_text(
        json.dumps(analytics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    html_template = (
        '<div class="label">總題數</div><div><span class="num" data-target="0">0</span></div>\n'
        '<div class="label">選擇題</div><div><span class="num" data-target="0">0</span></div>\n'
        '<div class="label">申論題</div><div><span class="num" data-target="0">0</span></div>\n'
        '<div class="label">類科</div><div><span class="num" data-target="0">0</span></div>\n'
        '<div class="label">科目</div><div><span class="num" data-target="0">0</span></div>\n'
        '<div class="label">年份</div><div><span class="num">0–0</span></div>\n'
        '<span class="filter-tag" id="filterTag">全部類科 · 0 題</span>\n'
        '<span class="hint">資料更新至 0 年</span>\n'
        '<div class="card-title"><h3>各年度出題數</h3><span class="badge">0–0</span>\n'
        '<div class="card-title"><h3>趨勢比較</h3><span class="badge">0–0</span>\n'
        '<script src="analytics-chart-bundle.js"></script>\n'
    )
    (site_dir / "analytics.html").write_text(
        sync_text(html_template, analytics["stats"]), encoding="utf-8"
    )
    chart_js = sync_chart_js(
        "function all(){return { year: ALL_YEAR, donut: ALL_DONUT, total: 0 };}\n"
    )
    (site_dir / "analytics-chart.js").write_text(chart_js, encoding="utf-8")
    chart_data = site_dir / "analytics-chart-data.js"
    subprocess.run(
        [
            "node",
            str(ROOT / "考古題網站" / "_gen_data.js"),
            str(analytics_path),
            str(chart_data),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    (site_dir / "analytics-chart-bundle.js").write_text(
        chart_bundle(
            chart_data.read_text(encoding="utf-8"),
            chart_js,
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


@pytest.fixture(scope="module")
def source_commit_repo(tmp_path_factory):
    repo = tmp_path_factory.mktemp("quality-summary-source-commits")
    data_dir = repo / "corpus"
    exam = data_dir / "exam" / "試題.json"
    exam.parent.mkdir(parents=True)
    exam.write_text('{"version": 1}\n', encoding="utf-8")
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Quality Test"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "quality@example.invalid"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", "."],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "first"],
        check=True,
        capture_output=True,
    )
    first = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    subprocess.run(
        ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "second"],
        check=True,
        capture_output=True,
    )
    second = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    exam.write_text('{"version": 2}\n', encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "."],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "different corpus"],
        check=True,
        capture_output=True,
    )
    different = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    subprocess.run(
        ["git", "-C", str(repo), "checkout", "--detach", second],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git", "-C", str(repo), "update-ref",
            "refs/remotes/origin/master", first,
        ],
        check=True,
        capture_output=True,
    )
    return repo, data_dir, first, second, different


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
        assert c["duplicate_choice"] == 1145
        assert c["duplicate_essay"] == 72
        # 重複副本不混入唯一題數
        assert c["total_files"] == c["json_files"] + c["duplicate_files"]
        inventory = summary["exclusion_inventory"]["metadata_duplicate_files"]
        assert len(inventory) == c["duplicate_files"]
        assert sum(item["questions"] for item in inventory) == c["duplicate_questions"]

    def test_year115_choice_included_in_scope(self, summary):
        # 550 道 115 年選擇題必須計入品質分母範圍
        assert summary["by_year"]["115"]["choice"] == 550
        assert summary["coverage"]["last_year"] == 115

    def test_quality_denominators_cover_full_choice_scope(self, summary):
        q = summary["quality"]
        for metric in ("option_completeness", "answer_validity"):
            assert q[metric]["denominator"] == summary["counts"]["choice"]
            assert q[metric]["denominator"] == 36760
            assert 0 <= q[metric]["numerator"] <= q[metric]["denominator"]

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
        assert summary["counts"]["top_level_only_duplicate_questions"] == 36
        assert summary["counts"]["top_level_only_duplicate_choice"] == 0
        assert summary["counts"]["top_level_only_duplicate_essay"] == 36
        assert summary["counts"]["files_without_year"] == 0
        assert any(
            "頂層" in s
            for s in summary["dataset"]["known_inconsistencies"]
        )
        inventory = summary["exclusion_inventory"]["top_level_only_duplicate_files"]
        assert len(inventory) == 9
        assert all(item["canonical_action"] == "included" for item in inventory)
        assert all(item["search_action"] == "excluded" for item in inventory)

    def test_identity_fields(self, summary):
        assert summary["schema_version"] == 1
        assert summary["dataset_fingerprint"].startswith("sha256:")
        assert len(summary["dataset_fingerprint"]) == len("sha256:") + 64
        assert summary["corpus_fingerprint"] == summary["dataset_fingerprint"]
        # Official image provenance in four source JSONs; source commit 5a24656e.
        assert summary["corpus_fingerprint"] == (
            "sha256:f64f6b48e0b0e6352b9c0a0d5771ce213b9625c6fae8c5db69487e023efcad4e"
        )
        assert summary["provenance"]["schema_version"] == 1
        assert summary["provenance"]["fingerprint"]["value"] == summary["corpus_fingerprint"]
        assert summary["provenance"]["fingerprint"]["byte_source"].startswith(
            "raw Git blob bytes"
        )
        assert summary["dataset"]["inclusion_rule"]
        assert summary["dataset"]["exclusion_rule"]

    def test_projection_scopes_are_generator_derived(self, summary):
        search = summary["projections"]["search"]
        analytics = summary["projections"]["analytics"]
        home = summary["projections"]["site"]
        assert search["stats"] == {
            "total": 42482,
            "choice": 36760,
            "essay": 5722,
            "categories": 49,
            "subjects": 101,
        }
        assert "頂層" in search["scope"] and "metadata" in search["scope"]
        assert analytics["stats"]["total"] == 42518
        assert analytics["stats"]["essay"] == 5758
        assert "只排除 metadata" in analytics["scope"]
        assert home["category_count"] == 17
        assert home["question_count"] == 24876

    def test_fingerprint_deterministic(self, summary):
        again = build_summary(DATA_DIR)
        assert again["dataset_fingerprint"] == summary["dataset_fingerprint"]

    def test_committed_artifact_in_sync(self, summary):
        assert SUMMARY_PATH.exists(), "quality_summary.json 未提交"
        committed = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        assert len(committed["source_commit"]) == 40
        assert semantic_diff(
            summary,
            committed,
            repo_root=ROOT,
            data_dir=DATA_DIR,
        ) == []

    def test_repo_surfaces_in_sync(self):
        findings = check_all(ROOT)
        assert findings == [], "\n".join(str(f) for f in findings)


# ══════════════════════════════════════════════
#  Fixture：年度匯入 / 重複副本 / 漂移偵測
# ══════════════════════════════════════════════

class TestFixtureImport:
    """對應 regression test 3/4：新年度匯入與重複副本行為。"""

    @pytest.mark.parametrize("page", ["index.html", "search.html", "quiz.html"])
    def test_visible_canonical_scope_and_one_count_drift(self, tmp_path, page):
        root = _build_fixture_root(tmp_path)
        summary = _sync_fixture(root)
        path = root / "考古題網站" / page
        text = path.read_text(encoding="utf-8")
        count = summary["counts"]
        canonical = (
            f"完整題庫：{count['choice']:,} 道選擇題、"
            f"{count['essay']:,} 道申論題，共 {count['questions']:,} 題"
        )
        assert canonical in text
        assert "本頁" in text
        path.write_text(text.replace(canonical, canonical.replace(
            f"共 {count['questions']:,} 題", f"共 {count['questions'] + 1:,} 題"
        )), encoding="utf-8")
        findings = check_all(root)
        assert any(f.path == f"考古題網站/{page}" for f in findings)

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
        assert s2["projections"]["search"]["stats"]["total"] == (
            s1["projections"]["search"]["stats"]["total"] + 1
        )
        assert s2["projections"]["site"]["question_count"] == (
            s1["projections"]["site"]["question_count"] + 1
        )
        assert s2["projections"]["analytics"]["stats"]["total"] == (
            s1["projections"]["analytics"]["stats"]["total"] + 1
        )
        assert s2["dataset_fingerprint"] != s1["dataset_fingerprint"]

        # 匯入後未重算的表面必須被判定漂移
        assert check_all(root) != []

        write_surfaces(root, s2)
        _write_foreign_surfaces(root, s2)
        assert check_all(root) == []
        for page in ("index.html", "search.html", "quiz.html"):
            text = (root / "考古題網站" / page).read_text(encoding="utf-8")
            assert f"共 {s2['counts']['questions']:,} 題" in text
            assert f"{s2['counts']['choice']:,} 道選擇題" in text
        search_index = json.loads(
            (root / "考古題網站" / "data" / "search-index.json").read_text(
                encoding="utf-8"
            )
        )
        analytics = json.loads(
            (root / "考古題網站" / "data" / "analytics.json").read_text(
                encoding="utf-8"
            )
        )
        assert search_index["stats"]["total"] == s2["projections"]["search"]["stats"]["total"]
        assert analytics["stats"] == s2["projections"]["analytics"]["stats"]
        assert 116 in search_index["facets"]["years"]

    def test_external_git_root_works_through_both_clis(self, tmp_path):
        root = _build_fixture_root(tmp_path)
        _sync_fixture(root)
        subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(root), "config", "user.name", "Quality Test"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "config",
                "user.email",
                "quality@example.invalid",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(root), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(root), "commit", "-m", "fixture"],
            check=True,
            capture_output=True,
        )

        data_dir = root / "考古題庫"
        output = data_dir / "quality_summary.json"
        build_command = [
            sys.executable,
            str(ROOT / "scripts" / "build_quality_summary.py"),
            "--data-dir",
            str(data_dir),
            "--output",
            str(output),
        ]
        subprocess.run(build_command, check=True, capture_output=True, text=True)
        checked = subprocess.run(
            [*build_command, "--check"],
            capture_output=True,
            text=True,
        )
        assert checked.returncode == 0, checked.stdout + checked.stderr

        claims = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "check_corpus_claims.py"),
                "--root",
                str(root),
            ],
            capture_output=True,
            text=True,
        )
        assert claims.returncode == 0, claims.stdout + claims.stderr
        artifact = json.loads(output.read_text(encoding="utf-8"))
        assert len(artifact["source_commit"]) == 40

        exam = next(data_dir.glob("**/試題.json"))
        exam.write_text(
            exam.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        dirty = subprocess.run(
            [*build_command, "--check"],
            capture_output=True,
            text=True,
        )
        assert dirty.returncode != 0
        assert "source commit" in dirty.stderr

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

    def test_top_level_duplicate_scope_divergence_is_explicit(self, tmp_path):
        root = _build_fixture_root(tmp_path)
        _write_exam(
            root / "考古題庫",
            "行政警察學系",
            114,
            "頂層旗標申論",
            [_essay(1)],
            top_dup=True,
        )
        summary = build_summary(root / "考古題庫")
        assert summary["counts"]["questions"] == 4
        assert summary["counts"]["essay"] == 2
        assert summary["projections"]["analytics"]["stats"]["total"] == 4
        assert summary["projections"]["search"]["stats"]["total"] == 3
        inventory = summary["exclusion_inventory"]["top_level_only_duplicate_files"]
        assert len(inventory) == 1
        assert inventory[0]["essay"] == 1
        assert inventory[0]["canonical_action"] == "included"
        assert inventory[0]["search_action"] == "excluded"

    def test_quality_metrics_reconcile_in_fixture(self, tmp_path):
        root = _build_fixture_root(tmp_path)
        s = build_summary(root / "考古題庫")
        q = s["quality"]
        assert q["option_completeness"]["denominator"] == s["counts"]["choice"]
        assert q["answer_validity"]["denominator"] == s["counts"]["choice"]
        assert q["option_completeness"]["numerator"] == 2
        assert q["answer_validity"]["numerator"] == 2

    def test_quality_metrics_are_measured_not_forced_to_100_percent(self, tmp_path):
        root = _build_fixture_root(tmp_path)
        exam = payload = None
        for candidate in (root / "考古題庫").glob("**/試題.json"):
            current = json.loads(candidate.read_text(encoding="utf-8"))
            if not current["metadata"]["_is_duplicate"] and len(current["questions"]) >= 2:
                exam, payload = candidate, current
                break
        assert exam is not None and payload is not None
        payload["questions"][0]["options"].pop("D")
        payload["questions"][1]["answer"] = "Z"
        exam.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        quality = build_summary(root / "考古題庫")["quality"]
        assert quality["option_completeness"]["numerator"] == 1
        assert quality["option_completeness"]["denominator"] == 2
        assert quality["answer_validity"]["numerator"] == 1
        assert quality["answer_validity"]["denominator"] == 2

    def test_valid_different_volatile_values_are_ignored(
        self, source_commit_repo
    ):
        repo, data_dir, first, second, _different = source_commit_repo
        expected = {
            "generated_at": "2026-10-08T01:02:03+00:00",
            "source_commit": first,
            "stable": 1,
        }
        actual = {
            "generated_at": "1999-01-01T00:00:00Z",
            "source_commit": second,
            "stable": 1,
        }
        assert semantic_diff(
            expected, actual, repo_root=repo, data_dir=data_dir
        ) == []

    def test_source_commit_falls_back_to_origin_master_without_symbolic_head(
        self, source_commit_repo
    ):
        repo, data_dir, first, _second, _different = source_commit_repo
        symbolic = subprocess.run(
            [
                "git", "-C", str(repo), "symbolic-ref", "--quiet",
                "refs/remotes/origin/HEAD",
            ],
            capture_output=True,
        )
        assert symbolic.returncode != 0
        assert _source_commit(data_dir) == first

    def test_git_blob_fingerprint_is_content_exact(self, source_commit_repo):
        repo, data_dir, first, _second, _different = source_commit_repo
        exam = data_dir / "exam" / "試題.json"
        h = hashlib.sha256()
        h.update("exam/試題.json".encode("utf-8"))
        h.update(b"\0")
        h.update(hashlib.sha256(b'{"version": 1}\n').digest())
        assert _fingerprint_at_commit(
            [str(exam)], data_dir, repo, first
        ) == "sha256:" + h.hexdigest()

    def test_existing_commit_with_different_corpus_is_not_ignored(
        self, source_commit_repo
    ):
        repo, data_dir, first, _second, different = source_commit_repo
        generated_at = "2026-10-08T01:02:03+00:00"
        diffs = semantic_diff(
            {"generated_at": generated_at, "source_commit": first},
            {"generated_at": generated_at, "source_commit": different},
            repo_root=repo,
            data_dir=data_dir,
        )
        assert any(path == "source_commit" for path, _expected, _actual in diffs)

    @pytest.mark.parametrize(
        "value",
        [
            "not-a-timestamp",
            "2026-10-08T01:02:03",
            None,
            123,
            {},
            [],
        ],
    )
    def test_invalid_generated_at_is_not_ignored(
        self, source_commit_repo, value
    ):
        repo, data_dir, first, _second, _different = source_commit_repo
        expected = {
            "generated_at": "2026-10-08T01:02:03+00:00",
            "source_commit": first,
        }
        actual = {**expected, "generated_at": value}
        assert any(
            path == "generated_at"
            for path, _expected, _actual in semantic_diff(
                expected, actual, repo_root=repo, data_dir=data_dir
            )
        )

    @pytest.mark.parametrize(
        "value",
        [
            "not-a-commit",
            "deadbeef",
            "0" * 40,
            None,
            123,
            {},
            [],
        ],
    )
    def test_invalid_source_commit_is_not_ignored(
        self, source_commit_repo, value
    ):
        repo, data_dir, first, _second, _different = source_commit_repo
        expected = {
            "generated_at": "2026-10-08T01:02:03+00:00",
            "source_commit": first,
        }
        actual = {**expected, "source_commit": value}
        assert any(
            path == "source_commit"
            for path, _expected, _actual in semantic_diff(
                expected, actual, repo_root=repo, data_dir=data_dir
            )
        )

    def test_source_commit_null_requires_no_git_contract(
        self, source_commit_repo, tmp_path
    ):
        repo, data_dir, first, _second, _different = source_commit_repo
        generated_at = "2026-10-08T01:02:03+00:00"
        no_git_data_dir = tmp_path / "non-git-corpus"
        no_git_data_dir.mkdir()
        assert semantic_diff(
            {"generated_at": generated_at, "source_commit": None},
            {"generated_at": generated_at, "source_commit": None},
            data_dir=no_git_data_dir,
        ) == []
        assert semantic_diff(
            {"generated_at": generated_at, "source_commit": first},
            {"generated_at": generated_at, "source_commit": None},
            repo_root=repo,
            data_dir=data_dir,
        )

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("generated_at", "not-a-timestamp"),
            ("source_commit", "deadbeef"),
        ],
    )
    def test_invalid_expected_volatile_schema_is_reported(
        self, source_commit_repo, field, value
    ):
        repo, data_dir, first, _second, _different = source_commit_repo
        expected = {
            "generated_at": "2026-10-08T01:02:03+00:00",
            "source_commit": first,
        }
        expected[field] = value
        assert any(
            path == field
            for path, _expected, _actual in semantic_diff(
                expected, expected, repo_root=repo, data_dir=data_dir
            )
        )

    @pytest.mark.parametrize("field", ["generated_at", "source_commit"])
    def test_missing_volatile_metadata_is_not_ignored(self, tmp_path, field):
        root = _build_fixture_root(tmp_path)
        summary = build_summary(root / "考古題庫")
        other = json.loads(json.dumps(summary))
        del other[field]
        assert any(
            path == field
            for path, _expected, _actual in semantic_diff(
                summary,
                other,
                data_dir=root / "考古題庫",
            )
        )


class TestDriftDetection:
    """對應 regression test 5：每個公開表面植入一處漂移都要被抓到。"""

    @pytest.mark.parametrize(
        "surface",
        [
            "quality_summary",
            "readme_inventory",
            "readme_quality",
            "readme_search_scope",
            "readme_free_score",
            "readme_year_range",
            "readme_marker_removed",
            "quiz_html",
            "search_html",
            "search_index",
            "dataset_manifest",
            "home_stats",
            "analytics_html",
            "analytics_year_card",
            "analytics_chart_data",
            "analytics_chart_bundle",
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
        elif surface == "readme_search_scope":
            p = root / "README.md"
            total = summary["projections"]["search"]["stats"]["total"]
            p.write_text(
                p.read_text(encoding="utf-8").replace(
                    f"離線生成值為 {total:,} 題",
                    f"離線生成值為 {total + 1:,} 題",
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
        elif surface == "search_html":
            p = root / "考古題網站" / "search.html"
            p.write_text(
                p.read_text(encoding="utf-8").replace(
                    "stats.total.toLocaleString()",
                    "(stats.total + 1).toLocaleString()",
                    1,
                ),
                encoding="utf-8",
            )
        elif surface == "search_index":
            p = root / "考古題網站" / "data" / "search-index.json"
            d = json.loads(p.read_text(encoding="utf-8"))
            d["stats"]["total"] += 1
            p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
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
        elif surface == "analytics_chart_bundle":
            p = root / "考古題網站" / "analytics-chart-bundle.js"
            total = summary["projections"]["analytics"]["stats"]["total"]
            p.write_text(
                p.read_text(encoding="utf-8").replace(
                    f'"total":{total}', f'"total":{total + 1}', 1
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
            "readme_search_scope": "README.md",
            "readme_free_score": "README.md",
            "readme_year_range": "README.md",
            "readme_marker_removed": "README.md",
            "quiz_html": "quiz.html",
            "search_html": "search.html",
            "search_index": "search-index.json",
            "dataset_manifest": "dataset_manifest.json",
            "home_stats": "home-stats.json",
            "analytics_html": "analytics.html",
            "analytics_year_card": "analytics.html",
            "analytics_chart_data": "analytics-chart-data.js",
            "analytics_chart_bundle": "analytics-chart-bundle.js",
        }
        assert any(target_names[surface] in f.path for f in findings)


class TestRobustness:
    """檢查器在邊界輸入下的行為。"""

    def test_crlf_surfaces_do_not_false_positive(self, tmp_path):
        """CRLF 換行的受管表面仍應判定一致（避免 Windows checkout 誤報）。"""
        root = _build_fixture_root(tmp_path)
        _sync_fixture(root)
        assert check_all(root) == []

        for rel in (
            "README.md",
            "考古題網站/quiz.html",
            "考古題網站/search.html",
            "考古題網站/analytics.html",
        ):
            p = root / rel
            p.write_text(
                p.read_text(encoding="utf-8").replace("\n", "\r\n"),
                encoding="utf-8",
            )
        assert check_all(root) == []

    def test_write_surfaces_tolerates_null_manifest_sections(self, tmp_path):
        """manifest counts/coverage 為 null 時 --write 不應崩潰且能補齊。"""
        root = _build_fixture_root(tmp_path)
        (root / "考古題庫" / "dataset_manifest.json").write_text(
            json.dumps(
                {"schema_version": 1, "counts": None, "coverage": None}
            ),
            encoding="utf-8",
        )
        _sync_fixture(root)
        assert check_all(root) == []

    def test_invalid_exam_json_fails_closed(self, tmp_path):
        root = _build_fixture_root(tmp_path)
        bad = root / "考古題庫" / "行政警察學系" / "116年" / "壞檔"
        bad.mkdir(parents=True)
        (bad / "試題.json").write_text("{not valid json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            build_summary(root / "考古題庫")

    def test_exclusion_inventory_uses_relative_paths_and_reconciles(self, tmp_path):
        root = _build_fixture_root(tmp_path)
        summary = build_summary(root / "考古題庫")
        inventory = summary["exclusion_inventory"]["metadata_duplicate_files"]
        assert len(inventory) == summary["counts"]["duplicate_files"] == 1
        assert all(not Path(item["path"]).is_absolute() for item in inventory)
        assert sum(item["choice"] for item in inventory) == summary["counts"]["duplicate_choice"]
