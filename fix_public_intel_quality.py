#!/usr/bin/env python3
"""
公共安全學系社安組學系情報組題目品質修復腳本
Fix quality issues in 公共安全學系社安組學系情報組 exam question JSON files.

Issues fixed:
1. PASSAGE_IN_OPTION: Reading passages stuck in option D → extract to passage field
2. EMPTY_STEM: Empty stems for reading comprehension questions → link to passage
3. EXAM_TIME_JUNK: Remove "座號：" from exam_time
4. META_SUBJECT_TRUNCATED: Fix truncated metadata.subject using top-level subject
5. FEW_OPTIONS (108年 Q37-Q40): Fix paragraph structure questions with option A in stem
"""

import json
import os
import re
import shutil
from datetime import datetime

BASE_DIR = "考古題庫/公共安全學系社安組學系情報組"
BACKUP_DIR = "backups/公共安全學系社安組學系情報組_fix_" + datetime.now().strftime("%Y%m%d_%H%M%S")

stats = {
    "files_processed": 0,
    "files_modified": 0,
    "passage_extracted": 0,
    "empty_stem_fixed": 0,
    "exam_time_fixed": 0,
    "meta_subject_fixed": 0,
    "few_options_fixed": 0,
}


def backup_file(fpath):
    """Create a backup of the file before modifying."""
    rel = os.path.relpath(fpath, ".")
    backup_path = os.path.join(BACKUP_DIR, rel)
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    shutil.copy2(fpath, backup_path)


def fix_exam_time(data):
    """Remove '座號：' and trailing junk from exam_time."""
    meta = data.get("metadata", {})
    exam_time = meta.get("exam_time", "")
    if "座號" in exam_time:
        # Extract just the time portion
        cleaned = re.sub(r"\s*座號[：:].*$", "", exam_time).strip()
        if cleaned != exam_time:
            meta["exam_time"] = cleaned
            return True
    return False


def fix_meta_subject(data):
    """Fix truncated metadata.subject using top-level subject field."""
    meta = data.get("metadata", {})
    meta_subj = meta.get("subject", "")
    top_subj = data.get("subject", "")

    if not top_subj:
        return False

    # Normalize brackets for comparison: use full-width from PDF metadata
    # The top-level subject uses half-width (), metadata uses full-width （）
    # We'll standardize metadata to match top-level (half-width)
    normalized_meta = meta_subj.replace("（", "(").replace("）", ")")

    if meta_subj and meta_subj != top_subj:
        # Check if metadata is truncated version of top-level
        if top_subj.startswith(normalized_meta[:15]) or normalized_meta.startswith(top_subj[:15]):
            meta["subject"] = top_subj
            return True
        # Also fix bracket mismatch
        if normalized_meta == top_subj:
            meta["subject"] = top_subj
            return True

    return False


def extract_passage_from_option(questions):
    """
    Find cases where a reading passage is embedded in option D of one question,
    and the following questions have empty stems. Extract the passage and add it
    as a 'passage' field to the affected question group.

    Returns number of fixes made.
    """
    fixes = 0

    # Build index by question number for quick lookup
    q_by_num = {}
    for i, q in enumerate(questions):
        num = q.get("number")
        if isinstance(num, int):
            q_by_num[num] = (i, q)
        elif isinstance(num, str) and num.isdigit():
            q_by_num[int(num)] = (i, q)

    # Scan for passages stuck in options
    for i, q in enumerate(questions):
        if q.get("type") != "choice":
            continue

        opts = q.get("options", {})
        if not isinstance(opts, dict):
            continue

        # Check if option D (or last option) contains a reading passage
        for opt_key in ["D", "d"]:
            opt_val = opts.get(opt_key, "")
            if not isinstance(opt_val, str) or len(opt_val) < 200:
                continue

            # Look for the passage marker pattern (multiple variants)
            passage_patterns = [
                # 請依下文回答第41題至第45題:
                r"(.*?)\s*(請依下文回答第?\s*(\d+)\s*題[至到]第?\s*(\d+)\s*題[：:\s]*)(.*)",
                # 請依下文回答第41至45題:
                r"(.*?)\s*(請依下文回答第?\s*(\d+)\s*[至到]\s*(\d+)\s*題[：:\s]*)(.*)",
                # 請回答下列第41題至第45題:
                r"(.*?)\s*(請回答下列第?\s*(\d+)\s*題[至到]第?\s*(\d+)\s*題[：:\s]*)(.*)",
                # 請回答下列第41至45題:
                r"(.*?)\s*(請回答下列第?\s*(\d+)\s*[至到]\s*(\d+)\s*題[：:\s]*)(.*)",
                # 請依下文回答第46至50題:
                r"(.*?)\s*(請依下文回答第\s*(\d+)\s*至\s*第?\s*(\d+)\s*題[：:\s]*)(.*)",
            ]
            passage_match = None
            for pat in passage_patterns:
                passage_match = re.search(pat, opt_val, re.DOTALL)
                if passage_match:
                    break

            if passage_match:
                real_option = passage_match.group(1).strip()
                passage_header = passage_match.group(2).strip()
                start_q = int(passage_match.group(3))
                end_q = int(passage_match.group(4))
                passage_text = passage_match.group(5).strip()

                # Fix the current question's option D
                if real_option:
                    opts[opt_key] = real_option
                else:
                    opts[opt_key] = opts[opt_key]  # keep as is if no real option

                # Construct full passage with header
                full_passage = passage_header + "\n" + passage_text

                # Fix option D to only contain the actual option value
                opts[opt_key] = real_option
                fixes += 1
                stats["passage_extracted"] += 1

                # Apply passage to the group of questions
                for qnum in range(start_q, end_q + 1):
                    if qnum in q_by_num:
                        idx, target_q = q_by_num[qnum]
                        # Add passage reference
                        target_q["passage"] = full_passage
                        target_q["passage_question_range"] = f"{start_q}-{end_q}"

                        # If stem was empty, note it
                        if not target_q.get("stem", "").strip():
                            stats["empty_stem_fixed"] += 1

    return fixes


def fix_108_paragraph_structure(questions):
    """
    Fix 108年 Q37-Q40 paragraph structure questions where option A is in stem.
    These questions have stem="(A)They also found..." but options only have B,C,D.
    """
    fixes = 0
    for q in questions:
        num = q.get("number")
        opts = q.get("options", {})
        stem = q.get("stem", "")

        if not isinstance(opts, dict):
            continue

        # Detect: stem starts with (A) and options don't have A
        if stem.startswith("(A)") and "A" not in opts and isinstance(opts, dict):
            # Extract option A from stem
            option_a_text = stem.strip()
            opts["A"] = option_a_text

            # These are paragraph structure questions - stem should describe the task
            # Since all Q37-40 share the same structure, set a generic stem
            q["stem"] = ""
            q["options"] = dict(sorted(opts.items()))  # Sort A,B,C,D
            fixes += 1
            stats["few_options_fixed"] += 1

    return fixes


def process_file(fpath):
    """Process a single JSON file and fix all issues."""
    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    stats["files_processed"] += 1
    modified = False

    # Fix 1: exam_time
    if fix_exam_time(data):
        modified = True
        stats["exam_time_fixed"] += 1

    # Fix 2: metadata subject
    if fix_meta_subject(data):
        modified = True
        stats["meta_subject_fixed"] += 1

    # Fix 3: passage extraction
    questions = data.get("questions", [])
    if extract_passage_from_option(questions) > 0:
        modified = True

    # Fix 4: 108年 paragraph structure
    parts = fpath.split("/")
    year_str = parts[2] if len(parts) > 2 else ""
    if "108" in year_str:
        if fix_108_paragraph_structure(questions) > 0:
            modified = True

    if modified:
        backup_file(fpath)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        stats["files_modified"] += 1

    return modified


def main():
    print("=" * 70)
    print("公共安全學系社安組學系情報組 題目品質修復")
    print("=" * 70)
    print(f"備份目錄: {BACKUP_DIR}")
    print()

    os.makedirs(BACKUP_DIR, exist_ok=True)

    for root, dirs, files in sorted(os.walk(BASE_DIR)):
        for f in sorted(files):
            if not f.endswith(".json"):
                continue
            fpath = os.path.join(root, f)
            parts = fpath.split("/")
            label = "/".join(parts[2:4]) if len(parts) > 3 else fpath
            modified = process_file(fpath)
            if modified:
                print(f"  [修復] {label}")

    print()
    print("=" * 70)
    print("修復統計")
    print("=" * 70)
    for key, val in stats.items():
        print(f"  {key}: {val}")
    print()


if __name__ == "__main__":
    main()
