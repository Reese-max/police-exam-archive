#!/usr/bin/env python3
"""
Agent 2: Structural & Content Quality Scanner for Police Exam Archive
Scans all exam JSON files for structural/content quality issues.
"""

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path("/home/user/police-exam-archive/考古題庫")
OUTPUT_FILE = Path("/home/user/police-exam-archive/agent2_structural_report.json")

# ============================================================
# Pattern Definitions
# ============================================================

# Category 1: Exam header/footer content leaked into stem
HEADER_FOOTER_PATTERNS = [
    (r"代號[：:]", "代號 (exam code marker)"),
    (r"頁次\s*[:：]?\s*\d", "頁次 (page number)"),
    (r"座號", "座號 (seat number)"),
    (r"等別\s*[:：]", "等別 (exam level marker)"),
    (r"類科\s*[:：]", "類科 (category marker)"),
    (r"科目\s*[:：]", "科目 (subject marker)"),
    (r"考試時間\s*[:：]", "考試時間 (exam time marker)"),
    (r"全[一二三四五六七八九十]+頁", "全X頁 (total pages marker)"),
    (r"第\s*\d+\s*頁", "第X頁 (page X marker)"),
    (r"考試別\s*[:：]", "考試別 (exam type marker)"),
    (r"類\s*科\s*[:：]", "類 科 (category marker with space)"),
    (r"代\s*號\s*[:：]", "代 號 (code marker with space)"),
]

# Category 2: Instruction text that shouldn't be in stems
INSTRUCTION_PATTERNS = [
    (r"不必抄題", "不必抄題 (don't copy questions instruction)"),
    (r"申論試卷", "申論試卷 (essay answer sheet reference)"),
    (r"禁止使用電子計算器", "禁止使用電子計算器 (calculator prohibition)"),
    (r"2B\s*鉛筆", "2B鉛筆 (2B pencil instruction)"),
    (r"可以使用電子計算器", "可以使用電子計算器 (calculator permission)"),
    (r"於本試題上作答者.*不予計分", "於本試題上作答者不予計分 (answer sheet warning)"),
    (r"請選出一個正確或最適當的?答案", "請選出一個正確或最適當的答案 (standard instruction prefix)"),
    (r"複選作答者.*該題不予計分", "複選作答者該題不予計分 (multiple selection warning)"),
    (r"須用2B鉛筆", "須用2B鉛筆 (2B pencil requirement)"),
    (r"在試卡上依題號清楚劃記", "在試卡上依題號清楚劃記 (answer card instruction)"),
    (r"藍、?黑色鋼筆或原子筆", "藍黑色鋼筆或原子筆 (pen color instruction)"),
    (r"不得於試卷上書寫姓名", "不得於試卷上書寫姓名 (name writing prohibition)"),
    (r"入場證號", "入場證號 (admission number reference)"),
    (r"本試題為單一選擇題", "本試題為單一選擇題 (single choice instruction)"),
    (r"注意.*[：:]", "注意 (attention/note header in stem)"),
]

# Category 4: Exam metadata patterns in options
OPTION_METADATA_PATTERNS = [
    (r"代號[：:]", "代號 (exam code in option)"),
    (r"頁次\s*[:：]?\s*\d", "頁次 (page number in option)"),
    (r"座號", "座號 (seat number in option)"),
    (r"等別\s*[:：]", "等別 (exam level in option)"),
    (r"類科\s*[:：]", "類科 (category in option)"),
    (r"科目\s*[:：]", "科目 (subject in option)"),
    (r"考試時間\s*[:：]", "考試時間 (exam time in option)"),
    (r"全[一二三四五六七八九十]+頁", "全X頁 (total pages in option)"),
    (r"第\s*\d+\s*頁", "第X頁 (page X in option)"),
    (r"不必抄題", "不必抄題 (instruction in option)"),
    (r"申論試卷", "申論試卷 (essay sheet in option)"),
    (r"2B\s*鉛筆", "2B鉛筆 (2B pencil in option)"),
    (r"禁止使用電子計算器", "禁止使用電子計算器 (calculator prohibition in option)"),
    (r"考試別\s*[:：]", "考試別 (exam type in option)"),
    (r"代\s*號\s*[:：]?\s*\d{3,}", "代號+number (exam code number in option)"),
]

# Standard instruction patterns that are expected in notes
# Notes entries matching these are considered normal/expected
STANDARD_NOTE_PATTERNS = [
    r"^[\s]*※",             # starts with ※
    r"^[\s]*[①②③④⑤⑥⑦⑧⑨⑩]",  # starts with circled number
    r"^[\s]*甲、",           # section marker 甲
    r"^[\s]*乙、",           # section marker 乙
    r"^[\s]*丙、",           # section marker 丙
    r"^[\s]*丁、",           # section marker 丁
    r"^[\s]*注意",           # starts with 注意
    r"^[\s]*本試題",         # starts with 本試題
    r"^[\s]*本科目",         # starts with 本科目
    r"^[\s]*本測驗",         # starts with 本測驗
    r"^[\s]*請以",           # starts with 請以
    r"^[\s]*不必",           # starts with 不必
    r"^[\s]*不得",           # starts with 不得
    r"^[\s]*共\d+題",        # starts with 共X題
    r"^[\s]*每題",           # starts with 每題
    r"^[\s]*須用",           # starts with 須用
    r"^[\s]*式作答",         # continuation of instruction
    r"^[\s]*禁止",           # starts with 禁止
    r"^[\s]*可以使用",       # starts with 可以使用
    r"^[\s]*作答",           # starts with 作答
    r"^[\s]*$",              # empty
]


def is_standard_note(note_text):
    """Check if a note entry matches standard instruction patterns."""
    stripped = note_text.strip()
    if not stripped:
        return True  # empty is handled separately

    for pattern in STANDARD_NOTE_PATTERNS:
        if re.match(pattern, stripped):
            return True

    # Also check for common instruction keywords anywhere in short notes
    if len(stripped) <= 60:
        instruction_keywords = [
            "注意", "不必抄題", "試卷", "鉛筆", "試卡",
            "計分", "選擇題", "鋼筆", "原子筆", "電子計算器",
            "書寫姓名", "座號", "申論", "測驗", "作文", "公文",
            "橫式作答", "本國文字"
        ]
        for kw in instruction_keywords:
            if kw in stripped:
                return True

    return False


def classify_non_standard_note(note_text, all_notes, note_idx):
    """Classify what type of non-standard content a note contains."""
    stripped = note_text.strip()

    # Check if it's part of a multi-line essay/question prompt leaked into notes
    # Indicators: plain Chinese prose, no instruction keywords, part of a sequence
    # of similar non-standard notes
    adjacent_non_standard = 0
    for i in range(max(0, note_idx - 2), min(len(all_notes), note_idx + 3)):
        if i != note_idx and not is_standard_note(str(all_notes[i])):
            adjacent_non_standard += 1

    # Check for mathematical/formula content (reference tables, formulas)
    has_math = bool(re.search(r"[πΣ∫∞≤≥±√∆]|[a-z]\s*[=<>]|f\s*\(|MHz|GHz|KHz|dB|sin|cos|log|exp|pdf", stripped))
    has_stats_table = bool(re.search(r"[χtFz]\s*[\(（]?\s*\d+\.?\d*\s*[;,]\s*\d", stripped))

    # Detect types
    if has_math or has_stats_table:
        return "notes_leaked_formula_or_table", "Mathematical formula, statistical table, or technical reference data leaked into notes"
    elif adjacent_non_standard >= 2:
        return "notes_leaked_question_content", "Question/essay prompt content leaked into notes (part of multi-line sequence)"
    elif re.match(r"^[\s]*[（(]\s*\d+\s*分\s*[)）]", stripped):
        return "notes_leaked_score_marker", "Score/point marker leaked into notes"
    elif re.match(r"^[\s]*英文作文", stripped):
        return "notes_leaked_question_content", "Essay writing prompt header leaked into notes"
    elif re.match(r"^[\s]*[\w\s]*[:：]$", stripped) and len(stripped) < 20:
        return "notes_leaked_section_header", "Section header or label leaked into notes"
    elif len(stripped) <= 10 and re.match(r"^[\s]*[（(].*[)）]\s*$|^[\s]*\d+\s*$|^[\s]*[a-zA-Z]\s*$|^[\s]*π\s*$", stripped):
        return "notes_leaked_formula_fragment", "Formula fragment or isolated symbol leaked into notes"
    else:
        return "notes_non_standard_content", "Non-standard content in notes that doesn't match expected instruction patterns"


def scan_file(filepath):
    """Scan a single JSON file for all quality issues."""
    issues = []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        issues.append({
            "category": "json_parse_error",
            "severity": "critical",
            "message": f"JSON parse error: {str(e)}",
            "file": str(filepath),
        })
        return issues
    except Exception as e:
        issues.append({
            "category": "file_read_error",
            "severity": "critical",
            "message": f"File read error: {str(e)}",
            "file": str(filepath),
        })
        return issues

    rel_path = str(filepath.relative_to(BASE_DIR))
    questions = data.get("questions", [])
    notes = data.get("notes", [])
    metadata = data.get("metadata", {})

    # --------------------------------------------------------
    # Check 1: Header/footer content leaked into stem
    # --------------------------------------------------------
    for q in questions:
        stem = q.get("stem", "")
        qnum = q.get("number", "?")
        qtype = q.get("type", "unknown")

        if not stem:
            continue

        for pattern, desc in HEADER_FOOTER_PATTERNS:
            if re.search(pattern, stem):
                issues.append({
                    "category": "header_footer_leak_in_stem",
                    "severity": "high",
                    "file": rel_path,
                    "question_number": qnum,
                    "question_type": qtype,
                    "pattern_matched": desc,
                    "stem_excerpt": stem[:200],
                })

    # --------------------------------------------------------
    # Check 2: Instruction text in stem
    # --------------------------------------------------------
    for q in questions:
        stem = q.get("stem", "")
        qnum = q.get("number", "?")
        qtype = q.get("type", "unknown")

        if not stem:
            continue

        for pattern, desc in INSTRUCTION_PATTERNS:
            if re.search(pattern, stem):
                # Filter: "注意" might be used legitimately in question context
                if desc.startswith("注意") and not re.match(r"^[\s※]*注意", stem):
                    continue
                issues.append({
                    "category": "instruction_text_in_stem",
                    "severity": "high",
                    "file": rel_path,
                    "question_number": qnum,
                    "question_type": qtype,
                    "pattern_matched": desc,
                    "stem_excerpt": stem[:200],
                })

    # --------------------------------------------------------
    # Check 3: Missing answer for choice-type questions
    # --------------------------------------------------------
    for q in questions:
        qnum = q.get("number", "?")
        qtype = q.get("type", "")

        if qtype == "choice":
            answer = q.get("answer")
            if answer is None or (isinstance(answer, str) and answer.strip() == ""):
                issues.append({
                    "category": "missing_answer_for_choice",
                    "severity": "critical",
                    "file": rel_path,
                    "question_number": qnum,
                    "question_type": qtype,
                    "stem_excerpt": q.get("stem", "")[:150],
                })

    # --------------------------------------------------------
    # Check 4: Options contain exam metadata OR reading passages
    # --------------------------------------------------------
    for q in questions:
        options = q.get("options", {})
        qnum = q.get("number", "?")
        qtype = q.get("type", "unknown")

        if not options:
            continue

        for opt_key, opt_val in options.items():
            if not opt_val:
                continue
            val_str = str(opt_val)

            # 4a: Check for exam metadata in options
            # Use stricter matching to avoid false positives with legitimate legal content
            strict_metadata_patterns = [
                (r"頁次\s*[:：]?\s*\d", "頁次 (page number in option)"),
                (r"座號", "座號 (seat number in option)"),
                (r"等別\s*[:：]", "等別 (exam level in option)"),
                (r"類科\s*[:：]", "類科 (category in option)"),
                (r"考試時間\s*[:：]", "考試時間 (exam time in option)"),
                (r"全[一二三四五六七八九十]+頁", "全X頁 (total pages in option)"),
                (r"不必抄題", "不必抄題 (instruction in option)"),
                (r"禁止使用電子計算器", "禁止使用電子計算器 (calculator prohibition in option)"),
                (r"考\s*試\s*別\s*[:：]", "考試別 (exam type marker in option)"),
            ]
            for pattern, desc in strict_metadata_patterns:
                if re.search(pattern, val_str):
                    issues.append({
                        "category": "metadata_in_options",
                        "severity": "high",
                        "file": rel_path,
                        "question_number": qnum,
                        "question_type": qtype,
                        "option_key": opt_key,
                        "option_value": val_str[:200],
                        "pattern_matched": desc,
                    })

            # 4b: Check for reading passage content leaked into options
            # This happens when a reading passage for subsequent questions
            # gets appended to the last option of the preceding question
            passage_intro_patterns = [
                r"請依下文回答第?\d+至第?\d+題",
                r"請回答下列第?\d+題至第?\d+題",
                r"請閱讀下文後.{0,10}回答",
                r"第\d+題至第\d+題為篇章結構題組",
                r"請依下文回答",
            ]
            for ppat in passage_intro_patterns:
                if re.search(ppat, val_str):
                    issues.append({
                        "category": "reading_passage_leaked_into_option",
                        "severity": "high",
                        "file": rel_path,
                        "question_number": qnum,
                        "question_type": qtype,
                        "option_key": opt_key,
                        "option_value_length": len(val_str),
                        "option_excerpt": val_str[:200],
                        "message": "Reading passage for subsequent questions leaked into this option value",
                    })
                    break  # Don't double-report for same option

            # 4c: Check for abnormally long option values (> 200 chars)
            # which may indicate content concatenation errors
            if len(val_str) > 200:
                # Only flag if not already flagged by 4b
                already_flagged = any(
                    i.get("category") == "reading_passage_leaked_into_option"
                    and i.get("question_number") == qnum
                    and i.get("option_key") == opt_key
                    for i in issues
                )
                if not already_flagged:
                    issues.append({
                        "category": "abnormally_long_option",
                        "severity": "medium",
                        "file": rel_path,
                        "question_number": qnum,
                        "question_type": qtype,
                        "option_key": opt_key,
                        "option_value_length": len(val_str),
                        "option_excerpt": val_str[:200],
                        "message": f"Option value is unusually long ({len(val_str)} chars), may contain concatenated content",
                    })

    # --------------------------------------------------------
    # Check 5: Notes containing irrelevant/leaked content
    # This is a comprehensive check that detects:
    # - Question/essay content leaked into notes (split across lines)
    # - Mathematical formulas/tables leaked into notes
    # - Score markers, section headers, fragments
    # - Empty notes entries
    # --------------------------------------------------------
    if notes:
        non_standard_indices = []
        for idx, note in enumerate(notes):
            if not isinstance(note, str):
                issues.append({
                    "category": "notes_invalid_type",
                    "severity": "medium",
                    "file": rel_path,
                    "note_index": idx,
                    "note_content": str(note)[:200],
                    "message": f"Note is not a string, type={type(note).__name__}",
                })
                continue

            note_stripped = note.strip()

            # Check for empty notes
            if note_stripped == "":
                issues.append({
                    "category": "notes_empty_entry",
                    "severity": "low",
                    "file": rel_path,
                    "note_index": idx,
                    "message": "Empty note entry",
                })
                continue

            # Check if this note matches standard instruction patterns
            if not is_standard_note(note):
                non_standard_indices.append(idx)

        # Now classify non-standard notes with context
        for idx in non_standard_indices:
            note = notes[idx]
            note_stripped = note.strip()
            category, message = classify_non_standard_note(note, notes, idx)

            issues.append({
                "category": category,
                "severity": "medium" if "leaked" in category else "low",
                "file": rel_path,
                "note_index": idx,
                "note_content": note_stripped[:200],
                "message": message,
            })

    # --------------------------------------------------------
    # Check 6: Empty stems or empty options
    # --------------------------------------------------------
    for q in questions:
        qnum = q.get("number", "?")
        qtype = q.get("type", "unknown")
        stem = q.get("stem", "")

        # Empty stem
        if stem is None or (isinstance(stem, str) and stem.strip() == ""):
            issues.append({
                "category": "empty_stem",
                "severity": "critical",
                "file": rel_path,
                "question_number": qnum,
                "question_type": qtype,
                "message": "Question has empty or missing stem",
            })

        # Empty options for choice questions
        if qtype == "choice":
            options = q.get("options", {})
            if not options:
                issues.append({
                    "category": "empty_options",
                    "severity": "critical",
                    "file": rel_path,
                    "question_number": qnum,
                    "question_type": qtype,
                    "message": "Choice question has no options",
                })
            else:
                for opt_key, opt_val in options.items():
                    if opt_val is None or (isinstance(opt_val, str) and opt_val.strip() == ""):
                        issues.append({
                            "category": "empty_option_value",
                            "severity": "high",
                            "file": rel_path,
                            "question_number": qnum,
                            "question_type": qtype,
                            "option_key": opt_key,
                            "message": f"Option {opt_key} is empty",
                        })

                # Check for incomplete option sets
                actual_keys = set(options.keys())
                if len(actual_keys) < 2:
                    issues.append({
                        "category": "insufficient_options",
                        "severity": "high",
                        "file": rel_path,
                        "question_number": qnum,
                        "question_type": qtype,
                        "options_found": sorted(list(actual_keys)),
                        "message": f"Choice question has fewer than 2 options: {sorted(list(actual_keys))}",
                    })

    # --------------------------------------------------------
    # Check 7: Answer value validity for choice questions
    # --------------------------------------------------------
    for q in questions:
        qnum = q.get("number", "?")
        qtype = q.get("type", "")

        if qtype == "choice":
            answer = q.get("answer")
            options = q.get("options", {})

            if answer and options:
                answer_str = str(answer).strip()
                answer_letters = set(re.findall(r"[A-Z]", answer_str.upper()))
                option_keys = set(options.keys())

                for letter in answer_letters:
                    if letter not in option_keys:
                        issues.append({
                            "category": "answer_not_in_options",
                            "severity": "high",
                            "file": rel_path,
                            "question_number": qnum,
                            "question_type": qtype,
                            "answer": answer_str,
                            "available_options": sorted(list(option_keys)),
                            "message": f"Answer '{letter}' not found in options {sorted(list(option_keys))}",
                        })

    # --------------------------------------------------------
    # Check 8: Page break artifacts in stem
    # --------------------------------------------------------
    for q in questions:
        stem = q.get("stem", "")
        qnum = q.get("number", "?")
        qtype = q.get("type", "unknown")

        if not stem:
            continue

        page_break_patterns = [
            (r"代號[：:]\s*\d{3,}", "代號:XXXXX (exam code number embedded)"),
            (r"\d+-\d+\s*頁", "X-X頁 (page range embedded)"),
            (r"頁次[：:]\s*\d", "頁次:X (page number embedded)"),
        ]
        for pattern, desc in page_break_patterns:
            if re.search(pattern, stem):
                issues.append({
                    "category": "page_break_artifact_in_stem",
                    "severity": "high",
                    "file": rel_path,
                    "question_number": qnum,
                    "question_type": qtype,
                    "pattern_matched": desc,
                    "stem_excerpt": stem[:200],
                })

    return issues


def main():
    print("=" * 70)
    print("Agent 2: Structural & Content Quality Scanner")
    print("=" * 70)
    print(f"Scanning directory: {BASE_DIR}")
    print()

    # Collect all exam JSON files (exclude top-level metadata files)
    all_files = sorted(BASE_DIR.rglob("*.json"))
    exam_files = [f for f in all_files if f.parent != BASE_DIR]

    print(f"Total JSON files found: {len(all_files)}")
    print(f"Exam JSON files to scan: {len(exam_files)}")
    print()

    all_issues = []
    files_with_issues = set()
    files_scanned = 0
    total_questions = 0
    total_choice_questions = 0
    total_essay_questions = 0

    for filepath in exam_files:
        files_scanned += 1
        if files_scanned % 100 == 0:
            print(f"  Scanned {files_scanned}/{len(exam_files)} files...")

        # Count questions
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            questions = data.get("questions", [])
            total_questions += len(questions)
            for q in questions:
                if q.get("type") == "choice":
                    total_choice_questions += 1
                elif q.get("type") == "essay":
                    total_essay_questions += 1
        except:
            pass

        issues = scan_file(filepath)
        if issues:
            files_with_issues.add(str(filepath.relative_to(BASE_DIR)))
            all_issues.extend(issues)

    print(f"\nScan complete. Scanned {files_scanned} files.")
    print(f"Total questions: {total_questions}")
    print(f"  Choice questions: {total_choice_questions}")
    print(f"  Essay questions: {total_essay_questions}")
    print(f"Total issues found: {len(all_issues)}")
    print(f"Files with issues: {len(files_with_issues)}")

    # Categorize issues
    category_counts = defaultdict(int)
    severity_counts = defaultdict(int)
    for issue in all_issues:
        category_counts[issue["category"]] += 1
        severity_counts[issue["severity"]] += 1

    print("\n--- Issues by Category ---")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    print("\n--- Issues by Severity ---")
    for sev, count in sorted(severity_counts.items(), key=lambda x: -x[1]):
        print(f"  {sev}: {count}")

    # Build the report
    report = {
        "scan_metadata": {
            "scanner": "Agent 2 - Structural & Content Quality Scanner",
            "base_directory": str(BASE_DIR),
            "total_files_scanned": files_scanned,
            "total_questions_scanned": total_questions,
            "total_choice_questions": total_choice_questions,
            "total_essay_questions": total_essay_questions,
            "files_with_issues": len(files_with_issues),
            "total_issues_found": len(all_issues),
        },
        "summary": {
            "by_category": dict(sorted(category_counts.items(), key=lambda x: -x[1])),
            "by_severity": dict(sorted(severity_counts.items(), key=lambda x: -x[1])),
        },
        "category_descriptions": {
            "header_footer_leak_in_stem": "Exam header/footer content (代號, 頁次, 座號, 等別, 類科, 科目, etc.) leaked into question stem text",
            "instruction_text_in_stem": "Exam instruction text (不必抄題, 申論試卷, 禁止使用電子計算器, 2B鉛筆, etc.) found in question stem",
            "missing_answer_for_choice": "Choice-type question is missing the answer field",
            "metadata_in_options": "Answer options contain exam metadata or header/footer content",
            "reading_passage_leaked_into_option": "Reading passage for subsequent questions leaked into an option value (content concatenation error during extraction)",
            "abnormally_long_option": "Option value is unusually long (>200 chars), suggesting possible content concatenation or extraction error",
            "notes_leaked_question_content": "Question/essay prompt content leaked into the notes array, split across multiple note entries (should be in a question stem instead)",
            "notes_leaked_formula_or_table": "Mathematical formula, statistical table, or technical reference data leaked into the notes array (should be in question content or a separate reference field)",
            "notes_leaked_formula_fragment": "Isolated formula fragment or symbol leaked into notes",
            "notes_leaked_score_marker": "Score/point marker (e.g. '(25分)') leaked into notes",
            "notes_leaked_section_header": "Section header or label leaked into notes",
            "notes_non_standard_content": "Non-standard content in notes that doesn't match expected instruction patterns",
            "notes_empty_entry": "Notes array contains empty string entry",
            "notes_invalid_type": "Notes array entry is not a string",
            "empty_stem": "Question has an empty or missing stem",
            "empty_options": "Choice question has no options at all",
            "empty_option_value": "One or more option values are empty strings",
            "insufficient_options": "Choice question has fewer than 2 options",
            "answer_not_in_options": "Answer references an option key that doesn't exist in the options object",
            "page_break_artifact_in_stem": "Page break artifacts (代號:XXXXX, page ranges) embedded in stem text",
            "json_parse_error": "JSON file could not be parsed",
            "file_read_error": "File could not be read",
        },
        "issues": all_issues,
        "affected_files_list": sorted(list(files_with_issues)),
    }

    # Write report
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\nReport saved to: {OUTPUT_FILE}")
    print(f"Report file size: {os.path.getsize(OUTPUT_FILE)} bytes")


if __name__ == "__main__":
    main()
