#!/usr/bin/env python3
"""
Ralph-Loop Round 2: Deep error scanner.
Finds remaining text quality issues after Round 1 fixes.
"""
import json
import os
import re
import sys

BASE_DIR = "/home/user/police-exam-archive/考古題庫"

def deep_scan_file(filepath, rel_path):
    """Deep scan a file for remaining text quality issues."""
    issues = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return [{"type": "parse_error", "detail": str(e)}]

    metadata = data.get('metadata', {})
    questions = data.get('questions', [])

    # 1. Check metadata fields for garbage
    exam_time = metadata.get('exam_time', '')
    if '座號' in exam_time or '代號' in exam_time:
        issues.append({"type": "metadata_still_dirty", "detail": f"exam_time: {exam_time}"})

    # 2. Check for remaining empty stems
    for q in questions:
        qnum = q.get('number', '?')
        stem = q.get('stem', '').strip()
        qtype = q.get('type', '')
        options = q.get('options', {})

        if not stem and qtype == 'choice':
            issues.append({"type": "empty_stem", "question": qnum, "detail": f"Empty stem with options: {list(options.keys())}"})

        if not stem and qtype == 'essay':
            issues.append({"type": "empty_essay_stem", "question": qnum, "detail": "Empty essay stem"})

        # 3. Check for remaining empty options
        for k, v in options.items():
            if not str(v).strip():
                issues.append({"type": "empty_option", "question": qnum, "detail": f"Option {k} is empty"})

        # 4. Check for OCR artifacts in English text
        # Pattern: word broken by spaces (e.g., "off icer", "re search")
        all_text = stem + ' '.join(str(v) for v in options.values())
        ocr_breaks = re.findall(r'\b([a-z]{1,3})\s([a-z]{2,})\b', all_text)
        for prefix, suffix in ocr_breaks:
            combined = prefix + suffix
            # Only flag if the combined word looks like a real word (> 5 chars)
            if len(combined) > 5 and not re.match(r'^(the|and|for|are|but|not|you|all|can|her|was|one|our|out|are|his|has|had|how|its|may|new|now|old|see|two|way|who|did|get|let|say|she|too|use)$', prefix):
                # Check if this might be a real OCR break
                if prefix in ['re', 'un', 'in', 'de', 'ex', 'co', 'en', 'im', 'pre', 'dis', 'mis', 'non', 'sub', 'out', 'over']:
                    # These are common prefixes that might be OCR breaks
                    pass  # Too many false positives

        # 5. Check for exam page header content in stems
        header_patterns = [
            r'代號[：:]\s*\d+',
            r'頁次[：:]',
            r'全[一二三四五六七八九十]+頁',
            r'等\s*別[：:]',
            r'類\s*科[：:]',
            r'科\s*目[：:]',
        ]
        for pat in header_patterns:
            if re.search(pat, stem):
                issues.append({"type": "header_in_stem", "question": qnum, "detail": f"Pattern '{pat}' found in stem"})

        # 6. Check for mismatched question types
        if qtype == 'choice' and not options:
            issues.append({"type": "choice_no_options", "question": qnum, "detail": "Choice question with no options"})

        if qtype == 'choice' and len(options) < 2:
            issues.append({"type": "too_few_options", "question": qnum, "detail": f"Only {len(options)} options"})

        # 7. Check for duplicate question numbers
        seen_numbers = set()
        for q2 in questions:
            n = q2.get('number')
            if n in seen_numbers:
                issues.append({"type": "duplicate_number", "question": n, "detail": "Duplicate question number"})
                break
            seen_numbers.add(n)

        # 8. Check for answer not in options (skip '送分' which is valid)
        if qtype == 'choice' and options:
            answer = q.get('answer', '')
            if answer and answer not in options and answer != '送分':
                issues.append({"type": "answer_not_in_options", "question": qnum, "detail": f"Answer '{answer}' not in options {list(options.keys())}"})

    # 9. Check if file has zero questions
    if not questions:
        issues.append({"type": "no_questions", "detail": "File has no questions"})

    return issues


def main():
    print("=" * 60)
    print("Ralph-Loop Round 2: Deep Error Scanner")
    print("=" * 60)

    total_files = 0
    files_with_issues = 0
    total_issues = 0
    issue_type_count = {}
    all_issues = {}

    for root, dirs, fnames in os.walk(BASE_DIR):
        for fname in fnames:
            if fname != '試題.json':
                continue
            filepath = os.path.join(root, fname)
            rel_path = os.path.relpath(filepath, BASE_DIR)
            total_files += 1

            issues = deep_scan_file(filepath, rel_path)
            if issues:
                files_with_issues += 1
                total_issues += len(issues)
                all_issues[rel_path] = issues

                for issue in issues:
                    itype = issue['type']
                    issue_type_count[itype] = issue_type_count.get(itype, 0) + 1

    print(f"\nTotal files scanned: {total_files}")
    print(f"Files with issues: {files_with_issues}")
    print(f"Total issues found: {total_issues}")
    print(f"\nIssue breakdown:")
    for itype, count in sorted(issue_type_count.items(), key=lambda x: -x[1]):
        print(f"  {itype}: {count}")

    if all_issues:
        print(f"\n=== Detailed Issues ===")
        for rel_path, issues in sorted(all_issues.items()):
            print(f"\n--- {rel_path} ---")
            for issue in issues:
                print(f"  [{issue['type']}] Q{issue.get('question', '?')}: {issue.get('detail', '')}")

    # Save report
    report = {
        "summary": {
            "total_files": total_files,
            "files_with_issues": files_with_issues,
            "total_issues": total_issues,
            "issue_type_count": issue_type_count
        },
        "issues": all_issues
    }

    report_path = "/home/user/police-exam-archive/deep_scan_report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nReport saved to: {report_path}")

    return total_issues


if __name__ == '__main__':
    issues = main()
    sys.exit(0 if issues == 0 else 1)
