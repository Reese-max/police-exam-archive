#!/usr/bin/env python3
"""Deep scan of all immigration exam JSON files for essay and structural errors."""

import json
import os
import re
import glob

EXAM_DIR = "考古題庫/國境警察學系移民組"

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def scan_file(filepath):
    """Deep scan a single JSON file."""
    issues = []
    try:
        data = load_json(filepath)
    except Exception as e:
        issues.append(("CRITICAL", f"JSON PARSE ERROR: {e}"))
        return issues

    questions = data.get("questions", [])
    essay_qs = [q for q in questions if q.get("type") == "essay"]
    choice_qs = [q for q in questions if q.get("type") == "choice"]
    subject = data.get("subject", "") or data.get("metadata", {}).get("subject", "")
    year = data.get("year", "?")

    # total_questions mismatch
    total = data.get("total_questions", 0)
    actual = len(questions)
    if total != actual:
        issues.append(("ERROR", f"total_questions={total} but actual count={actual}"))

    # Check section assignments
    has_sections = bool(data.get("sections"))
    for q in questions:
        if q.get("section") is None and has_sections:
            issues.append(("WARNING", f"Q{q['number']} ({q['type']}): section is null despite file having sections"))

    # Check essay questions
    for q in essay_qs:
        stem = q.get("stem", "")
        num = q.get("number", "?")

        # Very short or empty
        if len(stem.strip()) < 10:
            issues.append(("ERROR", f"Q{num} (essay): EMPTY/VERY SHORT STEM ({len(stem.strip())} chars)"))

        # Has options (shouldn't for essay)
        if q.get("options"):
            issues.append(("ERROR", f"Q{num} (essay): HAS OPTIONS DICT - likely should be 'choice' type"))

        # Has single-letter answer
        if q.get("answer") and len(str(q.get("answer", ""))) == 1:
            issues.append(("ERROR", f"Q{num} (essay): HAS SINGLE-LETTER ANSWER '{q['answer']}' - likely should be 'choice' type"))

        # Integer number instead of Chinese numeral
        if isinstance(num, int):
            issues.append(("ERROR", f"Q{num} (essay): NUMBER IS INTEGER (expected Chinese numeral like 一,二,三)"))

        # Pipe character OCR artifacts
        if '|' in stem:
            pipe_count = stem.count('|')
            issues.append(("WARNING", f"Q{num} (essay): {pipe_count} pipe characters (OCR artifact)"))

        # Exam form remnants
        if re.search(r'座號|准考證號|考試編號|准考證', stem):
            issues.append(("ERROR", f"Q{num} (essay): CONTAINS EXAM FORM TEXT (座號/准考證)"))

        # Page markers
        if re.search(r'代號[：:]|全[一二三四五六七八九十\d]+頁|第[一二三四五六七八九十\d]+頁', stem):
            issues.append(("WARNING", f"Q{num} (essay): CONTAINS PAGE MARKER/HEADER"))

        # Section header mixed into stem
        if re.search(r'(?:乙、測驗題|甲、申論題)', stem):
            issues.append(("ERROR", f"Q{num} (essay): SECTION HEADER IN STEM"))

        # Back-of-page text
        if re.search(r'背面尚有試題|請翻面繼續作答', stem):
            issues.append(("ERROR", f"Q{num} (essay): BACK-OF-PAGE INSTRUCTION IN STEM"))
        elif re.search(r'背面', stem) and not re.search(r'背面[的之]|背面臨|背面有', stem):
            # Might be legit use of 背面 in context
            issues.append(("WARNING", f"Q{num} (essay): Contains '背面' - may be page instruction bleed"))

        # Check for sub-question numbering issues in essay (should have proper structure)
        # Missing score annotation
        if not re.search(r'\d+\s*分[）\)]|分\)', stem) and len(stem) > 50:
            issues.append(("INFO", f"Q{num} (essay): No score annotation found"))

        # Check for truncated text (ends abruptly)
        stripped = stem.rstrip()
        if stripped and not re.search(r'[。？！\)）分\n]$', stripped) and len(stripped) > 30:
            last_chars = stripped[-20:]
            issues.append(("WARNING", f"Q{num} (essay): May be truncated, ends with: '...{last_chars}'"))

    # Check choice questions
    for q in choice_qs:
        stem = q.get("stem", "")
        num = q.get("number", "?")
        options = q.get("options", {})
        answer = q.get("answer", "")

        # Missing or incomplete options
        if len(options) < 4:
            issues.append(("ERROR", f"Q{num} (choice): Only {len(options)} options (expected 4)"))

        # Empty options
        for k, v in options.items():
            if not v or not v.strip():
                issues.append(("ERROR", f"Q{num} (choice): EMPTY OPTION {k}"))

        # Missing answer
        if not answer:
            issues.append(("ERROR", f"Q{num} (choice): MISSING ANSWER"))
        elif answer not in options:
            issues.append(("ERROR", f"Q{num} (choice): ANSWER '{answer}' NOT IN OPTIONS {list(options.keys())}"))

        # Very short or empty stem
        if len(stem.strip()) < 5:
            issues.append(("ERROR", f"Q{num} (choice): VERY SHORT/EMPTY STEM"))

        # Chinese numeral number (should be integer for choice)
        if isinstance(num, str) and re.match(r'^[一二三四五六七八九十]+$', num):
            issues.append(("ERROR", f"Q{num} (choice): NUMBER IS CHINESE NUMERAL (expected integer)"))

    # Check sequential numbering
    choice_nums = [q["number"] for q in choice_qs if isinstance(q["number"], int)]
    if choice_nums:
        expected = list(range(1, len(choice_nums) + 1))
        if choice_nums != expected:
            issues.append(("ERROR", f"CHOICE NUMBERING ISSUE: got {choice_nums[:5]}... expected {expected[:5]}..."))

    # Check for duplicate questions
    type_num_pairs = [(q["type"], str(q["number"])) for q in questions]
    seen = {}
    for t, n in type_num_pairs:
        key = f"{t}:{n}"
        if key in seen:
            issues.append(("ERROR", f"DUPLICATE: {t} Q{n} appears multiple times"))
        seen[key] = True

    # Check for questions out of order (essays before choices)
    last_essay_idx = -1
    first_choice_idx = len(questions)
    for i, q in enumerate(questions):
        if q["type"] == "essay":
            last_essay_idx = max(last_essay_idx, i)
        elif q["type"] == "choice" and i < first_choice_idx:
            first_choice_idx = i

    if last_essay_idx > first_choice_idx and first_choice_idx < len(questions):
        issues.append(("WARNING", f"ORDERING: Essay questions appear after choice questions (essay at idx {last_essay_idx}, choice starts at {first_choice_idx})"))

    return issues

def main():
    all_issues = {}
    total_files = 0
    error_count = 0
    warning_count = 0
    info_count = 0

    for root, dirs, files in os.walk(EXAM_DIR):
        for f in files:
            if f == "試題.json":
                filepath = os.path.join(root, f)
                total_files += 1
                issues = scan_file(filepath)
                if issues:
                    rel_path = os.path.relpath(filepath, EXAM_DIR)
                    # Filter out INFO level
                    significant = [(lvl, msg) for lvl, msg in issues if lvl in ("ERROR", "WARNING", "CRITICAL")]
                    if significant:
                        all_issues[rel_path] = issues
                    for lvl, _ in issues:
                        if lvl == "ERROR" or lvl == "CRITICAL":
                            error_count += 1
                        elif lvl == "WARNING":
                            warning_count += 1
                        else:
                            info_count += 1

    print(f"=== Deep Immigration Exam Scan Results ===")
    print(f"Scanned: {total_files} files")
    print(f"Files with significant issues: {len(all_issues)}")
    print(f"Errors: {error_count} | Warnings: {warning_count} | Info: {info_count}")
    print()

    # Group by severity
    for filepath in sorted(all_issues.keys()):
        issues = all_issues[filepath]
        has_errors = any(lvl in ("ERROR", "CRITICAL") for lvl, _ in issues)
        marker = "!!!" if has_errors else "..."
        print(f"{marker} [{filepath}]")
        for lvl, msg in issues:
            if lvl != "INFO":
                print(f"  [{lvl}] {msg}")
        print()

if __name__ == "__main__":
    main()
