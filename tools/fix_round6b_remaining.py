#!/usr/bin/env python3
"""
Ralph-Loop Round 6b: Fix remaining OCR artifacts missed by Round 6.
"""
import json
import os
import re

BASE_DIR = "/home/user/police-exam-archive/考古題庫"

# Simple string replacements
STRING_FIXES = {
    'ArtificialIntelligence': 'Artificial Intelligence',
    'AssociationTheory': 'Association Theory',
    'BehaviorSyndrome': 'Behavior Syndrome',
    'MobileForensics': 'Mobile Forensics',
    'OpportunityTheories': 'Opportunity Theories',
    'PatrolExperiment': 'Patrol Experiment',
    'andProcesses': 'and Processes',
    'ofcyberbullying': 'of cyberbullying',
}

# Regex replacements
REGEX_FIXES = [
    (r'entit\s+led', 'entitled'),
    (r'\bfai\s+led\b', 'failed'),
    # "request ingimmediate" -> "requesting immediate"
    (r'request\s+ingimmediate', 'requesting immediate'),
    (r'([a-z])ingimmediate', r'\1ing immediate'),
    # "officer sare" -> "officers are", "chapter sare" -> "chapters are"
    (r'(\w+)\s+sare\b', lambda m: m.group(1) + 's are'),
    (r'([a-z])sare\b', r'\1s are'),
    # "suspect'sre side nce" -> "suspect's residence" (handles both ' and ')
    (r"suspect['\u2019]sre\s*side\s*nce", "suspect\u2019s residence"),
    (r"suspect['\u2019]sre", "suspect\u2019s re"),
]


def fix_text(text):
    if not text:
        return text, False
    original = text
    for wrong, right in STRING_FIXES.items():
        text = text.replace(wrong, right)
    for pattern, replacement in REGEX_FIXES:
        text = re.sub(pattern, replacement, text)
    return text, text != original


def main():
    files_modified = 0
    total_fixes = 0

    for root, dirs, fnames in os.walk(BASE_DIR):
        for fname in fnames:
            if fname != '試題.json':
                continue
            filepath = os.path.join(root, fname)
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            original = json.dumps(data, ensure_ascii=False, sort_keys=True)
            modified = False

            for q in data.get('questions', []):
                stem = q.get('stem', '')
                new_stem, changed = fix_text(stem)
                if changed:
                    q['stem'] = new_stem
                    modified = True
                    total_fixes += 1

                for key, val in q.get('options', {}).items():
                    new_val, changed = fix_text(str(val))
                    if changed:
                        q['options'][key] = new_val
                        modified = True
                        total_fixes += 1

            if modified:
                new_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
                if new_json != original:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    files_modified += 1

    print(f"Files modified: {files_modified}")
    print(f"Total fixes: {total_fixes}")


if __name__ == '__main__':
    main()
