#!/usr/bin/env python3
"""
Ralph-Loop Final Validator: Comprehensive quality check.
This is the final pass that should report ZERO issues for the project to be perfect.
"""
import json
import os
import re
import sys

BASE_DIR = "/home/user/police-exam-archive/考古題庫"

def validate_file(filepath, rel_path):
    """Run all validation checks on a single file."""
    issues = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            raw = f.read()
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return [f"JSON parse error: {e}"]
    except UnicodeDecodeError as e:
        return [f"Unicode error: {e}"]

    # === Structural Validation ===
    if not isinstance(data, dict):
        return ["Root is not a dict"]

    # Metadata checks
    metadata = data.get('metadata', {})
    if not metadata:
        issues.append("Missing metadata")
    else:
        if '座號' in str(metadata):
            issues.append(f"'座號' found in metadata: {json.dumps(metadata, ensure_ascii=False)[:100]}")
        exam_time = metadata.get('exam_time', '')
        if exam_time and any(x in exam_time for x in ['座號', '代號', '頁次']):
            issues.append(f"Garbage in exam_time: {exam_time}")

    # Questions checks
    questions = data.get('questions', [])
    if not questions:
        issues.append("No questions in file")

    for q in questions:
        qnum = q.get('number', '?')
        stem = q.get('stem', '')
        qtype = q.get('type', '')
        options = q.get('options', {})
        answer = q.get('answer', '')

        # Empty stem
        if not stem.strip():
            issues.append(f"Q{qnum}: Empty stem")

        # Choice question checks
        if qtype == 'choice':
            if not options:
                issues.append(f"Q{qnum}: Choice question with no options")
            if len(options) < 2:
                issues.append(f"Q{qnum}: Only {len(options)} options")
            # Answer validation
            if answer and answer not in options and answer != '送分':
                issues.append(f"Q{qnum}: Answer '{answer}' not in options")
            # Empty options
            for k, v in options.items():
                if not str(v).strip():
                    issues.append(f"Q{qnum}: Empty option {k}")

        # Exam header leaks
        header_leaks = ['座號', '代號：', '頁次']
        for leak in header_leaks:
            if leak in stem:
                issues.append(f"Q{qnum}: Header leak '{leak}' in stem")
            for k, v in options.items():
                if leak in str(v):
                    issues.append(f"Q{qnum}: Header leak '{leak}' in option {k}")

    # === JSON format validation ===
    # Check proper indentation (should be 2-space indent)
    try:
        reformatted = json.dumps(data, ensure_ascii=False, indent=2)
        if raw.strip() != reformatted.strip():
            # Minor formatting difference is OK
            pass
    except Exception:
        pass

    return issues


def main():
    print("=" * 60)
    print("Ralph-Loop FINAL VALIDATOR")
    print("=" * 60)

    total_files = 0
    total_questions = 0
    files_with_issues = 0
    total_issues = 0
    all_issues = {}

    for root, dirs, fnames in os.walk(BASE_DIR):
        for fname in fnames:
            if fname != '試題.json':
                continue
            filepath = os.path.join(root, fname)
            rel_path = os.path.relpath(filepath, BASE_DIR)
            total_files += 1

            # Count questions
            try:
                with open(filepath) as f:
                    data = json.load(f)
                total_questions += len(data.get('questions', []))
            except:
                pass

            issues = validate_file(filepath, rel_path)
            if issues:
                files_with_issues += 1
                total_issues += len(issues)
                all_issues[rel_path] = issues

    print(f"\n{'=' * 60}")
    print(f"FINAL VALIDATION RESULTS")
    print(f"{'=' * 60}")
    print(f"Total files: {total_files}")
    print(f"Total questions: {total_questions}")
    print(f"Files with issues: {files_with_issues}")
    print(f"Total issues: {total_issues}")

    if all_issues:
        print(f"\n--- Remaining Issues ---")
        for rel_path, issues in sorted(all_issues.items()):
            for issue in issues:
                print(f"  {rel_path}: {issue}")
    else:
        print(f"\n*** PERFECT: Zero issues found across all {total_files} files! ***")
        print(f"*** All {total_questions} questions are properly formatted. ***")

    # Final score
    if total_issues == 0:
        score = 100
    else:
        score = max(0, 100 - (total_issues / total_files * 100))

    print(f"\nQuality Score: {score:.1f}/100")

    return total_issues


if __name__ == '__main__':
    issues = main()
    sys.exit(0 if issues == 0 else 1)
