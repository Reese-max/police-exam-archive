#!/usr/bin/env python3
"""Comprehensive error scanner for police exam JSON files."""
import json
import os
import re
import sys

BASE_DIR = "/home/user/police-exam-archive/考古題庫"

# Error patterns to detect
EXAM_HEADER_PATTERN = re.compile(r'(座號|代號：|頁次|類科|全[一二三四五六七八九十]+頁|考試時間：?\s*\d)')
PAGE_MARKER_PATTERN = re.compile(r'(第\s*\d+\s*頁|共\s*\d+\s*頁)')
GARBLED_PATTERN = re.compile(r'[□■●○◎]{3,}')
BROKEN_UNICODE_PATTERN = re.compile(r'[\ufffd\ufffe\uffff]')
WATERMARK_PATTERN = re.compile(r'(高點|志光|保成|學儒|超級函授)')
# Trailing/leading irrelevant content - exam metadata that leaked in
METADATA_LEAK_PATTERN = re.compile(r'(等\s*別|類\s*科|科\s*目|考試時間|座\s*號)')
# Question number prefix repeated
DOUBLE_NUMBER_PATTERN = re.compile(r'^\d+\s*\.\s*\d+\s*\.')
# Irrelevant text patterns - text from adjacent questions or headers
ADJACENT_LEAK_PATTERN = re.compile(r'(申論題部分|測驗題部分|禁止使用電子計算器|不必抄題|藍、黑色鋼筆|2B鉛筆|申論試卷)')

def scan_file(filepath):
    """Scan a single JSON file for text errors."""
    errors = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return [{"type": "json_parse_error", "detail": str(e)}]

    # Check metadata
    metadata = data.get('metadata', {})
    exam_time = metadata.get('exam_time', '')
    if '座號' in exam_time:
        errors.append({"type": "metadata_leak_in_exam_time", "detail": f"exam_time contains '座號': {exam_time}"})

    # Check notes for issues
    notes = data.get('notes', [])

    # Check questions
    questions = data.get('questions', [])
    for q in questions:
        qnum = q.get('number', '?')
        stem = q.get('stem', '')
        qtype = q.get('type', '')

        # 1. Exam header leaked into stem
        if EXAM_HEADER_PATTERN.search(stem):
            match = EXAM_HEADER_PATTERN.search(stem)
            errors.append({
                "type": "exam_header_in_stem",
                "question": qnum,
                "detail": f"Found '{match.group()}' in stem: {stem[:100]}"
            })

        # 2. Page markers in stem
        if PAGE_MARKER_PATTERN.search(stem):
            errors.append({
                "type": "page_marker_in_stem",
                "question": qnum,
                "detail": f"Page marker in stem: {stem[:100]}"
            })

        # 3. Adjacent question/instruction leak
        if ADJACENT_LEAK_PATTERN.search(stem):
            match = ADJACENT_LEAK_PATTERN.search(stem)
            errors.append({
                "type": "instruction_leak_in_stem",
                "question": qnum,
                "detail": f"Found '{match.group()}' in stem: {stem[:100]}"
            })

        # 4. Garbled characters
        if GARBLED_PATTERN.search(stem):
            errors.append({
                "type": "garbled_text_in_stem",
                "question": qnum,
                "detail": f"Garbled chars in stem: {stem[:100]}"
            })

        # 5. Very short stem for choice questions
        if qtype == 'choice' and len(stem.strip()) < 5:
            errors.append({
                "type": "too_short_stem",
                "question": qnum,
                "detail": f"Stem too short ({len(stem.strip())} chars): '{stem}'"
            })

        # 6. Empty stem
        if not stem.strip():
            errors.append({
                "type": "empty_stem",
                "question": qnum,
                "detail": "Empty stem"
            })

        # Check options
        options = q.get('options', {})
        for key, val in options.items():
            val_str = str(val)

            if EXAM_HEADER_PATTERN.search(val_str):
                errors.append({
                    "type": "exam_header_in_option",
                    "question": qnum,
                    "option": key,
                    "detail": f"Header leak in option {key}: {val_str[:80]}"
                })

            if PAGE_MARKER_PATTERN.search(val_str):
                errors.append({
                    "type": "page_marker_in_option",
                    "question": qnum,
                    "option": key,
                    "detail": f"Page marker in option {key}: {val_str[:80]}"
                })

            if ADJACENT_LEAK_PATTERN.search(val_str):
                errors.append({
                    "type": "instruction_leak_in_option",
                    "question": qnum,
                    "option": key,
                    "detail": f"Instruction leak in option {key}: {val_str[:80]}"
                })

            if not val_str.strip():
                errors.append({
                    "type": "empty_option",
                    "question": qnum,
                    "option": key,
                    "detail": f"Empty option {key}"
                })

        # 7. Choice question missing answer
        if qtype == 'choice' and not q.get('answer'):
            errors.append({
                "type": "missing_answer",
                "question": qnum,
                "detail": "Choice question has no answer"
            })

        # 8. Choice question missing options
        if qtype == 'choice' and len(options) < 2:
            errors.append({
                "type": "missing_options",
                "question": qnum,
                "detail": f"Choice question only has {len(options)} options"
            })

    return errors


def main():
    total_files = 0
    files_with_errors = 0
    total_errors = 0
    error_type_count = {}
    all_errors = {}

    for root, dirs, fnames in os.walk(BASE_DIR):
        for fname in fnames:
            if fname != '試題.json':
                continue
            filepath = os.path.join(root, fname)
            rel_path = os.path.relpath(filepath, BASE_DIR)
            total_files += 1

            errors = scan_file(filepath)
            if errors:
                files_with_errors += 1
                total_errors += len(errors)
                all_errors[rel_path] = errors

                for err in errors:
                    etype = err['type']
                    error_type_count[etype] = error_type_count.get(etype, 0) + 1

    # Print summary
    print(f"=== Error Scan Summary ===")
    print(f"Total files scanned: {total_files}")
    print(f"Files with errors: {files_with_errors}")
    print(f"Total errors found: {total_errors}")
    print(f"\nError breakdown:")
    for etype, count in sorted(error_type_count.items(), key=lambda x: -x[1]):
        print(f"  {etype}: {count}")

    print(f"\n=== Detailed Errors by File ===")
    for rel_path, errors in sorted(all_errors.items()):
        print(f"\n--- {rel_path} ---")
        for err in errors:
            print(f"  [{err['type']}] Q{err.get('question', '?')}: {err.get('detail', '')}")

    # Save report
    report = {
        "summary": {
            "total_files": total_files,
            "files_with_errors": files_with_errors,
            "total_errors": total_errors,
            "error_type_count": error_type_count
        },
        "errors": all_errors
    }

    report_path = "/home/user/police-exam-archive/error_scan_report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nReport saved to: {report_path}")

    return total_errors


if __name__ == '__main__':
    errors = main()
    sys.exit(0 if errors == 0 else 1)
