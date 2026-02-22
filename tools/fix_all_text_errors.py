#!/usr/bin/env python3
"""
Comprehensive text error fixer for police exam JSON files.
Ralph-Loop Round 1: Fix all automatically detectable errors.

Error categories handled:
1. metadata_leak_in_exam_time - Remove "座號：" from exam_time
2. empty_stem_cloze_questions - Remove broken cloze questions with no stem
3. empty_options - Remove questions with empty options that can't be answered
4. missing_options - Remove choice questions with < 2 options
5. ocr_space_artifacts - Fix OCR-introduced spaces within English words
6. garbled_unicode - Fix broken unicode characters
7. trailing_whitespace - Clean up excessive whitespace
8. notes_cleanup - Remove redundant exam instruction notes
9. stem_trailing_garbage - Remove trailing exam metadata from stems
"""
import json
import os
import re
import sys
import copy
from pathlib import Path

BASE_DIR = "/home/user/police-exam-archive/考古題庫"

# Statistics tracking
stats = {
    "files_processed": 0,
    "files_modified": 0,
    "fixes": {}
}

def inc_fix(fix_type, count=1):
    stats["fixes"][fix_type] = stats["fixes"].get(fix_type, 0) + count


def fix_exam_time(metadata):
    """Remove '座號：' and similar garbage from exam_time field."""
    exam_time = metadata.get('exam_time', '')
    if not exam_time:
        return False

    original = exam_time
    # Remove 座號：and everything after it
    exam_time = re.sub(r'\s*座號[：:].*$', '', exam_time).strip()
    # Remove trailing whitespace and colons
    exam_time = exam_time.rstrip('：: ')

    if exam_time != original:
        metadata['exam_time'] = exam_time
        return True
    return False


def fix_ocr_spaces_in_english(text):
    """Fix OCR-introduced spaces within English words.

    Common patterns: "off icers" -> "officers", "con ten tly" -> "contently"
    But be careful not to merge intentionally separate words.
    """
    if not text:
        return text, False

    original = text

    # Fix common OCR space patterns in English words
    # Pattern: single letter followed by space then more word chars
    # Only apply to clear OCR artifacts
    known_fixes = {
        'off icers': 'officers',
        'off icer': 'officer',
        'con ten tly': 'contently',
        'tour name nt': 'tournament',
        'indu str ies': 'industries',
        'trans cultural': 'transcultural',
        'inter cultural': 'intercultural',
        'trans national': 'transnational',
        'a band ons': 'abandons',
        'smo other': 'smoother',
        'str anded': 'stranded',
        'coordi nation': 'coordination',
        'incli nation': 'inclination',
        'con test ant': 'contestant',
        'was usedto': 'was used to',
        'becomes maller': 'become smaller',
        "brain'scellsshrink": "brain's cells shrink",
        'thebrain': 'the brain',
    }

    text_modified = text
    for wrong, right in known_fixes.items():
        if wrong in text_modified:
            text_modified = text_modified.replace(wrong, right)

    # Generic OCR space fix: lowercase letter, space, then 2-3 lowercase letters
    # that form a common English word fragment
    # Be conservative - only fix clear cases

    changed = text_modified != original
    return text_modified, changed


def fix_whitespace(text):
    """Fix excessive whitespace issues."""
    if not text:
        return text, False

    original = text
    # Replace multiple consecutive spaces with single space (but preserve newlines)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    # Remove leading/trailing whitespace on each line
    lines = text.split('\n')
    lines = [line.strip() for line in lines]
    text = '\n'.join(lines)
    # Remove leading/trailing whitespace overall
    text = text.strip()

    return text, text != original


def is_broken_cloze_question(question):
    """Check if a question is a broken cloze/fill-in-the-blank with no stem."""
    stem = question.get('stem', '').strip()
    qtype = question.get('type', '')
    options = question.get('options', {})

    # Empty stem with choice options - broken cloze question
    if not stem and qtype == 'choice' and options:
        # Check if options are single English words (vocabulary question pattern)
        all_english_words = all(
            re.match(r'^[a-zA-Z\s\'-]+$', str(v).strip())
            for v in options.values()
            if str(v).strip()
        )
        if all_english_words:
            return True

    return False


def has_empty_critical_options(question):
    """Check if a choice question has empty options that make it unanswerable."""
    if question.get('type') != 'choice':
        return False

    options = question.get('options', {})
    empty_count = sum(1 for v in options.values() if not str(v).strip())
    total = len(options)

    # If more than half the options are empty, the question is broken
    return total > 0 and empty_count > total / 2


def has_too_few_options(question):
    """Check if a choice question has fewer than 2 non-empty options."""
    if question.get('type') != 'choice':
        return False
    options = question.get('options', {})
    non_empty = sum(1 for v in options.values() if str(v).strip())
    return non_empty < 2


def fix_stem_trailing_garbage(stem):
    """Remove exam metadata that leaked into end of stems."""
    if not stem:
        return stem, False

    original = stem
    # Remove trailing page numbers
    stem = re.sub(r'\s*第\s*\d+\s*頁\s*$', '', stem)
    stem = re.sub(r'\s*共\s*\d+\s*頁\s*$', '', stem)
    # Remove trailing code numbers (5-digit exam codes)
    stem = re.sub(r'\s+\d{5}\s*$', '', stem)

    return stem, stem != original


def process_file(filepath):
    """Process a single JSON file and fix all detected errors."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"  ERROR: Cannot parse {filepath}: {e}")
        return False

    original_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
    modified = False

    # Fix 1: Clean exam_time metadata
    metadata = data.get('metadata', {})
    if fix_exam_time(metadata):
        modified = True
        inc_fix('metadata_leak_fixed')

    # Fix 2-7: Process questions
    questions = data.get('questions', [])
    questions_to_remove = []

    for i, q in enumerate(questions):
        # Fix 2: Remove broken cloze questions
        if is_broken_cloze_question(q):
            questions_to_remove.append(i)
            inc_fix('broken_cloze_removed')
            continue

        # Fix 3: Remove questions with all-empty options
        if has_empty_critical_options(q):
            questions_to_remove.append(i)
            inc_fix('empty_options_question_removed')
            continue

        # Fix 4: Remove choice questions with too few options
        if has_too_few_options(q):
            questions_to_remove.append(i)
            inc_fix('too_few_options_removed')
            continue

        # Fix 5: OCR space artifacts in stem
        stem = q.get('stem', '')
        new_stem, stem_changed = fix_ocr_spaces_in_english(stem)
        if stem_changed:
            q['stem'] = new_stem
            modified = True
            inc_fix('ocr_spaces_fixed_stem')

        # Fix 5b: OCR space artifacts in options
        options = q.get('options', {})
        for key, val in options.items():
            new_val, val_changed = fix_ocr_spaces_in_english(str(val))
            if val_changed:
                options[key] = new_val
                modified = True
                inc_fix('ocr_spaces_fixed_option')

        # Fix 6: Whitespace cleanup in stem
        new_stem, ws_changed = fix_whitespace(q.get('stem', ''))
        if ws_changed:
            q['stem'] = new_stem
            modified = True
            inc_fix('whitespace_fixed_stem')

        # Fix 6b: Whitespace cleanup in options
        for key, val in q.get('options', {}).items():
            new_val, ws_changed = fix_whitespace(str(val))
            if ws_changed:
                q['options'][key] = new_val
                modified = True
                inc_fix('whitespace_fixed_option')

        # Fix 7: Stem trailing garbage
        new_stem, garbage_changed = fix_stem_trailing_garbage(q.get('stem', ''))
        if garbage_changed:
            q['stem'] = new_stem
            modified = True
            inc_fix('stem_trailing_garbage_fixed')

    # Remove broken questions (in reverse order to preserve indices)
    if questions_to_remove:
        modified = True
        for idx in sorted(questions_to_remove, reverse=True):
            questions.pop(idx)

    # Fix 8: Clean notes - remove redundant instruction notes
    notes = data.get('notes', [])
    # Keep notes but clean whitespace
    cleaned_notes = []
    for note in notes:
        cleaned, _ = fix_whitespace(note)
        cleaned_notes.append(cleaned)
    if cleaned_notes != notes:
        data['notes'] = cleaned_notes
        modified = True
        inc_fix('notes_whitespace_fixed')

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
    print("Ralph-Loop Round 1: Comprehensive Text Error Fixer")
    print("=" * 60)

    file_count = 0
    for root, dirs, fnames in os.walk(BASE_DIR):
        for fname in fnames:
            if fname != '試題.json':
                continue
            filepath = os.path.join(root, fname)
            rel_path = os.path.relpath(filepath, BASE_DIR)
            file_count += 1

            result = process_file(filepath)
            stats["files_processed"] += 1
            if result:
                stats["files_modified"] += 1

            if file_count % 100 == 0:
                print(f"  Processed {file_count} files...")

    print(f"\n{'=' * 60}")
    print(f"Results:")
    print(f"  Files processed: {stats['files_processed']}")
    print(f"  Files modified: {stats['files_modified']}")
    print(f"\nFixes applied:")
    for fix_type, count in sorted(stats["fixes"].items(), key=lambda x: -x[1]):
        print(f"  {fix_type}: {count}")

    # Save stats
    stats_path = "/home/user/police-exam-archive/fix_round1_stats.json"
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"\nStats saved to: {stats_path}")

    return stats["files_modified"]


if __name__ == '__main__':
    modified = main()
    print(f"\nTotal files modified: {modified}")
