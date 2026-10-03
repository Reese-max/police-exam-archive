#!/usr/bin/env python3
"""Quality summary artifact and drift detection tests.

Ensures all public corpus counts and quality denominators derive from a single
machine-readable artifact and CI fails on any drift.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUALITY_SUMMARY = PROJECT_ROOT / "考古題庫" / "quality_summary.json"
README = PROJECT_ROOT / "README.md"
QUIZ_HTML = PROJECT_ROOT / "考古題網站" / "quiz.html"
MANIFEST = PROJECT_ROOT / "考古題庫" / "dataset_manifest.json"


def load_quality_summary():
    """Load the quality summary artifact."""
    if not QUALITY_SUMMARY.exists():
        return None
    return json.loads(QUALITY_SUMMARY.read_text(encoding="utf-8"))


class TestQualitySummaryArtifact:
    """Tests for the quality summary artifact itself."""

    def test_artifact_exists(self):
        """Quality summary artifact must exist."""
        assert QUALITY_SUMMARY.exists(), f"Quality summary not found at {QUALITY_SUMMARY}"

    def test_artifact_schema_version(self):
        """Artifact must have schema_version."""
        data = load_quality_summary()
        assert data is not None
        assert "schema_version" in data
        assert data["schema_version"] >= 1

    def test_artifact_has_snapshot_info(self):
        """Artifact must have snapshot/version identification."""
        data = load_quality_summary()
        assert data is not None
        assert "snapshot" in data
        snap = data["snapshot"]
        assert "generated_at" in snap
        assert "commit_sha" in snap
        assert "corpus_version" in snap  # e.g., "106-115"
        assert "inclusion_rules" in snap
        assert "exclusion_rules" in snap

    def test_artifact_has_correct_counts(self):
        """Artifact counts must match current corpus: 36760 choice, 5758 essay, 42518 total."""
        data = load_quality_summary()
        assert data is not None
        counts = data.get("counts", {})
        assert counts.get("choice") == 36760, f"Choice count mismatch: {counts.get('choice')}"
        assert counts.get("essay") == 5758, f"Essay count mismatch: {counts.get('essay')}"
        assert counts.get("questions") == 42518, f"Total count mismatch: {counts.get('questions')}"
        assert counts.get("json_files") == 2049
        assert counts.get("categories") == 49
        assert counts.get("subjects") == 101

    def test_artifact_has_duplicate_exclusion_count(self):
        """Artifact must report duplicate exclusion count separately."""
        data = load_quality_summary()
        assert data is not None
        assert "duplicate_exclusions" in data
        dup = data["duplicate_exclusions"]
        assert "papers" in dup
        assert "questions" in dup
        assert isinstance(dup["papers"], int)
        assert isinstance(dup["questions"], int)

    def test_artifact_has_quality_metrics(self):
        """Artifact must have quality metrics with numerator/denominator."""
        data = load_quality_summary()
        assert data is not None
        assert "quality" in data
        quality = data["quality"]
        assert "option_completeness" in quality
        assert "answer_legality" in quality
        for metric in ("option_completeness", "answer_legality"):
            m = quality[metric]
            assert "numerator" in m
            assert "denominator" in m
            assert "rate" in m
            # Denominator must equal full non-duplicate choice scope
            assert m["denominator"] == 36760, f"{metric} denominator mismatch: {m['denominator']}"
            # Rate should be 1.0 (100%)
            assert m["rate"] == 1.0, f"{metric} rate not 100%: {m['rate']}"

    def test_artifact_includes_year_115_questions(self):
        """Artifact must explicitly include year-115 questions in quality scope."""
        data = load_quality_summary()
        assert data is not None
        snap = data["snapshot"]
        # The corpus version should include 115
        assert "115" in snap["corpus_version"]
        # Inclusion rules should mention year 115
        assert any("115" in str(r) for r in snap["inclusion_rules"])


class TestReadmeQualitySection:
    """Tests that README quality section matches the artifact."""

    def test_readme_quality_denominator_matches_artifact(self):
        """README quality denominators must match artifact choice count (36760)."""
        readme_text = README.read_text(encoding="utf-8")
        # Find the quality section
        quality_section = re.search(r"## 資料品質\n(.*?)(?=\n## |\Z)", readme_text, re.DOTALL)
        assert quality_section, "README quality section not found"
        section_text = quality_section.group(1)
        # Check option completeness
        opt_match = re.search(r"選項完整率.*?(\d[\d,]*)/(\d[\d,]*)", section_text)
        assert opt_match, "選項完整率 not found in README"
        opt_num, opt_den = int(opt_match.group(1).replace(",", "")), int(opt_match.group(2).replace(",", ""))
        assert opt_den == 36760, f"README option completeness denominator {opt_den} != 36760"
        assert opt_num == 36760, f"README option completeness numerator {opt_num} != 36760"
        # Check answer legality
        ans_match = re.search(r"答案合法率.*?(\d[\d,]*)/(\d[\d,]*)", section_text)
        assert ans_match, "答案合法率 not found in README"
        ans_num, ans_den = int(ans_match.group(1).replace(",", "")), int(ans_match.group(2).replace(",", ""))
        assert ans_den == 36760, f"README answer legality denominator {ans_den} != 36760"
        assert ans_num == 36760, f"README answer legality numerator {ans_num} != 36760"


class TestQuizHtmlComment:
    """Tests that quiz.html source comment matches the artifact."""

    def test_quiz_html_comment_matches_artifact(self):
        """quiz.html comment must reference 36760 choice questions."""
        quiz_text = QUIZ_HTML.read_text(encoding="utf-8")
        # Find the comment mentioning choice question count
        # Original: "真實題庫（minisearch + search-engine.js，36,210 道選擇題）"
        comment_match = re.search(r"真實題庫.*?(\d[\d,]*)\s*道選擇題", quiz_text)
        assert comment_match, "Quiz HTML choice count comment not found"
        count = int(comment_match.group(1).replace(",", ""))
        assert count == 36760, f"Quiz HTML comment count {count} != 36760"


class TestManifestConsistency:
    """Tests that dataset_manifest.json matches the artifact."""

    def test_manifest_counts_match_artifact(self):
        """Manifest counts must match quality summary counts."""
        manifest_data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        summary_data = load_quality_summary()
        assert manifest_data["counts"]["choice"] == summary_data["counts"]["choice"]
        assert manifest_data["counts"]["essay"] == summary_data["counts"]["essay"]
        assert manifest_data["counts"]["questions"] == summary_data["counts"]["questions"]
        assert manifest_data["counts"]["json_files"] == summary_data["counts"]["json_files"]
        assert manifest_data["counts"]["categories"] == summary_data["counts"]["categories"]
        assert manifest_data["counts"]["subjects"] == summary_data["counts"]["subjects"]


class TestDriftDetection:
    """Tests for drift detection mechanism."""

    def test_drift_check_script_exists(self):
        """Drift check script must exist."""
        drift_check = PROJECT_ROOT / "scripts" / "check_quality_drift.py"
        assert drift_check.exists(), "Drift check script not found"

    def test_drift_check_fails_on_readme_drift(self, tmp_path):
        """Drift check must fail when README quality denominator is changed."""
        drift_check = PROJECT_ROOT / "scripts" / "check_quality_drift.py"
        # Create a modified README with wrong denominator
        readme_text = README.read_text(encoding="utf-8")
        modified_readme = readme_text.replace("36,760/36,760", "36,210/36,210")
        modified_readme = modified_readme.replace("36760/36760", "36210/36210")

        test_readme = tmp_path / "README.md"
        test_readme.write_text(modified_readme, encoding="utf-8")

        # Run drift check with modified README
        result = subprocess.run(
            [sys.executable, str(drift_check), "--readme", str(test_readme)],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.returncode != 0, "Drift check should fail on README denominator mismatch"
        assert "README" in result.stdout or "README" in result.stderr

    def test_drift_check_fails_on_quiz_drift(self, tmp_path):
        """Drift check must fail when quiz.html comment is changed."""
        drift_check = PROJECT_ROOT / "scripts" / "check_quality_drift.py"
        quiz_text = QUIZ_HTML.read_text(encoding="utf-8")
        modified_quiz = quiz_text.replace("36,760 道選擇題", "36,210 道選擇題")
        modified_quiz = modified_quiz.replace("36760 道選擇題", "36210 道選擇題")

        test_quiz = tmp_path / "quiz.html"
        test_quiz.write_text(modified_quiz, encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(drift_check), "--quiz", str(test_quiz)],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.returncode != 0, "Drift check should fail on quiz.html comment mismatch"
        assert "quiz" in result.stdout.lower() or "quiz" in result.stderr.lower()

    def test_drift_check_passes_on_correct_files(self):
        """Drift check must pass when all files match the artifact."""
        drift_check = PROJECT_ROOT / "scripts" / "check_quality_drift.py"
        result = subprocess.run(
            [sys.executable, str(drift_check)],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0, f"Drift check failed unexpectedly: {result.stdout} {result.stderr}"


class TestYearlyImportPropagation:
    """Tests that a new yearly import updates all governed counts together."""

    def test_fixture_import_changes_all_counts(self, tmp_path):
        """Simulate a new yearly import and verify all counts update together."""
        # This test will be implemented after the quality summary generator
        # creates the artifact. For now, it's a placeholder for the acceptance criteria.
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])