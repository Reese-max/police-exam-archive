#!/usr/bin/env python3
"""
Recover English reading comprehension questions that were incorrectly
deleted during the repair process. These questions exist in the backup
files with options embedded in the stem text.

Recoverable data:
- 109年 中華民國憲法與警察專業英文 Q56-60 (5 Qs × 11 categories)
- 111年 中華民國憲法與警察專業英文 Q57-60 (4 Qs × 12 categories)
- 106年 中華民國憲法與水上警察學系專業英文 Q51-60 (10 Qs × 1 category)
- 109年 中華民國憲法與水上警察學系專業英文 Q51-60 (10 Qs × 1 category)
"""

import json
import re
import glob
import os

BACKUP_DIR = "backups/repair_20260221_175555"


def parse_options_from_stem(stem_text):
    """Extract (A)(B)(C)(D) options from stem text.

    Handles formats like:
    - "(A)word1 (B)word2 (C)word3 (D)word4"
    - "(A)multi word option (B)another option (C)third (D)fourth"
    - Mixed with passage text
    """
    # Pattern: (A)text (B)text (C)text (D)text
    pattern = r'\(A\)(.*?)\s*\(B\)(.*?)\s*\(C\)(.*?)\s*\(D\)(.*?)$'

    # Try to find options at the end of stem
    match = re.search(pattern, stem_text, re.DOTALL)
    if match:
        a, b, c, d = [s.strip() for s in match.groups()]
        # Clean up: remove trailing passage text from D option
        # D option might be followed by "請依下文回答..." which is next passage
        passage_start = re.search(r'\s*請依下文回答', d)
        if passage_start:
            d = d[:passage_start.start()].strip()

        # Get the stem part (before options)
        stem_before = stem_text[:match.start()].strip()

        return stem_before, {"A": a, "B": b, "C": c, "D": d}

    return None, None


def extract_passage_from_stems(questions, start_num, end_num):
    """Extract passage text from the first question that contains it."""
    for q in questions:
        if start_num <= q["number"] <= end_num:
            stem = q.get("stem", "")
            # Check if stem contains passage text (longer than just options)
            if len(stem) > 200 and "請依下文回答" not in stem[:30]:
                # This might be a question with passage embedded
                return stem
            # Check for passage header
            match = re.search(r'請依下文回答第\d+\s*題至第\d+\s*題[：:]\s*(.*)', stem, re.DOTALL)
            if match:
                return match.group(0)
    return None


def fix_spacing(text):
    """Fix common PDF parsing spacing issues."""
    if not text:
        return text

    # Fix words concatenated together (camelCase-like patterns in English)
    # e.g., "TheNationalImmigrationAgency" -> "The National Immigration Agency"
    # But be careful not to break intentional patterns

    # Fix common concatenation patterns
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    # Fix missing space after periods
    text = re.sub(r'\.([A-Z])', r'. \1', text)
    # Fix missing space after commas
    text = re.sub(r',([A-Za-z])', r', \1', text)
    # Fix double spaces
    text = re.sub(r'  +', ' ', text)
    # Fix "- -" artifacts
    text = text.replace(' - -', '')
    text = text.replace('- -', '')

    return text.strip()


def process_backup_questions(backup_path, current_path):
    """Process a single backup file and recover missing questions."""
    with open(backup_path) as f:
        backup = json.load(f)
    with open(current_path) as f:
        current = json.load(f)

    backup_qs = {q["number"]: q for q in backup["questions"] if q.get("type") == "choice"}
    current_qs = {q["number"]: q for q in current["questions"] if q.get("type") == "choice"}

    current_nums = set(current_qs.keys())
    backup_nums = set(backup_qs.keys())
    missing_nums = sorted(backup_nums - current_nums)

    if not missing_nums:
        return current, 0

    # Collect recovered questions
    recovered = []

    # Build passage context from backup questions
    all_backup_sorted = sorted(backup_qs.values(), key=lambda q: q["number"])

    for num in missing_nums:
        bq = backup_qs[num]
        stem_text = bq.get("stem", "")
        answer = bq.get("answer", "")

        # Parse options from stem
        clean_stem, options = parse_options_from_stem(stem_text)

        if options is None:
            # Stem might be entirely passage text or a complex format
            # Try to handle as a passage-embedded question
            print(f"  WARNING: Could not parse options for Q{num}: {stem_text[:80]}...")
            continue

        # Fix spacing in options
        for key in options:
            options[key] = fix_spacing(options[key])

        # Determine passage
        passage = bq.get("passage", "")

        # For cloze questions (stem is empty or very short), find the passage
        if not clean_stem or len(clean_stem) < 10:
            # This is a cloze blank - stem is just options
            # Look for passage in nearby questions
            for prev_num in range(num - 1, max(0, num - 10), -1):
                if prev_num in backup_qs:
                    prev_stem = backup_qs[prev_num].get("stem", "")
                    passage_match = re.search(r'(請依下文回答第\d+\s*題至第\d+\s*題[：:].*)', prev_stem, re.DOTALL)
                    if passage_match:
                        passage = fix_spacing(passage_match.group(1))
                        break
                if prev_num in current_qs:
                    prev_passage = current_qs[prev_num].get("passage", "")
                    if prev_passage:
                        passage = prev_passage
                        break

            clean_stem = ""  # Cloze questions have empty stem
        else:
            clean_stem = fix_spacing(clean_stem)

        # Build recovered question
        new_q = {
            "number": num,
            "type": "choice",
            "stem": clean_stem,
            "options": options,
            "answer": answer,
        }
        if passage:
            new_q["passage"] = passage

        recovered.append(new_q)

    if not recovered:
        return current, 0

    # Insert recovered questions into current data
    all_questions = current["questions"] + recovered
    all_questions.sort(key=lambda q: (0 if q.get("type") == "choice" else 1, q.get("number", 0)))

    # Re-sort: essays first (by number), then choices (by number)
    essays = [q for q in all_questions if q.get("type") != "choice"]
    choices = [q for q in all_questions if q.get("type") == "choice"]
    choices.sort(key=lambda q: q["number"])

    current["questions"] = essays + choices

    return current, len(recovered)


def find_all_affected_files(year, subject_pattern):
    """Find all current files matching a year and subject pattern."""
    results = []
    for f in glob.glob("考古題庫/**/試題.json", recursive=True):
        parts = f.split("/")
        if len(parts) >= 4 and parts[2] == year and subject_pattern in parts[3]:
            results.append(f)
    return sorted(results)


def find_backup_file(category, year, subject_pattern):
    """Find the backup file for a given category/year/subject."""
    for f in glob.glob(f"{BACKUP_DIR}/**/試題.json", recursive=True):
        parts = f.split("/")
        if len(parts) >= 5 and parts[2] == category and parts[3] == year and subject_pattern in parts[4]:
            return f
    return None


def main():
    print("=" * 60)
    print("  Recovery of deleted English reading comprehension questions")
    print("=" * 60)

    # Define what to recover
    recovery_specs = [
        {
            "year": "109年",
            "subject_pattern": "中華民國憲法與警察專業英文",
            "expected_extra": [56, 57, 58, 59, 60],
            "description": "109年 警察專業英文 Q56-60",
        },
        {
            "year": "111年",
            "subject_pattern": "中華民國憲法與警察專業英文",
            "expected_extra": [57, 58, 59, 60],
            "description": "111年 警察專業英文 Q57-60",
        },
        {
            "year": "106年",
            "subject_pattern": "中華民國憲法與水上警察學系專業英文",
            "expected_extra": list(range(51, 61)),
            "description": "106年 水上警察學系專業英文 Q51-60",
        },
        {
            "year": "109年",
            "subject_pattern": "中華民國憲法與水上警察學系專業英文",
            "expected_extra": list(range(51, 61)),
            "description": "109年 水上警察學系專業英文 Q51-60",
        },
    ]

    total_recovered = 0
    total_files = 0

    for spec in recovery_specs:
        year = spec["year"]
        subject = spec["subject_pattern"]
        desc = spec["description"]

        print(f"\n--- {desc} ---")

        # Find all current files for this exam
        current_files = find_all_affected_files(year, subject)
        print(f"Found {len(current_files)} files to update")

        # Find a backup file to use as source
        # Use the first available category's backup
        backup_file = None
        for cf in current_files:
            parts = cf.split("/")
            category = parts[1]
            bf = find_backup_file(category, year, subject)
            if bf:
                backup_file = bf
                break

        if not backup_file:
            print(f"  ERROR: No backup found!")
            continue

        print(f"Using backup: {backup_file}")

        # Process the backup to get recovered questions
        with open(backup_file) as f:
            backup_data = json.load(f)
        backup_qs = {q["number"]: q for q in backup_data["questions"] if q.get("type") == "choice"}

        # Get the first current file to determine what's missing
        with open(current_files[0]) as f:
            sample_current = json.load(f)
        current_nums = set(q["number"] for q in sample_current["questions"] if q.get("type") == "choice")
        missing = sorted(set(backup_qs.keys()) - current_nums)
        print(f"Missing question numbers: {missing}")

        # Process backup to extract properly formatted questions
        test_result, test_count = process_backup_questions(backup_file, current_files[0])

        if test_count == 0:
            print(f"  WARNING: No questions recovered from backup")
            continue

        print(f"Recovered {test_count} questions from backup")

        # Extract the recovered questions (they're the new ones)
        recovered_qs = []
        test_nums = set(q["number"] for q in test_result["questions"] if q.get("type") == "choice")
        for q in test_result["questions"]:
            if q.get("type") == "choice" and q["number"] in set(missing):
                recovered_qs.append(q)

        # Show recovered questions for verification
        for q in recovered_qs:
            opts = q.get("options", {})
            print(f"  Q{q['number']}: stem='{q['stem'][:60]}...' opts={list(opts.keys())} ans={q['answer']}")

        # Apply to ALL files for this exam
        for cf in current_files:
            with open(cf) as f:
                curr_data = json.load(f)

            # Check if this file already has the questions
            curr_nums = set(q["number"] for q in curr_data["questions"] if q.get("type") == "choice")
            qs_to_add = [q for q in recovered_qs if q["number"] not in curr_nums]

            if not qs_to_add:
                continue

            # Add recovered questions
            import copy
            curr_data["questions"].extend(copy.deepcopy(qs_to_add))

            # Sort: essays first, then choices by number
            essays = [q for q in curr_data["questions"] if q.get("type") != "choice"]
            choices = [q for q in curr_data["questions"] if q.get("type") == "choice"]
            choices.sort(key=lambda q: q["number"])
            curr_data["questions"] = essays + choices

            # Write back
            with open(cf, "w", encoding="utf-8") as f:
                json.dump(curr_data, f, ensure_ascii=False, indent=2)
                f.write("\n")

            category = cf.split("/")[1]
            total_files += 1
            total_recovered += len(qs_to_add)
            print(f"  Updated: {category} (+{len(qs_to_add)} Qs)")

    print(f"\n{'=' * 60}")
    print(f"Total: Recovered {total_recovered} question instances across {total_files} files")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
