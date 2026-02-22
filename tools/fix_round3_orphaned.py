#!/usr/bin/env python3
"""
Ralph-Loop Round 3: Fix orphaned answers.
Restore missing option keys that are referenced by the answer field.
"""
import json
import os

BASE_DIR = "/home/user/police-exam-archive/考古題庫"

PLACEHOLDER = "(原始資料缺失)"

stats = {"restored": 0, "files_modified": 0}

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    modified = False
    for q in data.get('questions', []):
        if q.get('type') != 'choice':
            continue
        answer = q.get('answer', '')
        options = q.get('options', {})
        if answer and answer not in options and answer != '送分':
            # Restore the missing option
            options[answer] = PLACEHOLDER
            # Sort options by key
            q['options'] = dict(sorted(options.items()))
            modified = True
            stats["restored"] += 1
            rel = os.path.relpath(filepath, BASE_DIR)
            print(f"  Restored {rel} Q{q.get('number')} option {answer}")

    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        stats["files_modified"] += 1

    return modified


def main():
    print("=" * 60)
    print("Ralph-Loop Round 3: Fix Orphaned Answers")
    print("=" * 60)

    for root, dirs, fnames in os.walk(BASE_DIR):
        for fname in fnames:
            if fname != '試題.json':
                continue
            process_file(os.path.join(root, fname))

    print(f"\nResults:")
    print(f"  Options restored: {stats['restored']}")
    print(f"  Files modified: {stats['files_modified']}")


if __name__ == '__main__':
    main()
