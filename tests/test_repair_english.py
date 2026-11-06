import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.parse import ocr_repair
from scripts.rag import repair_english as repair


GLUED = "Theofficerscarefullysearchedtheareaforany"
FIXED = "The officers carefully searched the area for any"
pytestmark = pytest.mark.skipif(not ocr_repair.is_available(), reason="wordninja required")


def test_typical_glue_and_case():
    result, changes, skipped = repair.repair_text(GLUED)
    assert result == FIXED
    assert result.replace(" ", "") == GLUED
    assert len(changes) == 1
    assert not skipped


def test_changed_letter_sequence_is_rejected(monkeypatch):
    with monkeypatch.context() as context:
        context.setattr(ocr_repair, "repair_english_spacing", lambda _: "The officers changed letters")
        repair.split_candidate.cache_clear()
        result, changes, skipped = repair.repair_text(GLUED)
        assert result == GLUED
        assert not changes
        assert skipped[0]["reason"] == "letter_sequence_changed"
    repair.split_candidate.cache_clear()


def test_chinese_and_punctuation_are_exactly_preserved():
    text = f"題目：{GLUED}，選項（DNA）；不要更動。"
    result, changes, _ = repair.repair_text(text)
    assert result == f"題目：{FIXED}，選項（DNA）；不要更動。"
    assert changes[0]["before"] == GLUED


@pytest.mark.parametrize("text", [
    "FBI CIA DNA GPS TOEFL IELTS HTTP HTTPS AI SQL Wi-Fi",
    "HTTPHTTPS FBIinvestigators",
    f"https://example.org/{GLUED}?q=abc www.example.org/{GLUED}",
    f"{GLUED}@example.com",
    f"`{GLUED}` ```python\n{GLUED}\n```",
    f"${GLUED}$ \\({GLUED}\\)",
    f"{GLUED}123 Article12345 {GLUED}_value",
    f"{GLUED}(value) obj.{GLUED} C:\\data\\{GLUED}",
    f"{GLUED}=variable {GLUED}+something",
    "NaClCOOH HCOOHCHCOOH SomeCamelCaseIdentifier",
    "This is a normal English sentence, even in to and th rough stay unchanged.",
    "The overarching field of photogrammetry uses chatbots and specialness.",
])
def test_protected_and_already_spaced_text(text):
    result, changes, _ = repair.repair_text(text)
    assert result == text
    assert not changes


def test_low_confidence_is_reported():
    result, changes, skipped = repair.repair_text("photogrammetry")
    assert result == "photogrammetry"
    assert not changes
    assert skipped[0]["reason"] == "uncertain_short_piece"


@pytest.mark.parametrize("text", ["Thevenin", "indanedione", "Beckeline", "invariance", "Reppetto", "consulado", "setempat"])
def test_technical_names_and_other_languages_without_english_context(text):
    result, changes, skipped = repair.repair_text(text, english_context=False)
    assert result == text
    assert not changes
    assert skipped


def test_self_contained_long_english_context():
    result, changes, _ = repair.repair_text(GLUED, english_context=False)
    assert result == FIXED
    assert changes


def test_context_is_stable_after_long_repairs():
    text = "Whichofthefollowingismentionedinthepassage inhoping"
    context = repair.has_english_context("外國文(法文兼試移民專業英文)", [text])
    first, changes, _ = repair.repair_text(text, context)
    assert context
    assert len(changes) == 2
    assert first.endswith("in hoping")
    second_context = repair.has_english_context("外國文(法文兼試移民專業英文)", [first])
    assert second_context == context
    second, changes, _ = repair.repair_text(first, second_context)
    assert second == first
    assert not changes


def test_idempotence():
    text = f"{GLUED}. Whichofthefollowingis correct?"
    first, changes, _ = repair.repair_text(text)
    assert changes
    second, second_changes, _ = repair.repair_text(first)
    assert second == first
    assert not second_changes


def test_patch_preserves_literal_escapes_and_surrounding_format():
    text = ('{\r\n\t"metadata":{"subject":"' + GLUED + '"},\r\n'
            '\t"questions":[{"stem":"' + GLUED + '","notes":"\\u8cc7\\u6599",'
            '"options":{"B":"\\\"literal\\\""}}]\r\n}\r\n')
    result = repair.patch_json(text, json.loads(text), {("questions", 0, "stem"): FIXED})
    assert result == text.replace(f'"stem":"{GLUED}"', f'"stem":"{FIXED}"')


@pytest.mark.parametrize("indent,newline,bom", [(2, "\r\n", True), (4, "\n", False), (None, "\n", False)])
def test_scan_only_targets_and_preserves_json_format(tmp_path, indent, newline, bom):
    root = tmp_path / "bank"
    file = root / "english" / "試題.json"
    file.parent.mkdir(parents=True)
    data = {
        "metadata": {"subject": GLUED}, "notes": [GLUED],
        "questions": [{"number": 9, "type": "choice", "stem": GLUED,
                       "options": {"A": GLUED, "B": "正常\\路徑\"quoted\""},
                       "passage": GLUED, "passage_intro": GLUED,
                       "answer": GLUED, "section": GLUED, "notes": [GLUED]}],
    }
    text = json.dumps(data, ensure_ascii=False, indent=indent).replace("\n", newline) + newline
    prefix = b"\xef\xbb\xbf" if bom else b""
    original = prefix + text.encode("utf-8")
    file.write_bytes(original)
    dry = repair.scan(root)
    assert file.read_bytes() == original
    assert dry["summary"]["proposed_modifications"] == 4
    assert dry["summary"]["actual_modifications"] == 0
    applied = repair.scan(root, apply=True)
    expected = text
    for field in ("stem", "A", "passage", "passage_intro"):
        expected = expected.replace(f'"{field}": "{GLUED}"', f'"{field}": "{FIXED}"')
    assert file.read_bytes() == prefix + expected.encode("utf-8")
    assert applied["summary"]["scanned_questions"] == 1
    assert applied["summary"]["actual_modifications"] == 4
    assert {item["field"] for item in applied["changes"]} == {"stem", "options.A", "passage", "passage_intro"}
    second = repair.scan(root)
    assert second["summary"]["proposed_modifications"] == 0
    assert second["summary"]["detected_candidates"] == second["summary"]["skipped"]
    assert second == repair.scan(root)


def test_cli_defaults_to_dry_run_and_deterministic_report(tmp_path):
    root = tmp_path / "bank"
    root.mkdir()
    file = root / "試題.json"
    original = json.dumps({"questions": [{"number": 1, "stem": GLUED}]}).encode()
    file.write_bytes(original)
    report = tmp_path / "report.json"
    command = [sys.executable, str(Path(repair.__file__)), "--root", str(root), "--report", str(report)]
    first = subprocess.run(command, capture_output=True, check=True)
    first_bytes = report.read_bytes()
    second = subprocess.run(command, capture_output=True, check=True)
    assert first.stdout == second.stdout
    assert report.read_bytes() == first_bytes
    assert file.read_bytes() == original
    assert json.loads(first_bytes)["summary"]["actual_modifications"] == 0


def test_missing_dependency_fails_closed(monkeypatch):
    monkeypatch.setattr(ocr_repair, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="wordninja is required"):
        repair.scan(Path("."))
