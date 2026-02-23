#!/usr/bin/env python3
"""
Comprehensive OCR Issue Scanner for Police Exam JSON Files.

Scans all exam JSON files under 考古題庫/ for 10 categories of OCR artifacts
and data quality issues. Outputs a structured JSON report.

Categories:
  1. PUA characters (Private Use Area: U+E000-U+F8FF)
  2. Broken English words (spaces inserted inside words)
  3. Missing spaces between English words (concatenated words)
  4. Page header/footer residue
  5. Five-digit exam code pollution
  6. Multiple consecutive spaces (3+)
  7. Empty or very short stems
  8. Options embedded in stem
  9. Truncated text
 10. CID references
"""

import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────

BASE_DIR = Path("/home/user/police-exam-archive/考古題庫")
REPORT_PATH = Path("/home/user/police-exam-archive/comprehensive_scan_report.json")

# Files to skip (not exam files)
SKIP_FILENAMES = {
    "answer_verification_report.json",
    "download_summary.json",
    "extraction_stats.json",
    "失敗清單.json",
}

# Severity levels
CRITICAL = "critical"
HIGH = "high"
MEDIUM = "medium"
LOW = "low"

# ── 1. PUA Character Detection ──────────────────────────────────────────────
PUA_RE = re.compile(r'[\uE000-\uF8FF\U000F0000-\U000FFFFF]')

# ── 2. Broken English Words (space inserted inside a word) ──────────────────
# Specific known broken patterns from OCR
BROKEN_WORD_PATTERNS = [
    (r'\boff\s+icer', 'officer'),
    (r'\bpol\s+ice\b', 'police'),
    (r'\bgov\s+ern', 'govern...'),
    (r'\bcon\s+sti\s*tu', 'constitu...'),
    (r'\bpro\s+tec', 'protec...'),
    (r'\bse\s+cu\s*ri', 'securi...'),
    (r'\bin\s+ves\s*ti\s*ga', 'investiga...'),
    (r'\bcri\s+mi\s*nal', 'criminal'),
    (r'\ben\s+force', 'enforce...'),
    (r'\bevi\s+dence', 'evidence'),
    (r'\bde\s+fen\s*d', 'defend...'),
    (r'\bpro\s+se\s*cu', 'prosecu...'),
    (r'\bjudg\s+ment', 'judgment'),
    (r'\bcom\s+mit\s*tee', 'committee'),
    (r'\bcom\s+mu\s*ni', 'communi...'),
    (r'\bde\s+part\s*ment', 'department'),
    (r'\bac\s+ci\s*dent', 'accident'),
    (r'\bpun\s+ish', 'punish...'),
    (r'\bman\s+age', 'manage...'),
    (r'\bim\s+por\s*tant', 'important'),
    (r'\bin\s+for\s*ma', 'informa...'),
    (r'\bor\s+gan\s*i\s*za', 'organiza...'),
    (r'\bre\s+spon\s*si', 'responsi...'),
    (r'\btech\s+no\s*lo', 'technolo...'),
    (r'\bser\s+vice', 'service'),
    (r'\bna\s+tion\s*al', 'national'),
    (r'\bpub\s+lic\b', 'public'),
    (r'\bsys\s+tem\b', 'system'),
    (r'\bprob\s+lem', 'problem'),
    (r'\bal\s+though\b', 'although'),
    (r'\bbe\s+cause\b', 'because'),
    (r'\bbe\s+tween\b', 'between'),
    (r'\bbe\s+fore\b', 'before'),
    (r'\bbe\s+lieve', 'believe'),
    (r'\bdi\s+ffer', 'differ...'),
    (r'\bfol\s+low', 'follow...'),
    (r'\bknow\s+ledge', 'knowledge'),
    (r'\bne\s+ces\s*sa', 'necessa...'),
    (r'\bpar\s+tic\s*u', 'particu...'),
    (r'\bpre\s+vent', 'prevent'),
    (r'\bto\s+geth\s*er', 'together'),
    (r'\bper\s+son\b', 'person'),
    (r'\bpeo\s+ple\b', 'people'),
    (r'\bprac\s+tice', 'practice'),
    (r'\bre\s+ceive', 'receive'),
    (r'\bre\s+cent\b', 'recent'),
    (r'\bin\s+ter\s*na\s*tion', 'internation...'),
    (r'\bex\s+am\s*ple', 'example'),
    (r'\bex\s+peri', 'experi...'),
    (r'\bap\s+proach', 'approach'),
    (r'\bap\s+pear', 'appear...'),
    (r'\bap\s+plic', 'applic...'),
    (r'\bad\s+minis', 'adminis...'),
    (r'\ban\s+nounce', 'announce'),
    (r'\bau\s+thor', 'author...'),
    (r'\bindi\s+vid', 'individ...'),
    (r'\binde\s+pend', 'independ...'),
    (r'\bdis\s+cov', 'discov...'),
    (r'\bdis\s+cuss', 'discuss'),
    (r'\bdis\s+tri', 'distri...'),
    (r'\bsup\s+port', 'support'),
    (r'\bsup\s+pose', 'suppose'),
    (r'\bsig\s+nif', 'signif...'),
    (r'\binter\s+est', 'interest'),
    (r'\bedu\s+ca', 'educa...'),
    (r'\bpres\s+ident', 'president'),
    (r'\benvi\s+ron', 'environ...'),
    (r'\bdevel\s+op', 'develop'),
    (r'\bintro\s+duc', 'introduc...'),
    (r'\bpopula\s+tion', 'population'),
    (r'\brecog\s+ni', 'recogni...'),
    (r'\battrac\s+tion', 'attraction'),
    # Suffix-split patterns (very common in OCR)
    (r'\b([A-Za-z]{3,})\s+tion\b', 'broken -tion suffix'),
    (r'\b([A-Za-z]{3,})\s+sion\b', 'broken -sion suffix'),
    (r'\b([A-Za-z]{3,})\s+ment\b', 'broken -ment suffix'),
    (r'\b([A-Za-z]{3,})\s+ness\b', 'broken -ness suffix'),
    (r'\b([A-Za-z]{3,})\s+ence\b', 'broken -ence suffix'),
    (r'\b([A-Za-z]{3,})\s+ance\b', 'broken -ance suffix'),
    (r'\b([A-Za-z]{3,})\s+able\b', 'broken -able suffix'),
    (r'\b([A-Za-z]{3,})\s+ible\b', 'broken -ible suffix'),
    (r'\b([A-Za-z]{3,})\s+ity\b', 'broken -ity suffix'),
    (r'\b([A-Za-z]{3,})\s+ous\b', 'broken -ous suffix'),
    (r'\b([A-Za-z]{3,})\s+ive\b', 'broken -ive suffix'),
    (r'\b([A-Za-z]{3,})\s+ally\b', 'broken -ally suffix'),
]

# Compile broken word patterns
BROKEN_WORD_RE = []
for pat, expected in BROKEN_WORD_PATTERNS:
    try:
        BROKEN_WORD_RE.append((re.compile(pat, re.IGNORECASE), expected))
    except re.error:
        pass

# Words that are valid standalone English words — if the part before the space
# is one of these, it's NOT a broken word (e.g., "are able" is valid)
VALID_STANDALONE_WORDS = {
    'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had',
    'her', 'was', 'one', 'our', 'out', 'has', 'his', 'how', 'its', 'may',
    'new', 'now', 'old', 'see', 'way', 'who', 'did', 'get', 'let', 'say',
    'she', 'too', 'use', 'per', 'own', 'any', 'pay', 'run', 'put', 'set',
    'try', 'ask', 'men', 'end', 'few', 'got', 'big', 'act', 'add', 'age',
    'ago', 'air', 'also', 'area', 'away', 'back', 'been', 'best', 'body',
    'both', 'call', 'came', 'case', 'city', 'come', 'could', 'data', 'days',
    'each', 'even', 'fact', 'feel', 'find', 'form', 'from', 'full', 'gave',
    'give', 'goes', 'gone', 'good', 'hand', 'have', 'head', 'help', 'here',
    'high', 'hold', 'home', 'just', 'keep', 'kind', 'know', 'land', 'last',
    'late', 'left', 'less', 'life', 'like', 'line', 'live', 'long', 'look',
    'made', 'make', 'many', 'more', 'most', 'move', 'much', 'must', 'name',
    'need', 'next', 'only', 'open', 'over', 'part', 'plan', 'play', 'said',
    'same', 'show', 'side', 'some', 'sure', 'take', 'tell', 'than', 'that',
    'them', 'then', 'they', 'this', 'time', 'turn', 'upon', 'used', 'very',
    'want', 'well', 'went', 'were', 'what', 'when', 'will', 'with', 'word',
    'work', 'year', 'your', 'being', 'great', 'place', 'point', 'right',
    'small', 'still', 'their', 'there', 'these', 'thing', 'think', 'those',
    'three', 'under', 'water', 'where', 'which', 'while', 'world', 'would',
    'young', 'after', 'again', 'begin', 'below', 'bring', 'carry', 'clear',
    'close', 'cover', 'early', 'earth', 'every', 'first', 'found', 'given',
    'going', 'group', 'house', 'large', 'later', 'learn', 'leave', 'level',
    'light', 'might', 'never', 'often', 'order', 'other', 'paper', 'power',
    'quite', 'shall', 'short', 'since', 'stand', 'start', 'state', 'story',
    'study', 'taken', 'until', 'using', 'watch', 'whole', 'write', 'above',
    'human', 'local', 'major', 'money', 'night', 'share', 'ready', 'serve',
    'seven', 'south', 'space', 'table', 'today', 'total', 'trade', 'treat',
    'value', 'voice', 'woman', 'women', 'train', 'truth', 'usual',
    'man', 'men', 'war', 'law', 'far', 'cut', 'hot', 'bit', 'low', 'car',
    'eye', 'sit', 'dog', 'eat', 'red', 'sun', 'bed', 'ten', 'top', 'yes',
    'yet', 'nor', 'god', 'boy', 'die', 'hit', 'six', 'art', 'led', 'lay',
    'sea', 'tax', 'nor', 'fit', 'bar', 'ran', 'met', 'saw', 'win', 'son',
    'wife', 'half', 'told', 'real', 'free', 'able', 'true', 'four', 'five',
    'hard', 'past', 'ever', 'done', 'west', 'east', 'north',
    # Specifically problematic: these + suffix-like words form valid phrases
    'most', 'least', 'less', 'ever', 'former', 'inner', 'outer', 'upper',
    'lower', 'super', 'over', 'under', 'counter', 'cross',
    # Comparatives / common adjectives that precede -able/-ible/-ive etc.
    'better', 'more', 'much', 'further', 'higher', 'lower',
    'select', 'collect', 'object', 'direct', 'correct', 'protect',
    'effect', 'perfect', 'detect', 'expect', 'respect', 'reject',
    'subject', 'connect', 'project',
}

# ── 3. Missing Spaces Between English Words ─────────────────────────────────
MISSING_SPACE_PATTERNS = [
    (r'\bofthe\b', 'of the'),
    (r'\btothe\b', 'to the'),
    (r'\binthe\b', 'in the'),
    (r'\bonthe\b', 'on the'),
    (r'\bforthe\b', 'for the'),
    (r'\bbythe\b', 'by the'),
    (r'\batthe\b', 'at the'),
    (r'\bfromthe\b', 'from the'),
    (r'\bwiththe\b', 'with the'),
    (r'\bandthe\b', 'and the'),
    (r'\bisthe\b', 'is the'),
    (r'\basthe\b', 'as the'),
    (r'\bwasthe\b', 'was the'),
    (r'\btobe\b', 'to be'),
    (r'\bcanbe\b', 'can be'),
    (r'\bwillbe\b', 'will be'),
    (r'\bhasbeen\b', 'has been'),
    (r'\bhavebeen\b', 'have been'),
    (r'\bdonot\b', 'do not'),
    (r'\bdoesnot\b', 'does not'),
    (r'\bshouldbe\b', 'should be'),
    (r'\bwouldbe\b', 'would be'),
    (r'\bmustbe\b', 'must be'),
    (r'\bmaybe\b', None),  # skip - "maybe" is a valid word
    (r'\bitis\b', 'it is'),
    (r'\bwhichis\b', 'which is'),
    (r'\bthatis\b', 'that is'),
    (r'\bthereare\b', 'there are'),
    (r'\bthereis\b', 'there is'),
    (r'\bcannotbe\b', 'cannot be'),
    # Concatenated at camelCase-like boundaries within running English text
    (r'(?<=[a-z])(?=[A-Z][a-z]{3,})', 'missing space at case boundary'),
]

# Known CamelCase proper nouns / brand names that should NOT be flagged
CAMELCASE_WHITELIST = {
    'YouTube', 'CompStat', 'iPhone', 'iPad', 'LinkedIn', 'JavaScript',
    'TypeScript', 'GitHub', 'WordPress', 'PowerPoint', 'YouTube',
    'McDonald', 'McGrath', 'McDonalds', 'McCarthy', 'McKinsey',
    'DeepMind', 'TikTok', 'WeChat', 'WhatsApp', 'FaceTime',
    'PayPal', 'MasterCard', 'FedEx', 'DreamWorks', 'StarBucks',
}
# Remove None entries and compile
MISSING_SPACE_RE = []
for pat, desc in MISSING_SPACE_PATTERNS:
    if desc is not None:
        try:
            MISSING_SPACE_RE.append((re.compile(pat), desc))
        except re.error:
            pass

# ── 4. Page Header/Footer Residue ───────────────────────────────────────────
HEADER_FOOTER_PATTERNS = [
    (re.compile(r'代號[：:]\s*\d{4,5}'), 'exam code header'),
    (re.compile(r'頁次[：:]\s*\d'), 'page number header'),
    (re.compile(r'第\s*\d+\s*頁'), 'page indicator'),
    (re.compile(r'請接背面'), 'continue on back'),
    (re.compile(r'請翻頁'), 'turn page'),
    (re.compile(r'背面尚有試題'), 'more questions on back'),
    (re.compile(r'全\s*\d+\s*頁'), 'total pages'),
    (re.compile(r'共\s*\d+\s*頁'), 'total pages'),
    (re.compile(r'座號[：:]'), 'seat number'),
]

# ── 5. Five-Digit Code Pollution ────────────────────────────────────────────
# Matches 5-digit codes starting with 4 or 5 (exam code patterns)
FIVE_DIGIT_CODE_RE = re.compile(r'(?<!\d)[45]\d{4}(?!\d)')

# ── 6. Multiple Consecutive Spaces ──────────────────────────────────────────
MULTI_SPACE_RE = re.compile(r' {3,}')

# ── 7. Empty/Short Stems — checked structurally, no regex needed ─────────────

# ── 8. Options Embedded in Stem ──────────────────────────────────────────────
OPTIONS_IN_STEM_RE = re.compile(r'\(A\).*?\(B\).*?\(C\)', re.DOTALL)

# ── 9. Truncated Text ───────────────────────────────────────────────────────
TRUNCATION_PATTERNS = [
    # Only flag mid-sentence punctuation (comma, semicolon, enumeration comma).
    # Do NOT flag ：or : — exam questions routinely end with colons.
    (re.compile(r'[，,；;、]\s*$'), 'ends with mid-sentence punctuation'),
    (re.compile(r'\b(and|or|but|the|a|an|of|to|in|for|with|by|from|that|this|is|are|was|were|be|have|has|had|not|can|will|shall|may|should|would|could|must|its|their|our|your|his|her)\s*$', re.IGNORECASE),
     'ends with function word'),
    (re.compile(r'(?:的|之|與|及|或|在|於|為|是|將|把|被|由|從|對|向|以|而|但|並|且|如|若|則|因|故|所|又|也|都|應|需|要|可|能|會|該|其|此)\s*$'),
     'ends with Chinese function word/particle'),
]

# ── 10. CID References ──────────────────────────────────────────────────────
CID_RE = re.compile(r'\(cid:\d+\)')

# ── Category metadata ───────────────────────────────────────────────────────
CATEGORIES = {
    "pua_characters": {
        "description": "Private Use Area characters (U+E000-U+F8FF) from PDF custom fonts",
        "severity": CRITICAL,
    },
    "broken_english_words": {
        "description": "Spaces inserted inside English words (e.g., 'off icer' -> 'officer')",
        "severity": HIGH,
    },
    "missing_spaces_english": {
        "description": "Missing spaces between concatenated English words (e.g., 'ofthe' -> 'of the')",
        "severity": MEDIUM,
    },
    "header_footer_residue": {
        "description": "Page header/footer text leaked into question content (代號, 頁次, 請接背面, etc.)",
        "severity": HIGH,
    },
    "five_digit_code_pollution": {
        "description": "Five-digit exam codes (e.g., 50120) stuck in question content",
        "severity": HIGH,
    },
    "multiple_consecutive_spaces": {
        "description": "Three or more consecutive spaces in text",
        "severity": LOW,
    },
    "empty_or_short_stems": {
        "description": "Choice questions with stem shorter than 5 characters",
        "severity": CRITICAL,
    },
    "options_in_stem": {
        "description": "Stems containing (A)(B)(C)(D) text while options dict is empty or duplicated",
        "severity": CRITICAL,
    },
    "truncated_text": {
        "description": "Text appearing to end mid-sentence or mid-word",
        "severity": MEDIUM,
    },
    "cid_references": {
        "description": "(cid:NNNN) patterns from PDF font extraction failures",
        "severity": CRITICAL,
    },
}


# ── Scanning functions ──────────────────────────────────────────────────────

def ctx(text, start, end, margin=20):
    """Extract context around a match."""
    s = max(0, start - margin)
    e = min(len(text), end + margin)
    return text[s:e].replace('\n', ' ')


def scan_text(text, field_name, extra_info, metadata_code=None):
    """Scan a text field for all issue categories. Returns dict of category -> list of issues."""
    if not text or not isinstance(text, str):
        return {}

    issues = defaultdict(list)

    # 1. PUA characters
    for m in PUA_RE.finditer(text):
        ch = m.group()
        issues["pua_characters"].append({
            "field": field_name,
            "char_code": f"U+{ord(ch):04X}",
            "context": ctx(text, m.start(), m.end()),
            **extra_info,
        })

    # 2. Broken English words
    seen_positions = set()
    for pattern, expected in BROKEN_WORD_RE:
        for m in pattern.finditer(text):
            matched = m.group()
            # For generic suffix-split patterns, check if the first part is a
            # valid standalone English word (e.g., "are able" is NOT broken)
            if expected and expected.startswith('broken -'):
                # Extract the word before the space
                parts = matched.strip().split()
                if len(parts) >= 2:
                    first_word = parts[0].lower()
                    if first_word in VALID_STANDALONE_WORDS:
                        continue
            # Deduplicate overlapping matches
            pos_key = (m.start(), m.end())
            if pos_key in seen_positions:
                continue
            seen_positions.add(pos_key)
            issues["broken_english_words"].append({
                "field": field_name,
                "found": matched,
                "expected": expected,
                "context": ctx(text, m.start(), m.end()),
                **extra_info,
            })

    # 3. Missing spaces between English words
    for pattern, desc in MISSING_SPACE_RE:
        for m in pattern.finditer(text):
            found = m.group() if m.group() else text[max(0,m.start()-3):m.start()+8]
            context_str = ctx(text, m.start(), m.end(), margin=30)
            # Skip camelCase matches that are known proper nouns
            if desc == 'missing space at case boundary':
                # Extract the full word around the boundary
                word_start = m.start()
                while word_start > 0 and text[word_start-1].isalpha():
                    word_start -= 1
                word_end = m.start()
                while word_end < len(text) and text[word_end].isalpha():
                    word_end += 1
                full_word = text[word_start:word_end]
                if any(full_word.startswith(w) or full_word == w for w in CAMELCASE_WHITELIST):
                    continue
                # Also skip if the word is in a Chinese context (mixed Chinese-English)
                before_ctx = text[max(0, word_start-2):word_start]
                after_word_end = word_end
                while after_word_end < len(text) and text[after_word_end].isalpha():
                    after_word_end += 1
                after_ctx = text[after_word_end:min(len(text), after_word_end+2)]
                has_cjk_before = bool(re.search(r'[\u4e00-\u9fff]', before_ctx))
                has_cjk_after = bool(re.search(r'[\u4e00-\u9fff]', after_ctx))
                if has_cjk_before or has_cjk_after:
                    continue
            issues["missing_spaces_english"].append({
                "field": field_name,
                "found": found,
                "suggestion": desc,
                "context": context_str,
                **extra_info,
            })

    # 4. Header/footer residue (only in stems and options, not notes)
    if field_name in ("stem", "option"):
        for pattern, desc in HEADER_FOOTER_PATTERNS:
            for m in pattern.finditer(text):
                issues["header_footer_residue"].append({
                    "field": field_name,
                    "found": m.group(),
                    "pattern_type": desc,
                    "context": ctx(text, m.start(), m.end()),
                    **extra_info,
                })

    # 5. Five-digit code pollution (in stems only)
    if field_name == "stem" and metadata_code:
        for m in FIVE_DIGIT_CODE_RE.finditer(text):
            code = m.group()
            # Only flag if it matches the exam's own code
            if code == metadata_code:
                issues["five_digit_code_pollution"].append({
                    "field": field_name,
                    "found": code,
                    "note": "matches exam code from metadata",
                    "context": ctx(text, m.start(), m.end()),
                    **extra_info,
                })
            else:
                # Check if embedded between Chinese chars (strong pollution signal)
                before = text[max(0, m.start()-3):m.start()]
                after = text[m.end():min(len(text), m.end()+3)]
                has_cjk_before = bool(re.search(r'[\u4e00-\u9fff]', before))
                has_cjk_after = bool(re.search(r'[\u4e00-\u9fff]', after))
                if has_cjk_before and has_cjk_after:
                    issues["five_digit_code_pollution"].append({
                        "field": field_name,
                        "found": code,
                        "note": "5-digit code sandwiched between Chinese text",
                        "context": ctx(text, m.start(), m.end()),
                        **extra_info,
                    })

    # 6. Multiple consecutive spaces
    for m in MULTI_SPACE_RE.finditer(text):
        issues["multiple_consecutive_spaces"].append({
            "field": field_name,
            "space_count": len(m.group()),
            "context": ctx(text, m.start(), m.end()).replace(' ', '\u2423'),
            **extra_info,
        })

    # 9. Truncated text (only for stems — see scan_question for gating logic)
    if field_name == "stem":
        stripped = text.rstrip()
        if stripped:
            for pattern, desc in TRUNCATION_PATTERNS:
                if pattern.search(stripped):
                    issues["truncated_text"].append({
                        "field": field_name,
                        "description": desc,
                        "text_ending": stripped[-50:].replace('\n', ' '),
                        **extra_info,
                    })
                    break  # one truncation flag per stem is enough

    # 10. CID references
    for m in CID_RE.finditer(text):
        issues["cid_references"].append({
            "field": field_name,
            "found": m.group(),
            "context": ctx(text, m.start(), m.end()),
            **extra_info,
        })

    return dict(issues)


def scan_question(question, file_rel, metadata_code):
    """Scan a single question for all issue types."""
    qnum = question.get("number", "?")
    qtype = question.get("type", "unknown")
    base_info = {"question_number": qnum, "question_type": qtype}

    all_issues = defaultdict(list)

    stem = question.get("stem", "")
    options = question.get("options", {})

    # Scan stem
    if isinstance(stem, str):
        stem_issues = scan_text(stem, "stem", base_info, metadata_code)
        for cat, items in stem_issues.items():
            # Filter truncated_text false positives for choice questions:
            # If the stem contains numbered sub-options (1xxxx 2xxxx 3xxxx etc.),
            # the "ending" is just the last sub-option text, not a truncation.
            if cat == "truncated_text" and qtype == "choice":
                has_numbered_options = bool(
                    re.search(r'[①②③④⑤⑥]|[1-6][^\d].*[2-6][^\d]', stem or '')
                )
                if has_numbered_options:
                    continue
            all_issues[cat].extend(items)

    # Scan options
    if isinstance(options, dict):
        for key, val in options.items():
            if isinstance(val, str):
                opt_info = {**base_info, "option_key": key}
                opt_issues = scan_text(val, "option", opt_info, metadata_code)
                for cat, items in opt_issues.items():
                    all_issues[cat].extend(items)

    # Scan passage if present
    passage = question.get("passage", "")
    if isinstance(passage, str) and passage:
        pass_issues = scan_text(passage, "passage", base_info, metadata_code)
        for cat, items in pass_issues.items():
            all_issues[cat].extend(items)

    # 7. Empty or short stems (structural check)
    if qtype == "choice":
        stem_text = stem if isinstance(stem, str) else ""
        if len(stem_text.strip()) < 5:
            all_issues["empty_or_short_stems"].append({
                "field": "stem",
                "stem_length": len(stem_text.strip()),
                "stem_content": stem_text.strip() if stem_text.strip() else "(empty)",
                **base_info,
            })

    # 8. Options embedded in stem
    if isinstance(stem, str) and OPTIONS_IN_STEM_RE.search(stem):
        if not options or len(options) == 0:
            all_issues["options_in_stem"].append({
                "field": "stem",
                "note": "stem contains (A)(B)(C)(D) but options dict is empty",
                "stem_preview": stem[:150].replace('\n', ' '),
                **base_info,
            })

    return dict(all_issues)


def scan_file(filepath):
    """Scan a single JSON file. Returns (file_issues_by_category, error_msg_or_None)."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {}, str(e)

    if not isinstance(data, dict):
        return {}, None

    metadata = data.get("metadata", {})
    metadata_code = metadata.get("code", "")
    questions = data.get("questions", [])
    rel_path = str(filepath.relative_to(BASE_DIR))

    file_issues = defaultdict(list)

    # Scan notes for PUA and CID only
    notes = data.get("notes", [])
    for i, note in enumerate(notes):
        if isinstance(note, str):
            note_info = {"location": f"notes[{i}]"}
            note_issues = scan_text(note, "note", note_info)
            for cat in ("pua_characters", "cid_references"):
                if cat in note_issues:
                    file_issues[cat].extend(note_issues[cat])

    # Scan each question
    for q in questions:
        q_issues = scan_question(q, rel_path, metadata_code)
        for cat, items in q_issues.items():
            file_issues[cat].extend(items)

    return dict(file_issues), None


def main():
    print(f"Comprehensive OCR Scanner")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Base directory: {BASE_DIR}")
    print()

    # Discover all exam JSON files
    all_json = sorted(BASE_DIR.rglob("*.json"))
    exam_files = [f for f in all_json if f.name not in SKIP_FILENAMES]
    print(f"Found {len(exam_files)} JSON files to scan (skipping {len(all_json) - len(exam_files)} metadata files).")
    print()

    # Aggregate
    global_counts = defaultdict(int)          # category -> total count
    global_affected_files = defaultdict(set)  # category -> set of files
    global_examples = defaultdict(list)       # category -> list of example issues (capped)
    MAX_EXAMPLES = 30

    files_scanned = 0
    files_with_issues = 0
    files_with_errors = 0
    all_file_summaries = []  # list of per-file summaries

    for filepath in exam_files:
        files_scanned += 1
        rel_path = str(filepath.relative_to(BASE_DIR))

        file_issues, error = scan_file(filepath)

        if error:
            files_with_errors += 1
            all_file_summaries.append({
                "file": rel_path,
                "error": error,
            })
            continue

        if file_issues:
            files_with_issues += 1
            file_summary = {"file": rel_path, "issues": {}}
            for cat, items in file_issues.items():
                count = len(items)
                global_counts[cat] += count
                global_affected_files[cat].add(rel_path)
                file_summary["issues"][cat] = count

                # Collect examples
                if len(global_examples[cat]) < MAX_EXAMPLES:
                    for item in items:
                        if len(global_examples[cat]) < MAX_EXAMPLES:
                            global_examples[cat].append({
                                "file": rel_path,
                                **item,
                            })

            all_file_summaries.append(file_summary)

        if files_scanned % 200 == 0:
            print(f"  ... scanned {files_scanned}/{len(exam_files)} files ...")

    # Build final report
    total_issues = sum(global_counts.values())

    report = {
        "scan_metadata": {
            "scan_time": datetime.now().isoformat(),
            "base_directory": str(BASE_DIR),
            "total_files_scanned": files_scanned,
            "files_with_issues": files_with_issues,
            "files_clean": files_scanned - files_with_issues - files_with_errors,
            "files_with_parse_errors": files_with_errors,
            "total_issues": total_issues,
        },
        "category_summary": {},
        "detailed_issues": {},
        "per_file_summary": [],
    }

    # Category summary
    for cat_key in CATEGORIES:
        cat_meta = CATEGORIES[cat_key]
        count = global_counts.get(cat_key, 0)
        affected = len(global_affected_files.get(cat_key, set()))
        report["category_summary"][cat_key] = {
            "description": cat_meta["description"],
            "severity": cat_meta["severity"],
            "total_occurrences": count,
            "affected_files_count": affected,
        }

    # Detailed issues (examples)
    for cat_key in CATEGORIES:
        examples = global_examples.get(cat_key, [])
        if examples:
            total = global_counts.get(cat_key, 0)
            report["detailed_issues"][cat_key] = {
                "showing": f"{len(examples)} of {total}",
                "examples": examples,
            }

    # Per-file summary (only files with issues)
    report["per_file_summary"] = [s for s in all_file_summaries if "issues" in s and s["issues"]]

    # Also list affected files per category
    report["affected_files_by_category"] = {}
    for cat_key in CATEGORIES:
        files_set = global_affected_files.get(cat_key, set())
        if files_set:
            report["affected_files_by_category"][cat_key] = sorted(files_set)

    # Write report
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Print summary
    print()
    print("=" * 75)
    print("  COMPREHENSIVE OCR SCAN RESULTS")
    print("=" * 75)
    print(f"  Files scanned:       {files_scanned}")
    print(f"  Files with issues:   {files_with_issues}")
    print(f"  Files clean:         {files_scanned - files_with_issues - files_with_errors}")
    print(f"  Parse errors:        {files_with_errors}")
    print(f"  Total issues found:  {total_issues}")
    print("=" * 75)
    print()
    print(f"  {'Category':<35} {'Severity':<10} {'Count':>8} {'Files':>8}")
    print(f"  {'-'*63}")

    for cat_key in CATEGORIES:
        cat_meta = CATEGORIES[cat_key]
        count = global_counts.get(cat_key, 0)
        fcount = len(global_affected_files.get(cat_key, set()))
        sev = cat_meta["severity"].upper()
        marker = " ***" if count > 0 and cat_meta["severity"] in (CRITICAL, HIGH) else ""
        print(f"  {cat_key:<35} {sev:<10} {count:>8} {fcount:>8}{marker}")

    print(f"  {'-'*63}")
    print(f"  {'TOTAL':<35} {'':10} {total_issues:>8}")
    print("=" * 75)
    print()
    print(f"  Report saved to: {REPORT_PATH}")
    print()

    # Print a few notable examples for critical/high categories
    for cat_key in CATEGORIES:
        cat_meta = CATEGORIES[cat_key]
        if cat_meta["severity"] not in (CRITICAL, HIGH):
            continue
        examples = global_examples.get(cat_key, [])
        if not examples:
            continue
        count = global_counts.get(cat_key, 0)
        print(f"  [{cat_meta['severity'].upper()}] {cat_key} ({count} total):")
        for ex in examples[:5]:
            file_str = ex.get("file", "?")
            qnum = ex.get("question_number", "?")
            context_str = ex.get("context", ex.get("stem_preview", ex.get("stem_content", ex.get("found", "?"))))
            if len(str(context_str)) > 80:
                context_str = str(context_str)[:77] + "..."
            print(f"    - {file_str} Q{qnum}: {context_str}")
        if count > 5:
            print(f"    ... and {count - 5} more")
        print()


if __name__ == "__main__":
    main()
