#!/usr/bin/env python3
"""Scan all immigration exam JSON files for essay question analysis errors."""

import json
import os
import re
import glob

EXAM_DIR = "考古題庫/國境警察學系移民組"

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def scan_file(filepath):
    """Scan a single JSON file for essay question errors."""
    issues = []
    try:
        data = load_json(filepath)
    except Exception as e:
        issues.append(f"  JSON PARSE ERROR: {e}")
        return issues

    questions = data.get("questions", [])
    essay_qs = [q for q in questions if q.get("type") == "essay"]
    choice_qs = [q for q in questions if q.get("type") == "choice"]

    # Check total_questions vs actual count
    total = data.get("total_questions", 0)
    actual = len(questions)
    if total != actual:
        issues.append(f"  MISMATCH: total_questions={total} but actual={actual}")

    for q in essay_qs:
        stem = q.get("stem", "")
        num = q.get("number", "?")

        # 1. Very short essay stems (likely truncated or empty)
        if len(stem.strip()) < 20:
            issues.append(f"  Q{num} (essay): VERY SHORT STEM ({len(stem.strip())} chars): '{stem.strip()[:50]}'")

        # 2. Pipe characters (OCR artifact from scan)
        if '|' in stem:
            issues.append(f"  Q{num} (essay): CONTAINS PIPE CHARACTER '|' (OCR artifact)")

        # 3. Seat number / exam number remnants
        if re.search(r'座號|准考證|姓名欄|考試編號', stem):
            issues.append(f"  Q{num} (essay): CONTAINS EXAM FORM REMNANTS (座號/准考證)")

        # 4. Page markers or headers bleeding in
        if re.search(r'代號：|全[一二三四五六七八九十]頁|第[一二三四五六七八九十\d]+頁', stem):
            issues.append(f"  Q{num} (essay): CONTAINS PAGE MARKER/HEADER BLEEDING")

        # 5. Check for choice-like patterns in essay questions (might be mis-typed)
        if re.search(r'\([A-D]\)', stem) and not re.search(r'[一二三四]、', str(num)):
            # Has (A)(B)(C)(D) patterns - might be choice question mistyped as essay
            option_count = len(re.findall(r'\([A-D]\)', stem))
            if option_count >= 3:
                issues.append(f"  Q{num} (essay): HAS {option_count} CHOICE-LIKE OPTIONS (A)(B)(C)(D) - may be mistyped as essay")

        # 6. Check for garbled/corrupted text (high density of special chars)
        special_chars = len(re.findall(r'[^\w\s\u4e00-\u9fff\u3000-\u303f\uff00-\uffef,.;:!?()（）、。，：；！？「」『』【】\-\d\n]', stem))
        if len(stem) > 0 and special_chars / len(stem) > 0.05:
            issues.append(f"  Q{num} (essay): HIGH SPECIAL CHAR DENSITY ({special_chars}/{len(stem)})")

        # 7. Check for "背面" (back of page) text bleeding
        if re.search(r'背面|翻面|反面', stem):
            issues.append(f"  Q{num} (essay): CONTAINS BACK-OF-PAGE TEXT (背面/翻面)")

        # 8. Check for duplicate content or fragments
        if stem.count(stem[:30]) > 1 if len(stem) > 30 else False:
            issues.append(f"  Q{num} (essay): POSSIBLE DUPLICATE CONTENT")

        # 9. Check for number formatting issues in essay numbering
        if isinstance(num, int):
            issues.append(f"  Q{num} (essay): ESSAY NUMBER IS INTEGER (should be Chinese numeral)")

        # 10. Check for options dict in essay questions (should not have)
        if q.get("options"):
            issues.append(f"  Q{num} (essay): ESSAY HAS OPTIONS DICT (should be choice type?)")

        # 11. Check for answer in essay questions (should not have single-letter answer)
        if q.get("answer") and len(str(q.get("answer", ""))) == 1:
            issues.append(f"  Q{num} (essay): ESSAY HAS SINGLE-LETTER ANSWER '{q.get('answer')}' (should be choice?)")

        # 12. Check for fragmented text (lines that are too short, suggesting bad OCR splitting)
        lines = stem.split('\n')
        very_short_lines = [l for l in lines if 0 < len(l.strip()) < 5]
        if len(very_short_lines) > 3:
            issues.append(f"  Q{num} (essay): MANY VERY SHORT LINES ({len(very_short_lines)}) - possible text fragmentation")

        # 13. Check for section text bleeding into stem
        if re.search(r'^[甲乙丙丁]、', stem.strip()):
            issues.append(f"  Q{num} (essay): STEM STARTS WITH SECTION MARKER")

        # 14. Check for other question's content mixed in
        if re.search(r'(?:乙、測驗題|甲、申論題)', stem):
            issues.append(f"  Q{num} (essay): SECTION HEADER MIXED INTO STEM")

        # 15. Incomplete parenthesized scoring - missing score
        if re.search(r'\(\s*分\)', stem):
            issues.append(f"  Q{num} (essay): INCOMPLETE SCORE MARKER '( 分)'")

    # Check for choice questions that might actually be essays
    for q in choice_qs:
        stem = q.get("stem", "")
        num = q.get("number", "?")

        # Choice question with very long stem and no options
        if not q.get("options") or len(q.get("options", {})) < 2:
            issues.append(f"  Q{num} (choice): MISSING OR INCOMPLETE OPTIONS")

        # Check for empty/missing answer
        if not q.get("answer"):
            issues.append(f"  Q{num} (choice): MISSING ANSWER")

        # Check for empty options
        if q.get("options"):
            for opt_key, opt_val in q["options"].items():
                if not opt_val or not opt_val.strip():
                    issues.append(f"  Q{num} (choice): EMPTY OPTION {opt_key}")

    # Check for sequential number issues
    essay_nums = []
    choice_nums = []
    for q in questions:
        if q["type"] == "essay":
            essay_nums.append(q["number"])
        elif q["type"] == "choice":
            choice_nums.append(q["number"])

    # Check choice question numbering
    if choice_nums:
        expected = list(range(1, len(choice_nums) + 1))
        actual_nums = [n for n in choice_nums if isinstance(n, int)]
        if actual_nums and actual_nums != expected:
            issues.append(f"  CHOICE NUMBERING: expected {expected[:3]}...{expected[-1]} but got {actual_nums[:3]}...{actual_nums[-1] if actual_nums else '?'}")

    # Check for duplicate question numbers
    all_nums = [(q["type"], q["number"]) for q in questions]
    seen = set()
    for t, n in all_nums:
        key = f"{t}:{n}"
        if key in seen:
            issues.append(f"  DUPLICATE: {t} Q{n} appears multiple times")
        seen.add(key)

    return issues

def main():
    all_issues = {}
    total_files = 0
    total_issues = 0

    for root, dirs, files in os.walk(EXAM_DIR):
        for f in files:
            if f == "試題.json":
                filepath = os.path.join(root, f)
                total_files += 1
                issues = scan_file(filepath)
                if issues:
                    rel_path = os.path.relpath(filepath, EXAM_DIR)
                    all_issues[rel_path] = issues
                    total_issues += len(issues)

    print(f"=== Immigration Exam Essay Error Scan ===")
    print(f"Scanned: {total_files} files")
    print(f"Files with issues: {len(all_issues)}")
    print(f"Total issues: {total_issues}")
    print()

    for filepath, issues in sorted(all_issues.items()):
        print(f"[{filepath}]")
        for issue in issues:
            print(issue)
        print()

if __name__ == "__main__":
    main()
