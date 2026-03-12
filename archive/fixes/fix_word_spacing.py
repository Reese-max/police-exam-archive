#!/usr/bin/env python3
"""Fix missing word spaces in English OCR text across immigration exam files."""

import json
import os
import re

EXAM_DIR = "考古題庫/國境警察學系移民組"

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def fix_concatenated_words(text):
    """Add spaces between concatenated English words (lowercase followed by uppercase)."""
    if not text:
        return text
    # Only fix if there are enough concatenated word patterns to indicate OCR error
    concat_count = len(re.findall(r'[a-z][A-Z][a-z]', text))
    if concat_count < 3:
        return text

    # Add space before uppercase letter preceded by lowercase
    fixed = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    # Also fix patterns like "word.Another" -> "word. Another"
    fixed = re.sub(r'(\.)([A-Z])', r'\1 \2', fixed)
    # Fix "word,Another" -> "word, Another"
    fixed = re.sub(r'(,)([A-Z])', r'\1 \2', fixed)
    # Fix "word;Another" -> "word; Another"
    fixed = re.sub(r'(;)([A-Z])', r'\1 \2', fixed)
    # Fix "word?Another" -> "word? Another"
    fixed = re.sub(r'(\?)([A-Z])', r'\1 \2', fixed)
    # Fix ")Another" -> ") Another"
    fixed = re.sub(r'(\))([A-Z])', r'\1 \2', fixed)
    # Fix double spaces that might result
    fixed = re.sub(r'  +', ' ', fixed)

    return fixed

def fix_all_files():
    stats = {"files_modified": 0, "fields_fixed": 0}

    for root, dirs, files in os.walk(EXAM_DIR):
        for f in files:
            if f != "試題.json":
                continue
            filepath = os.path.join(root, f)
            data = load_json(filepath)
            modified = False
            rel_path = os.path.relpath(filepath, EXAM_DIR)

            for q in data.get("questions", []):
                num = q.get("number", "?")

                # Fix stem
                stem = q.get("stem", "")
                new_stem = fix_concatenated_words(stem)
                if new_stem != stem:
                    q["stem"] = new_stem
                    modified = True
                    stats["fields_fixed"] += 1
                    print(f"  [{rel_path}] Q{num} stem: fixed word spacing")

                # Fix options
                for k in list(q.get("options", {}).keys()):
                    opt_val = q["options"][k]
                    new_val = fix_concatenated_words(opt_val)
                    if new_val != opt_val:
                        q["options"][k] = new_val
                        modified = True
                        stats["fields_fixed"] += 1
                        print(f"  [{rel_path}] Q{num} opt {k}: fixed word spacing")

                # Fix passage
                passage = q.get("passage", "")
                if passage:
                    new_passage = fix_concatenated_words(passage)
                    if new_passage != passage:
                        q["passage"] = new_passage
                        modified = True
                        stats["fields_fixed"] += 1
                        print(f"  [{rel_path}] Q{num} passage: fixed word spacing")

                # Fix passage_intro
                pi = q.get("passage_intro", "")
                if pi:
                    new_pi = fix_concatenated_words(pi)
                    if new_pi != pi:
                        q["passage_intro"] = new_pi
                        modified = True
                        stats["fields_fixed"] += 1

            if modified:
                save_json(filepath, data)
                stats["files_modified"] += 1

    return stats

if __name__ == "__main__":
    print("=== Fixing missing word spaces in English OCR text ===\n")
    stats = fix_all_files()
    print(f"\n=== Summary ===")
    print(f"Files modified: {stats['files_modified']}")
    print(f"Fields fixed: {stats['fields_fixed']}")
