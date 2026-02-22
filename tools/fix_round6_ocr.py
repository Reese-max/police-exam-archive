#!/usr/bin/env python3
"""
Ralph-Loop Round 6: Fix remaining OCR artifacts found by Agent 1.

Fixes:
1. Broken words (58 patterns): "Str iking" → "Striking", etc.
2. Missing spaces after commas: ",New" → ", New"
3. Known concatenations: "acharge" → "a charge", etc.
4. CamelCase concatenations: "CrimePrevention" → "Crime Prevention", etc.
5. Concatenated prepositions: "ofan" → "of an", etc.
"""
import json
import os
import re
import sys

BASE_DIR = "/home/user/police-exam-archive/考古題庫"

stats = {"files_processed": 0, "files_modified": 0, "fixes": {}}

def inc_fix(fix_type, count=1):
    stats["fixes"][fix_type] = stats["fixes"].get(fix_type, 0) + count


# === 1. Broken word patterns (space inside word) ===
BROKEN_WORD_FIXES = [
    # Capital-start broken words
    (r'\bArson\s+ist\b', 'Arsonist'),
    (r'\bArt\s+ificial\b', 'Artificial'),
    (r'\bExpo\s+sure\b', 'Exposure'),
    (r'\bFire\s+fighter\b', 'Firefighter'),
    (r'\bInform\s+ant\b', 'Informant'),
    (r'\bOff\s+icials\b', 'Officials'),
    (r'\bOver\s+whelmed\b', 'Overwhelmed'),
    (r'\bStr\s+iking\b', 'Striking'),
    (r'\bTaiwan\s+ese\b', 'Taiwanese'),
    (r'\bTrans\s+parent\b', 'Transparent'),
    (r'\bTravel\s+ers\b', 'Travelers'),
    (r'\bUnder\s+cover\b', 'Undercover'),
    # Lowercase broken words
    (r'\bapp\s+aratus\b', 'apparatus'),
    (r'\bapp\s+rehended\b', 'apprehended'),
    (r'\bapp\s+ropriated\b', 'appropriated'),
    (r'\bapp\s+ropriation\b', 'appropriation'),
    (r'\bapp\s+roximate\b', 'approximate'),
    (r'\bapp\s+roximation\b', 'approximation'),
    (r'\bappear\s+ance\b', 'appearance'),
    (r'\bart\s+ificial\b', 'artificial'),
    (r'\bassault\s+ing\b', 'assaulting'),
    (r'\bcom\s+promise\b', 'compromise'),
    (r'\bcombat\s+ing\b', 'combating'),
    (r'\bcommit\s+ting\b', 'committing'),
    (r'\bcontami\s+nation\b', 'contamination'),
    (r'\bcoordina\s+ted\b', 'coordinated'),
    (r'\bdepend\s+ents\b', 'dependents'),
    (r'\bdis\s+charged\b', 'discharged'),
    (r'\bdispatc\s+her\b', 'dispatcher'),
    (r'\bearth\s+quake\b', 'earthquake'),
    (r'\bentit\s+led\b', 'entitled'),
    (r'\bexpo\s+sure\b', 'exposure'),
    (r'\bfinger\s+prints\b', 'fingerprints'),
    (r'\bfire\s+fighter\b', 'firefighter'),
    (r'\bflamm\s+able\b', 'flammable'),
    (r'\bhazard\s+ous\b', 'hazardous'),
    (r'\bhead\s+aches\b', 'headaches'),
    (r'\bkid\s+napped\b', 'kidnapped'),
    (r'\bmisdemea\s+nor\b', 'misdemeanor'),
    (r'\bmonitor\s+ing\b', 'monitoring'),
    (r'\bnatural\s+ization\b', 'naturalization'),
    (r'\bnight\s+mares\b', 'nightmares'),
    (r'\bper\s+ceptions\b', 'perceptions'),
    (r'\bplain\s+tiff\b', 'plaintiff'),
    (r'\bprohi\s+bit\b', 'prohibit'),
    (r'\brest\s+orative\b', 'restorative'),
    (r'\brest\s+ricted\b', 'restricted'),
    (r'\breturn\s+ing\b', 'returning'),
    (r'\bsim\s+ulations\b', 'simulations'),
    (r'\bspecial\s+ized\b', 'specialized'),
    (r'\bthe\s+ory\b', 'theory'),
    (r'\btrans\s+action\b', 'transaction'),
    (r'\btrans\s+actions\b', 'transactions'),
    (r'\btrans\s+parent\b', 'transparent'),
    (r'\btranscri\s+bed\b', 'transcribed'),
    (r'\btrauma\s+tic\b', 'traumatic'),
    (r'\btravel\s+ers\b', 'travelers'),
    (r'\bunder\s+cover\b', 'undercover'),
]

# === 2. CamelCase concatenations (real issues, not proper names) ===
# These appear in parenthetical English terms within Chinese text
CAMELCASE_FIXES = {
    'LoneWolf': 'Lone Wolf',
    'IntelligenceStrategyof': 'Intelligence Strategy of',
    'UNRefugeeAgency': 'UN Refugee Agency',
    'EgmontGroup': 'Egmont Group',
    'EconomicZone': 'Economic Zone',
    'DifferentialReinforcement': 'Differential Reinforcement',
    'CrimePrevention': 'Crime Prevention',
    'TargetRemoval': 'Target Removal',
    'RuleSetting': 'Rule Setting',
    'NewOpportunity': 'New Opportunity',
    'DifferentialAssociation': 'Differential Association',
    'PreventivePatrol': 'Preventive Patrol',
    'ProblemBehavior': 'Problem Behavior',
    'CourseAnalysis': 'Course Analysis',
    'CheeseModel': 'Cheese Model',
    'RiskManagement': 'Risk Management',
    'CrisisManagement': 'Crisis Management',
    'PolicyAnalysis': 'Policy Analysis',
    'ComputerForensics': 'Computer Forensics',
    'SoftwareForensics': 'Software Forensics',
    'DataForensics': 'Data Forensics',
    'DataAnalytics': 'Data Analytics',
    'SystemExtraction': 'System Extraction',
    'PhysicalExtraction': 'Physical Extraction',
    'MarcelProust': 'Marcel Proust',
    'DeltaModulation': 'Delta Modulation',
    'GenerativeArtificial': 'Generative Artificial',
    'InvestigationPrinciplesand': 'Investigation Principles and',
    'DEFSOPforMobile': 'DEFSOP for Mobile',
    'andOhlin': 'and Ohlin',
    'ofGod': 'of God',
}

# === 3. Known concatenation fixes ===
KNOWN_CONCAT_FIXES = {
    'Creationof': 'Creation of',
    'Evolutionof': 'Evolution of',
    'Howdoes': 'How does',
    'acharge': 'a charge',
    'afine': 'a fine',
    'alocal': 'a local',
    'alonein': 'alone in',
    'avictim': 'a victim',
    'bannedin': 'banned in',
    'bebuilt': 'be built',
    'canbe': 'can be',
    'ofcyber': 'of cyber',
    'orit': 'or it',
    'shewas': 'she was',
    'sohe': 'so he',
    'suchas': 'such as',
    'tobe': 'to be',
    'tocalm': 'to calm',
}

# Patterns that need regex (partial word boundaries)
KNOWN_CONCAT_REGEX = [
    # "...edto" patterns (e.g., "reportedto", "allowedto")
    (r'([a-z])edto\b', r'\1ed to'),
    # "...ingimmediate" patterns
    (r'([a-z])ingimmediate', r'\1ing immediate'),
    # "...sare" patterns (e.g., "officersare")
    (r'([a-z])sare\b', r'\1s are'),
    # "regularlyassigned"
    (r'regularly(?=assigned)', 'regularly '),
    # "step pedupto" -> "stepped up to"
    (r'step\s*pedupto', 'stepped up to'),
    # "suspect'sre" -> "suspect's re"
    (r"suspect'sre", "suspect's re"),
    # "orlotteryas" -> "or lottery as"
    (r'orlotteryas', 'or lottery as'),
    # "hefai" -> "he fai"
    (r'\bhefai', 'he fai'),
    # "jobop" -> "job op"
    (r'\bjobop', 'job op'),
    # "ifa" -> "if a" (careful with word boundary)
    (r'\bifa\b', 'if a'),
]

# === 4. Concatenated prepositions ===
CONCAT_PREP_FIXES = [
    (r'\bAsailor\b', 'A sailor'),
    (r'\bInan\b', 'In an'),
    (r'\bThenow\b', 'The now'),
    (r'\bandair\b', 'and air'),
    (r'(?<=[, ])andits\b', 'and its'),
    (r'\basamule\b', 'as a mule'),
    (r'\batapeto\b', 'a tape to'),
    (r'\bofan\b', 'of an'),
    (r'\bofsome\b', 'of some'),
    (r'\bthearea\b', 'the area'),
    (r'\btododge\b', 'to dodge'),
    (r'\btoheat\b', 'to heat'),
]


def fix_text(text):
    """Apply all OCR fixes to a text string."""
    if not text:
        return text, False

    original = text

    # 1. Broken word fixes (regex)
    for pattern, replacement in BROKEN_WORD_FIXES:
        text = re.sub(pattern, replacement, text)

    # 2. CamelCase fixes (exact string replacement)
    for wrong, right in CAMELCASE_FIXES.items():
        if wrong in text:
            text = text.replace(wrong, right)

    # 3. Known concatenation fixes (exact string)
    for wrong, right in KNOWN_CONCAT_FIXES.items():
        if wrong in text:
            # Use word boundary-aware replacement
            text = re.sub(r'(?<![a-zA-Z])' + re.escape(wrong) + r'(?![a-zA-Z])', right, text)

    # 3b. Known concatenation regex patterns
    for pattern, replacement in KNOWN_CONCAT_REGEX:
        text = re.sub(pattern, replacement, text)

    # 4. Concatenated preposition fixes
    for pattern, replacement in CONCAT_PREP_FIXES:
        if replacement is None:
            continue  # Skip false positives
        text = re.sub(pattern, replacement, text)

    # 5. Missing space after comma (before uppercase letter)
    # Pattern: comma directly followed by uppercase letter (no space)
    text = re.sub(r',([A-Z])', r', \1', text)

    return text, text != original


def process_file(filepath):
    """Process a single file for Round 6 fixes."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return False

    original_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
    modified = False

    for q in data.get('questions', []):
        # Fix stem
        stem = q.get('stem', '')
        new_stem, changed = fix_text(stem)
        if changed:
            q['stem'] = new_stem
            modified = True
            inc_fix('stem_fixed')

        # Fix options
        for key, val in q.get('options', {}).items():
            new_val, changed = fix_text(str(val))
            if changed:
                q['options'][key] = new_val
                modified = True
                inc_fix('option_fixed')

    if modified:
        new_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
        if new_json != original_json:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True

    return False


def main():
    print("=" * 60)
    print("Ralph-Loop Round 6: Fix Remaining OCR Artifacts")
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

    return stats["files_modified"]


if __name__ == '__main__':
    modified = main()
    print(f"\nTotal files modified: {modified}")
