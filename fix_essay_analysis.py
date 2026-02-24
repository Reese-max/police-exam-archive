#!/usr/bin/env python3
"""Fix all identified analysis errors in immigration exam JSON files."""

import json
import os
import re

EXAM_DIR = "考古題庫/移民特考"

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def fix_trailing_pipe(text):
    """Remove trailing pipe characters from text."""
    return re.sub(r'\s*\|\s*$', '', text)

def fix_all_files():
    stats = {"files_modified": 0, "pipes_fixed": 0, "page_bleeds_fixed": 0}

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

                # Fix trailing pipe in stem
                stem = q.get("stem", "")
                if stem and '|' in stem:
                    new_stem = fix_trailing_pipe(stem)
                    if new_stem != stem:
                        print(f"  [{rel_path}] Q{num} stem: removed trailing pipe")
                        q["stem"] = new_stem
                        modified = True
                        stats["pipes_fixed"] += 1

                # Fix trailing pipe and page bleed in options
                for opt_key in list(q.get("options", {}).keys()):
                    opt_val = q["options"][opt_key]
                    if not opt_val:
                        continue

                    # Check for page bleed (請接背面 + exam form text)
                    page_bleed_match = re.search(
                        r'\s*\(請接背面\).*$|\s*\(背面\).*$|\s*背面尚有試題.*$|\s*請翻面繼續作答.*$',
                        opt_val, re.DOTALL
                    )
                    if page_bleed_match:
                        new_val = opt_val[:page_bleed_match.start()].rstrip()
                        print(f"  [{rel_path}] Q{num} opt {opt_key}: removed page bleed: '{page_bleed_match.group().strip()[:60]}...'")
                        q["options"][opt_key] = new_val
                        modified = True
                        stats["page_bleeds_fixed"] += 1
                    elif '|' in opt_val:
                        new_val = fix_trailing_pipe(opt_val)
                        if new_val != opt_val:
                            print(f"  [{rel_path}] Q{num} opt {opt_key}: removed trailing pipe")
                            q["options"][opt_key] = new_val
                            modified = True
                            stats["pipes_fixed"] += 1

            if modified:
                save_json(filepath, data)
                stats["files_modified"] += 1

    return stats

if __name__ == "__main__":
    print("=== Fixing OCR artifacts in immigration exam files ===\n")
    stats = fix_all_files()
    print(f"\n=== Summary ===")
    print(f"Files modified: {stats['files_modified']}")
    print(f"Pipes fixed: {stats['pipes_fixed']}")
    print(f"Page bleeds fixed: {stats['page_bleeds_fixed']}")
