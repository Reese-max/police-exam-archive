#!/usr/bin/env python3
"""
Fix severe OCR errors in specific English passages where the OCR
produced massive concatenation and word-splitting artifacts.

These passages need targeted, context-aware replacements that
the generic fixer cannot handle.
"""

import json
import re
from pathlib import Path

BASE_DIR = Path("/home/user/police-exam-archive/考古題庫")

# ============================================================
# Targeted passage-level replacements
# Each entry: (file_glob_pattern, list of (old, new) replacements)
# ============================================================

PASSAGE_FIXES = {
    # ----------------------------------------------------------
    # 水上警察學系/114年/中華民國憲法與水上警察學系專業英文
    # Passage about fishing boat rescue (Q56-Q60)
    # ----------------------------------------------------------
    "水上警察學系/114年/中華民國憲法與水上警察學系專業英文/試題.json": [
        ("suffer edasuddenmechanical", "suffered a sudden mechanical"),
        ("rapid lyin a short", "rapidly in a short"),
        ("extinguis her but", "extinguisher but"),
        ("these ato escape", "the sea to escape"),
        ("act ivated the", "activated the"),
        ("contact edthe Air Force Comm and for bac kup", "contacted the Air Force Command for backup"),
        ("arrive dat the scene", "arrived at the scene"),
        ("boat'sengine", "boat's engine"),
        ("can nonsto help", "cannons to help"),
        ("launch ing a search", "launching a search"),
        ("byhelicopter for", "by helicopter for"),
        ("arrange dby the Coast Guardto", "arranged by the Coast Guard to"),
        ("detail edca use of the accidents till", "detailed cause of the accident still"),
        ("str essed that", "stressed that"),
        ("str eng then its", "strengthen its"),
        ("mari time safety", "maritime safety"),
        ("efficiencyinrescuinglives", "efficiency in rescuing lives"),
        # Options fixes
        ("Thefire from", "The fire from"),
        ("fall ing into", "falling into"),
        ("detail edca use will", "detailed cause will"),
        ("Thereis no fire extingui she ron", "There is no fire extinguisher on"),
        ("fifthparagraph", "fifth paragraph"),
        ("paragraphof this", "paragraph of this"),
        ("oftran sport didnot part icipate", "of transport did not participate"),
    ],

    # ----------------------------------------------------------
    # 交通學系電訊組/111年/中華民國憲法與警察專業英文
    # Passage about terrorism and organized crime (Q59-Q60)
    # ----------------------------------------------------------
    "交通學系電訊組/111年/中華民國憲法與警察專業英文/試題.json": [
        ("link ages", "linkages"),
        ("toideological", "to ideological"),
        ("operation ssoasto", "operations so as to"),
        ("per petuate", "perpetuate"),
        ("Inpracticalter ms", "In practical terms"),
        ("most not ably", "most notably"),
        ("tran sport", "transport"),
        # Q60 stem fixes
        ("referto", "refer to"),
        ("onterritories", "on territories"),
        ("top erpetuate", "to perpetuate"),
        # Option fixes
        ("reconci led", "reconciled"),
    ],

    # ----------------------------------------------------------
    # 交通學系電訊組/111年/通訊系統
    # Technical terms
    # ----------------------------------------------------------
    "交通學系電訊組/111年/通訊系統/試題.json": [
        ("impulseresponse", "impulse response"),
        ("cyclicredundancycheck", "cyclic redundancy check"),
        ("generatorpolynomial", "generator polynomial"),
    ],
}

# Also check if any other 中華民國憲法與警察專業英文 files from the same year
# share the same passage (they often do across categories for 111年)
SHARED_PASSAGE_CATEGORIES_111 = [
    "交通學系交通組", "公共安全學系社安組", "刑事警察學系", "國境警察學系境管組", "外事警察學系",
    "犯罪防治學系預防組", "行政管理學系", "行政警察學系", "法律學系", "資訊管理學系", "鑑識科學學系",
]


def apply_fixes(filepath, replacements):
    """Apply text replacements to a JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    changes = 0

    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            changes += 1

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return changes
    return 0


def main():
    total_fixes = 0
    files_fixed = 0

    # Apply direct fixes
    for rel_path, replacements in PASSAGE_FIXES.items():
        filepath = BASE_DIR / rel_path
        if filepath.exists():
            fixes = apply_fixes(filepath, replacements)
            if fixes:
                files_fixed += 1
                total_fixes += fixes
                print(f"Fixed {fixes} issues in: {rel_path}")
        else:
            print(f"WARNING: File not found: {rel_path}")

    # Check shared passages across categories for 111年
    terrorism_fixes = PASSAGE_FIXES.get(
        "交通學系電訊組/111年/中華民國憲法與警察專業英文/試題.json", [])

    for cat in SHARED_PASSAGE_CATEGORIES_111:
        rel_path = f"{cat}/111年/中華民國憲法與警察專業英文/試題.json"
        filepath = BASE_DIR / rel_path
        if filepath.exists():
            fixes = apply_fixes(filepath, terrorism_fixes)
            if fixes:
                files_fixed += 1
                total_fixes += fixes
                print(f"Fixed {fixes} issues in: {rel_path}")

    # Also scan for any OTHER files with the same passages
    # Check 水上警察學系 passage in other years
    water_fixes = PASSAGE_FIXES.get(
        "水上警察學系/114年/中華民國憲法與水上警察學系專業英文/試題.json", [])

    # Scan all English exam files for the same broken patterns
    print("\nScanning all files for remaining passage-level OCR issues...")
    for jf in sorted(BASE_DIR.rglob("*.json")):
        rel = str(jf.relative_to(BASE_DIR))
        if rel in PASSAGE_FIXES:
            continue  # Already handled

        try:
            with open(jf, 'r', encoding='utf-8') as f:
                content = f.read()
        except:
            continue

        # Check if this file has any of our known broken patterns
        all_fixes = []
        for fixes_list in PASSAGE_FIXES.values():
            for old, new in fixes_list:
                if old in content:
                    all_fixes.append((old, new))

        if all_fixes:
            fixes = apply_fixes(jf, all_fixes)
            if fixes:
                files_fixed += 1
                total_fixes += fixes
                print(f"Fixed {fixes} issues in: {rel}")

    print(f"\n{'='*60}")
    print(f"Passage-level fix complete!")
    print(f"Files fixed: {files_fixed}")
    print(f"Total fixes: {total_fixes}")


if __name__ == "__main__":
    main()
