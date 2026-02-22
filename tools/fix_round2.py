#!/usr/bin/env python3
"""
Ralph-Loop Round 2: Fix remaining issues found by deep scan.

Fixes:
1. Remaining empty stem cloze questions (remove broken questions)
2. Remaining empty options (remove or fix)
3. More OCR space artifacts (expanded pattern list)
4. Duplicate question numbers in 國文 files (renumber sub-items)
5. Clean answer '*' format -> mark as '送分'
"""
import json
import os
import re
import sys

BASE_DIR = "/home/user/police-exam-archive/考古題庫"

stats = {
    "files_processed": 0,
    "files_modified": 0,
    "fixes": {}
}

def inc_fix(fix_type, count=1):
    stats["fixes"][fix_type] = stats["fixes"].get(fix_type, 0) + count


# Expanded OCR space artifact fixes
# These patterns are found by analyzing the actual data
OCR_SPACE_FIXES = [
    # Common word breaks from 114年 and other years
    (r'threat\s+ened', 'threatened'),
    (r'associate\s*dwith', 'associated with'),
    (r'over\s*lyreliant', 'overly reliant'),
    (r'AIc\s*hat\s*apps?', 'AI chat apps'),
    (r'AIc\s*hat\s*bots?', 'AI chat bots'),
    (r'ina\s*ccu\s*rate', 'inaccurate'),
    (r'reported\s*lyex\s*posed', 'reportedly exposed'),
    (r'inter\s*actions', 'interactions'),
    (r'current\s*lybanned', 'currently banned'),
    (r'sur\s*pass', 'surpass'),
    (r'relation\s*ships\s*withAI', 'relationships with AI'),
    (r'develop\s*ing', 'developing'),
    (r'Com\s*plain\s*ing', 'Complaining'),
    (r'state\s*ments', 'statements'),
    (r'ofthe\s', 'of the '),
    (r'thebest', 'the best'),
    (r'Fondof', 'Fond of'),
    (r'historyofAI', 'history of AI'),
    (r'Teach\s*ers', 'Teachers'),
    (r'WhydidU\.S\.', 'Why did U.S.'),
    (r'AIuseto', 'AI use to'),
    (r'onAI', 'on AI'),
    (r'theU\.S\.', 'the U.S.'),
    (r'inAI', 'in AI'),
    (r'withAI', 'with AI'),
    (r'forAI', 'for AI'),
    # General OCR breaks
    (r'off\s+icers?', lambda m: 'officers' if m.group().endswith('s') else 'officer'),
    (r'de\s*part\s*ment', 'department'),
    (r'en\s*force\s*ment', 'enforcement'),
    (r'in\s*vesti\s*gat', 'investigat'),
    (r'gov\s*ern\s*ment', 'government'),
    (r'com\s*mun\s*ity', 'community'),
    (r'evi\s*dence', 'evidence'),
    (r'sus\s*pect', 'suspect'),
    (r'pro\s*tect', 'protect'),
    (r'de\s*tect', 'detect'),
]


def fix_ocr_advanced(text):
    """Fix advanced OCR space artifacts using regex patterns."""
    if not text:
        return text, False

    original = text
    for pattern, replacement in OCR_SPACE_FIXES:
        if callable(replacement):
            text = re.sub(pattern, replacement, text)
        else:
            text = re.sub(pattern, replacement, text)

    return text, text != original


def fix_remaining_empty_stems(questions):
    """Remove remaining questions with empty stems."""
    to_remove = []
    for i, q in enumerate(questions):
        stem = q.get('stem', '').strip()
        if not stem and q.get('type') == 'choice':
            to_remove.append(i)
            inc_fix('remaining_empty_stem_removed')

    for idx in sorted(to_remove, reverse=True):
        questions.pop(idx)

    return len(to_remove) > 0


def fix_empty_options(questions):
    """Handle remaining empty options."""
    modified = False
    to_remove = []

    for i, q in enumerate(questions):
        if q.get('type') != 'choice':
            continue
        options = q.get('options', {})
        empty_keys = [k for k, v in options.items() if not str(v).strip()]

        if empty_keys:
            # If only 1 option is empty and 3+ are valid, just remove the empty one
            non_empty = {k: v for k, v in options.items() if str(v).strip()}
            if len(non_empty) >= 3:
                q['options'] = non_empty
                modified = True
                inc_fix('single_empty_option_removed')
            elif len(non_empty) < 2:
                # Too many empty options - remove the question
                to_remove.append(i)
                inc_fix('too_many_empty_options_removed')

    for idx in sorted(to_remove, reverse=True):
        questions.pop(idx)

    return modified or len(to_remove) > 0


def fix_duplicate_numbers(questions):
    """Fix duplicate question numbers by adding sub-numbering."""
    modified = False
    seen = {}

    for q in questions:
        num = q.get('number')
        if num in seen:
            seen[num] += 1
        else:
            seen[num] = 1

    # Only fix if there are actual duplicates
    duplicates = {k: v for k, v in seen.items() if v > 1}
    if not duplicates:
        return False

    # For 國文 files: the pattern is essay sub-items after the main essay question
    # Renumber them as 一-1, 一-2, etc. (but actually these are content items)
    # Better approach: assign unique numbers
    counters = {}
    for q in questions:
        num = q.get('number')
        if num in duplicates:
            if num not in counters:
                counters[num] = 0
            counters[num] += 1
            if counters[num] > 1:
                # This is a duplicate - give it a unique sub-number
                q['number'] = f"{num}-{counters[num]}"
                modified = True
                inc_fix('duplicate_number_fixed')

    return modified


def fix_answer_star(questions):
    """Mark answer '*' as '送分' for clarity."""
    modified = False
    for q in questions:
        if q.get('answer') == '*':
            q['answer'] = '送分'
            modified = True
            inc_fix('answer_star_to_songfen')
    return modified


def fix_option_trailing_garbage(questions):
    """Clean trailing garbage from option values like ' - -' or ' - 、'."""
    modified = False
    for q in questions:
        options = q.get('options', {})
        for key, val in options.items():
            val_str = str(val)
            # Remove trailing " - -", " - 、", etc.
            cleaned = re.sub(r'\s*[-–—]\s*[-–—、]\s*$', '', val_str).strip()
            # Remove trailing isolated punctuation
            cleaned = re.sub(r'\s*[、，。；]\s*$', '', cleaned).strip()
            if cleaned != val_str:
                options[key] = cleaned
                modified = True
                inc_fix('option_trailing_garbage_removed')
    return modified


def process_file(filepath):
    """Process a single file for Round 2 fixes."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return False

    original_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
    modified = False

    questions = data.get('questions', [])

    # Fix 1: Remove remaining empty stem questions
    if fix_remaining_empty_stems(questions):
        modified = True

    # Fix 2: Handle empty options
    if fix_empty_options(questions):
        modified = True

    # Fix 3: OCR space artifacts (advanced)
    for q in questions:
        stem = q.get('stem', '')
        new_stem, changed = fix_ocr_advanced(stem)
        if changed:
            q['stem'] = new_stem
            modified = True
            inc_fix('ocr_advanced_stem')

        for key, val in q.get('options', {}).items():
            new_val, changed = fix_ocr_advanced(str(val))
            if changed:
                q['options'][key] = new_val
                modified = True
                inc_fix('ocr_advanced_option')

    # Fix 4: Duplicate numbers
    if fix_duplicate_numbers(questions):
        modified = True

    # Fix 5: Answer '*' -> '送分'
    if fix_answer_star(questions):
        modified = True

    # Fix 6: Option trailing garbage
    if fix_option_trailing_garbage(questions):
        modified = True

    # Write back if modified
    if modified:
        new_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
        if new_json != original_json:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True

    return False


def main():
    print("=" * 60)
    print("Ralph-Loop Round 2: Fix Remaining Issues")
    print("=" * 60)

    for root, dirs, fnames in os.walk(BASE_DIR):
        for fname in fnames:
            if fname != '試題.json':
                continue
            filepath = os.path.join(root, fname)
            stats["files_processed"] += 1

            if process_file(filepath):
                stats["files_modified"] += 1

            if stats["files_processed"] % 100 == 0:
                print(f"  Processed {stats['files_processed']} files...")

    print(f"\n{'=' * 60}")
    print(f"Results:")
    print(f"  Files processed: {stats['files_processed']}")
    print(f"  Files modified: {stats['files_modified']}")
    print(f"\nFixes applied:")
    for fix_type, count in sorted(stats["fixes"].items(), key=lambda x: -x[1]):
        print(f"  {fix_type}: {count}")

    stats_path = "/home/user/police-exam-archive/fix_round2_stats.json"
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"\nStats saved to: {stats_path}")


if __name__ == '__main__':
    main()
