#!/usr/bin/env python3
"""Fix 108年 外國文 exam files where Q1-Q20 choice questions were mislabeled as essay.

Problem: In 108年, 9 out of 11 language groups had the English professional test
section (乙、測驗題 Q1-Q20) incorrectly parsed as essay questions instead of
choice questions. The stems contain embedded option text, and answers/options
were not extracted.

Solution: Use the correctly-parsed 泰文 file as reference to restore proper
type, options, answer, passage, and section fields for Q1-Q20.

Affected language groups (9):
  俄文, 德文, 日文, 法文, 英文, 葡萄牙文, 西班牙文, 越南文, 韓文

Not affected (already correct):
  印尼文, 泰文
"""
import json
import os
import sys

BASE_DIR = "/home/user/police-exam-archive/考古題庫/國境警察學系移民組/108年"
REFERENCE_FILE = os.path.join(BASE_DIR, "外國文(泰文兼試移民專業英文)", "試題.json")

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')

def main():
    # Load reference data
    ref_data = load_json(REFERENCE_FILE)
    ref_choices = {}
    for q in ref_data['questions']:
        if q.get('type') == 'choice' and str(q.get('number', '')).isdigit():
            ref_choices[int(q['number'])] = q

    print(f"Reference (泰文) loaded: {len(ref_choices)} choice questions")

    # Find affected files
    fixed_count = 0
    affected_files = []

    for subject in sorted(os.listdir(BASE_DIR)):
        if '外國文' not in subject:
            continue
        filepath = os.path.join(BASE_DIR, subject, '試題.json')
        if not os.path.exists(filepath):
            continue

        data = load_json(filepath)
        questions = data.get('questions', [])

        # Check if this file has mislabeled questions
        mislabeled = [q for q in questions
                      if q.get('type') == 'essay'
                      and str(q.get('number', '')).isdigit()]

        if not mislabeled:
            continue

        lang = subject.split('(')[1].split('兼')[0] if '(' in subject else subject
        print(f"\nFixing {lang} ({len(mislabeled)} mislabeled questions)...")

        # Fix each mislabeled question
        questions_fixed = 0
        for i, q in enumerate(questions):
            if q.get('type') != 'essay' or not str(q.get('number', '')).isdigit():
                continue

            qnum = int(q['number'])
            if qnum not in ref_choices:
                print(f"  WARNING: Q{qnum} not found in reference, skipping")
                continue

            ref_q = ref_choices[qnum]

            # Update to choice type with reference data
            q['type'] = 'choice'
            q['options'] = ref_q['options'].copy()
            q['answer'] = ref_q['answer']
            q['section'] = ref_q.get('section', '乙、測驗題')

            # Copy passage if reference has it
            if 'passage' in ref_q:
                q['passage'] = ref_q['passage']

            # Clean up stem: use reference stem (which is clean)
            q['stem'] = ref_q['stem']

            # Update notes
            if 'notes' in ref_q:
                q['notes'] = ref_q['notes']
            elif 'notes' in q:
                del q['notes']

            questions_fixed += 1

        # Save
        save_json(filepath, data)
        fixed_count += questions_fixed
        affected_files.append(f"{lang}: {questions_fixed} questions fixed")
        print(f"  Fixed {questions_fixed} questions")

    print(f"\n=== Summary ===")
    print(f"Total questions fixed: {fixed_count}")
    for af in affected_files:
        print(f"  {af}")

    return fixed_count

if __name__ == '__main__':
    count = main()
    print(f"\nDone. {count} questions converted from essay to choice.")
