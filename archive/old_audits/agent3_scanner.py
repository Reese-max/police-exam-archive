#!/usr/bin/env python3
"""
Agent 3: Chinese Text Quality Scanner for Police Exam Archive
Scans all exam JSON files for text quality issues including:
1. Random English characters mixed into Chinese text (OCR artifacts)
2. Broken/mojibake characters (亂碼)
3. Incorrect/excessive punctuation
4. Truncated text (cut off mid-sentence)
5. Circled numbers (①②③) that should be regular numbers
6. "座號" or exam page layout artifacts
7. Garbage in metadata fields
"""

import json
import re
import os
import sys
from collections import defaultdict, Counter
from pathlib import Path
from datetime import datetime

BASE_DIR = "/home/user/police-exam-archive/考古題庫"
OUTPUT_FILE = "/home/user/police-exam-archive/agent3_chinese_report.json"

# ── Issue collection ──────────────────────────────────────────────────────────
issues = []
file_count = 0
files_with_issues = set()
issue_type_counts = Counter()
per_file_issue_counts = Counter()

def add_issue(filepath, issue_type, location, text_snippet, details="", severity="medium"):
    """Record an issue found in a file."""
    global issues
    rel_path = os.path.relpath(filepath, BASE_DIR)
    issue = {
        "file": rel_path,
        "issue_type": issue_type,
        "severity": severity,
        "location": location,
        "text_snippet": text_snippet[:300] if text_snippet else "",
        "details": details
    }
    issues.append(issue)
    files_with_issues.add(rel_path)
    issue_type_counts[issue_type] += 1
    per_file_issue_counts[rel_path] += 1

# ── Check 1: Random English characters mixed into Chinese text ────────────
def check_random_english_in_chinese(text, filepath, location):
    """
    Find random single English letters or short English fragments
    that appear incorrectly mixed into Chinese text.
    """
    if not text or len(text) < 2:
        return

    # Known legitimate patterns where single English letters appear in Chinese context
    LEGITIMATE_PATTERNS = {
        'e化', 'e世代', 'e政府', 'e管家',  # e-government/e-era terms
        'K他命', 'K粉',                      # Ketamine
        'X光', 'X射線', 'X線',               # X-ray
        'T恤',                                # T-shirt
        'U型', 'V型', 'L型', 'S型', 'T型',   # Shape descriptions
        'P2P', 'B2B', 'C2C',                 # Business terms
        'M化', 'M化偵查',                     # Mobile investigation system
    }

    # Pattern: Chinese char, then 1-2 random lowercase letters, then Chinese char
    # This catches OCR artifacts like "凌晨l時" (l instead of 1)
    pattern = r'[\u4e00-\u9fff\u3000-\u303f]([a-z]{1,2})[\u4e00-\u9fff\u3000-\u303f]'
    for m in re.finditer(pattern, text):
        eng_fragment = m.group(1)
        context_start = max(0, m.start() - 15)
        context_end = min(len(text), m.end() + 15)
        context = text[context_start:context_end]

        # Check if this matches any known legitimate pattern
        is_legitimate = False
        for legit in LEGITIMATE_PATTERNS:
            if legit in context:
                is_legitimate = True
                break

        if is_legitimate:
            continue

        # Skip if in a formula/math context
        wider_start = max(0, m.start() - 30)
        wider_end = min(len(text), m.end() + 30)
        wider = text[wider_start:wider_end]
        if re.search(r'[=+\-*/÷×∈∋≤≥<>%]', wider):
            continue

        # Skip if this is part of variable enumeration (a、b、c pattern)
        if re.search(r'[a-z]、[a-z]', wider):
            continue

        # Skip if near other English text (legitimate English passage)
        eng_in_wider = len(re.findall(r'[a-zA-Z]', wider))
        if eng_in_wider > len(wider) * 0.3:
            continue

        # Flag as genuine issue - likely OCR artifact
        # Determine if it's likely l/1 or O/0 confusion
        if eng_fragment == 'l':
            add_issue(filepath, "random_english_in_chinese", location, context,
                      f"OCR confusion: lowercase 'l' likely should be digit '1'",
                      severity="high")
        elif eng_fragment == 'O' or eng_fragment == 'o':
            add_issue(filepath, "random_english_in_chinese", location, context,
                      f"OCR confusion: letter '{eng_fragment}' likely should be digit '0'",
                      severity="high")
        else:
            add_issue(filepath, "random_english_in_chinese", location, context,
                      f"Suspicious English '{eng_fragment}' embedded in Chinese text",
                      severity="medium")

    # Pattern: Single uppercase letter sandwiched between Chinese (excluding common variables)
    pattern2 = r'[\u4e00-\u9fff]([A-Z])[\u4e00-\u9fff]'
    for m in re.finditer(pattern2, text):
        letter = m.group(1)
        context_start = max(0, m.start() - 15)
        context_end = min(len(text), m.end() + 15)
        context = text[context_start:context_end]

        # Check against legitimate patterns
        is_legitimate = False
        for legit in LEGITIMATE_PATTERNS:
            if legit in context:
                is_legitimate = True
                break
        if is_legitimate:
            continue

        # Skip A/B/C/D option references
        if letter in ('A', 'B', 'C', 'D', 'E'):
            continue

        # Skip if near parentheses (likely an option reference)
        wider_start = max(0, m.start() - 20)
        wider_end = min(len(text), m.end() + 20)
        wider = text[wider_start:wider_end]
        if re.search(r'[（(]\s*' + letter + r'\s*[)）]', wider):
            continue

        # Skip if looks like variable placeholder in exam (X年, Y萬, Z公斤 pattern)
        if letter in ('X', 'Y', 'Z', 'N', 'M', 'P', 'Q', 'R', 'S', 'T', 'H', 'K', 'L', 'W', 'F', 'G', 'I', 'J', 'U', 'V'):
            # These are commonly used as variables/placeholders in exam questions
            # Check if preceded by exam-variable context
            if re.search(r'[A-Z][\u4e00-\u9fff]', context):
                # Skip - this is used as a placeholder variable
                continue

        # Skip if this looks like a known abbreviation context
        if re.search(r'[A-Z]{2,}', wider):
            continue

    # Pattern: English words that look like OCR artifacts in predominantly Chinese text
    if len(text) > 20:
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        total_chars = len(text.replace(' ', ''))
        if total_chars > 0 and chinese_chars / total_chars > 0.6:
            eng_fragments = re.finditer(r'(?<![A-Za-z])([a-zA-Z]{3,15})(?![A-Za-z])', text)
            # Extended known English words/abbreviations list
            known_english = {
                'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her',
                'was', 'one', 'our', 'out', 'has', 'his', 'how', 'its', 'may', 'new', 'now',
                'old', 'see', 'way', 'who', 'did', 'get', 'let', 'say', 'she', 'too', 'use',
                'DNA', 'RNA', 'GPS', 'SOP', 'CPR', 'AED', 'LED', 'USB', 'WiFi', 'APP', 'app',
                'LINE', 'CPU', 'SIM', 'PIN', 'PDA', 'IP', 'IT', 'CEO', 'NGO', 'WHO', 'WTO',
                'pdf', 'PDF', 'www', 'http', 'https', 'com', 'org', 'net', 'gov',
                'CCTV', 'PTSD', 'IQ', 'EQ', 'AIDS', 'HIV', 'ICU',
                'No', 'no', 'YES', 'yes', 'OK', 'ok',
                'TCP', 'UDP', 'HTTP', 'HTTPS', 'SSL', 'VPN', 'LAN', 'WAN', 'MAC',
                'IoT', 'API', 'SQL', 'NoSQL', 'PHP', 'CSS', 'HTML', 'XML', 'JSON',
                'Windows', 'Linux', 'Android', 'iOS', 'Java', 'Python',
                'Facebook', 'Google', 'Yahoo', 'Microsoft', 'Apple',
                'email', 'Email', 'blog', 'Blog', 'wifi', 'WIFI',
                'log', 'bit', 'byte', 'pixel', 'ray', 'Ray',
                'diaza', 'fluoren', 'one', 'ray', 'mL', 'mg', 'kg', 'pH',
                'mol', 'ppm', 'ppb', 'rpm',
            }
            for m in eng_fragments:
                word = m.group(1)
                if word in known_english or word.upper() in known_english or word.lower() in known_english:
                    continue
                surrounding_start = max(0, m.start() - 30)
                surrounding_end = min(len(text), m.end() + 30)
                surrounding = text[surrounding_start:surrounding_end]
                eng_in_surrounding = len(re.findall(r'[a-zA-Z]', surrounding))
                if eng_in_surrounding > len(surrounding) * 0.35:
                    continue  # Legitimate English section
                if re.match(r'^[A-Z][a-z]+$', word):
                    continue  # Capitalized word - likely proper noun
                if re.match(r'^[A-Z]+$', word) and len(word) <= 5:
                    continue  # Short all-caps - likely abbreviation
                if re.match(r'^[a-z]+$', word) and len(word) <= 2:
                    continue  # Short lowercase - likely variable
                # Check for chemical/scientific notation
                if re.search(r'\d', surrounding) and re.search(r'[a-zA-Z]\d|\d[a-zA-Z]', surrounding):
                    continue  # Scientific formula context


# ── Check 2: Broken characters / mojibake ─────────────────────────────────
def check_mojibake(text, filepath, location):
    """Detect broken/garbled characters (亂碼) in text."""
    if not text:
        return

    # Unicode replacement character
    if '\ufffd' in text:
        idx = text.index('\ufffd')
        context = text[max(0, idx-15):min(len(text), idx+15)]
        add_issue(filepath, "mojibake", location, context,
                  "Unicode replacement character (U+FFFD) found",
                  severity="high")

    # Sequences of CJK compatibility ideographs (often mojibake)
    mojibake_ranges = re.finditer(r'[\uf900-\ufaff]{3,}', text)
    for m in mojibake_ranges:
        context_start = max(0, m.start() - 10)
        context_end = min(len(text), m.end() + 10)
        add_issue(filepath, "mojibake", location,
                  text[context_start:context_end],
                  "Suspicious CJK compatibility ideograph sequence",
                  severity="high")

    # Check for Private Use Area characters
    pua_pattern = re.finditer(r'[\ue000-\uf8ff]', text)
    for m in pua_pattern:
        context_start = max(0, m.start() - 10)
        context_end = min(len(text), m.end() + 10)
        add_issue(filepath, "mojibake", location,
                  text[context_start:context_end],
                  f"Private Use Area character U+{ord(m.group()):04X} found",
                  severity="high")

    # Check for control characters (except common whitespace)
    control_pattern = re.finditer(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', text)
    for m in control_pattern:
        context_start = max(0, m.start() - 10)
        context_end = min(len(text), m.end() + 10)
        add_issue(filepath, "mojibake", location,
                  repr(text[context_start:context_end]),
                  f"Control character U+{ord(m.group()):04X} found",
                  severity="high")

    # Multiple consecutive rare/unusual Unicode formatting characters
    unusual = re.finditer(r'[\u2000-\u200f\u2028-\u202f\u205f-\u206f]{2,}', text)
    for m in unusual:
        context_start = max(0, m.start() - 10)
        context_end = min(len(text), m.end() + 10)
        add_issue(filepath, "mojibake", location,
                  repr(text[context_start:context_end]),
                  "Suspicious Unicode formatting character sequence",
                  severity="medium")

    # Latin-1/UTF-8 mojibake patterns
    garbled = re.finditer(r'[ÃÂ¡¢£¤¥¦§¨©ª«¬®¯°±²³´µ¶·¸¹º»¼½¾¿À-ÿ]{2,}', text)
    for m in garbled:
        context_start = max(0, m.start() - 10)
        context_end = min(len(text), m.end() + 10)
        add_issue(filepath, "mojibake", location,
                  text[context_start:context_end],
                  "Latin-1/UTF-8 mojibake pattern detected",
                  severity="high")

    # Check for Hangul syllables mixed into Chinese text (encoding confusion)
    if re.search(r'[\u4e00-\u9fff]', text):  # Only if has Chinese
        hangul = re.finditer(r'[\uac00-\ud7af]', text)
        for m in hangul:
            context_start = max(0, m.start() - 10)
            context_end = min(len(text), m.end() + 10)
            add_issue(filepath, "mojibake", location,
                      text[context_start:context_end],
                      f"Korean Hangul character U+{ord(m.group()):04X} in Chinese text - likely encoding issue",
                      severity="high")


# ── Check 3: Incorrect/excessive punctuation ──────────────────────────────
def check_punctuation(text, filepath, location):
    """Check for incorrect or excessive punctuation."""
    if not text or len(text) < 3:
        return

    # Multiple consecutive commas (Chinese or English)
    for m in re.finditer(r'[,，]{2,}', text):
        context_start = max(0, m.start() - 15)
        context_end = min(len(text), m.end() + 15)
        add_issue(filepath, "excessive_punctuation", location,
                  text[context_start:context_end],
                  f"Multiple consecutive commas ({len(m.group())} commas)",
                  severity="medium")

    # Multiple consecutive Chinese periods
    for m in re.finditer(r'[。]{2,}', text):
        context_start = max(0, m.start() - 15)
        context_end = min(len(text), m.end() + 15)
        add_issue(filepath, "excessive_punctuation", location,
                  text[context_start:context_end],
                  f"Multiple consecutive Chinese periods ({len(m.group())})",
                  severity="medium")

    # Excessive question marks or exclamation marks (3+)
    for m in re.finditer(r'[？?]{3,}|[！!]{3,}', text):
        context_start = max(0, m.start() - 15)
        context_end = min(len(text), m.end() + 15)
        add_issue(filepath, "excessive_punctuation", location,
                  text[context_start:context_end],
                  "Excessive question/exclamation marks",
                  severity="low")

    # Multiple consecutive colons or semicolons
    for m in re.finditer(r'[：:]{2,}|[；;]{2,}', text):
        context_start = max(0, m.start() - 15)
        context_end = min(len(text), m.end() + 15)
        add_issue(filepath, "excessive_punctuation", location,
                  text[context_start:context_end],
                  "Multiple consecutive colons/semicolons",
                  severity="medium")

    # Period right after opening parenthesis
    for m in re.finditer(r'[（(][。.]', text):
        context_start = max(0, m.start() - 10)
        context_end = min(len(text), m.end() + 10)
        add_issue(filepath, "incorrect_punctuation", location,
                  text[context_start:context_end],
                  "Period immediately after opening parenthesis",
                  severity="medium")

    # Comma at very start of text
    stripped = text.strip()
    if stripped and stripped[0] in '，,':
        add_issue(filepath, "incorrect_punctuation", location,
                  stripped[:30],
                  "Text starts with a comma",
                  severity="medium")

    # Mixed closing punctuation sequence (e.g., 。？ or 。。)
    for m in re.finditer(r'[。！？!?][。！？!?]{1,}', text):
        combo = m.group()
        if len(combo) <= 2 and set(combo) <= {'？', '！', '?', '!'}:
            continue
        context_start = max(0, m.start() - 10)
        context_end = min(len(text), m.end() + 10)
        add_issue(filepath, "excessive_punctuation", location,
                  text[context_start:context_end],
                  f"Mixed closing punctuation sequence: {combo}",
                  severity="low")

    # Multiple spaces after Chinese punctuation
    for m in re.finditer(r'[\u4e00-\u9fff][，。；：、！？]  +[\u4e00-\u9fff]', text):
        context_start = max(0, m.start() - 5)
        context_end = min(len(text), m.end() + 5)
        add_issue(filepath, "incorrect_punctuation", location,
                  text[context_start:context_end],
                  "Multiple spaces after Chinese punctuation",
                  severity="low")

    # Repeated enumeration commas
    for m in re.finditer(r'、{2,}', text):
        context_start = max(0, m.start() - 10)
        context_end = min(len(text), m.end() + 10)
        add_issue(filepath, "excessive_punctuation", location,
                  text[context_start:context_end],
                  "Multiple consecutive enumeration commas (、)",
                  severity="medium")


# ── Check 4: Truncated text ──────────────────────────────────────────────
def check_truncated(text, filepath, location):
    """Check if text appears to be cut off mid-sentence."""
    if not text or len(text) < 5:
        return

    stripped = text.strip()
    if not stripped:
        return

    last_char = stripped[-1]

    # Text ending with connecting particles that strongly suggest continuation
    if len(stripped) > 20:
        # Only flag the strongest indicators of truncation
        strong_connectors = re.search(r'[而與及但且將被把讓向從]$', stripped)
        if strong_connectors:
            if not re.match(r'^[\u4e00-\u9fff]{1,6}$', stripped):
                add_issue(filepath, "truncated_text", location,
                          stripped[-50:],
                          f"Text likely truncated - ends with connecting word '{last_char}'",
                          severity="medium")

        # "的" at end is weaker signal - only flag for longer texts
        if stripped.endswith('的') and len(stripped) > 30:
            # Check if it looks like "...的" is really trailing
            if not stripped.endswith(('目的', '有的', '是的', '對的', '好的')):
                add_issue(filepath, "truncated_text", location,
                          stripped[-50:],
                          "Text may be truncated - ends with particle '的'",
                          severity="low")

        # "為" at end - common legitimate ending (e.g., "行為", "認為")
        if stripped.endswith('為') and len(stripped) > 20:
            # Check if it's a standalone 為 or part of a word
            if len(stripped) >= 2:
                prev_char = stripped[-2]
                # Common legitimate endings with 為
                legit_endings = ['行為', '認為', '作為', '成為', '因為', '以為',
                                 '所為', '人為', '稱為', '視為', '定為']
                if not any(stripped.endswith(e) for e in legit_endings):
                    add_issue(filepath, "truncated_text", location,
                              stripped[-50:],
                              "Text may be truncated - ends with '為' (not a common word ending)",
                              severity="low")

        # "使" at end - could be "行使", "使" as verb
        if stripped.endswith('使') and len(stripped) > 20:
            legit_use = ['行使', '驅使', '促使', '大使', '即使']
            if not any(stripped.endswith(e) for e in legit_use):
                add_issue(filepath, "truncated_text", location,
                          stripped[-50:],
                          "Text may be truncated - ends with '使'",
                          severity="low")

    # Text ending with opening bracket/parenthesis
    if last_char in '（(「『【《〈':
        add_issue(filepath, "truncated_text", location,
                  stripped[-30:],
                  f"Text ends with opening bracket '{last_char}'",
                  severity="high")

    # Unmatched parentheses/brackets suggesting truncation
    for open_ch, close_ch in [('（', '）'), ('(', ')'), ('「', '」'),
                                ('『', '』'), ('【', '】'), ('《', '》')]:
        opens = stripped.count(open_ch)
        closes = stripped.count(close_ch)
        if opens > closes and opens - closes >= 1:
            last_open = stripped.rfind(open_ch)
            last_close = stripped.rfind(close_ch)
            if last_open > last_close:
                add_issue(filepath, "truncated_text", location,
                          stripped[max(0, last_open-15):],
                          f"Unclosed bracket '{open_ch}' - text may be truncated",
                          severity="medium")
                break

    # Text ending mid-ordinal
    if re.search(r'第\d+$', stripped) and len(stripped) > 8:
        add_issue(filepath, "truncated_text", location,
                  stripped[-30:],
                  "Text appears cut off after ordinal number prefix '第'",
                  severity="high")


# ── Check 5: Circled numbers ─────────────────────────────────────────────
def check_circled_numbers(text, filepath, location):
    """Find circled numbers (①②③ etc.) in text."""
    if not text:
        return

    circled_nums = re.finditer(r'[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]', text)
    for m in circled_nums:
        context_start = max(0, m.start() - 15)
        context_end = min(len(text), m.end() + 15)
        context = text[context_start:context_end]
        char = m.group()

        circled_map = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳'
        num_val = circled_map.index(char) + 1

        # Determine if this is in notes (lower severity) or question content (higher)
        sev = "low" if "notes" in location else "medium"
        add_issue(filepath, "circled_number", location, context,
                  f"Circled number {char} (={num_val}) found",
                  severity=sev)


# ── Check 6: "座號" and exam layout artifacts ─────────────────────────────
def check_layout_artifacts(text, filepath, location):
    """Find exam page layout artifacts like 座號, headers, footers."""
    if not text:
        return

    # "座號" - seat number
    if '座號' in text:
        idx = text.index('座號')
        context = text[max(0, idx-15):min(len(text), idx+20)]
        add_issue(filepath, "layout_artifact_座號", location, context,
                  "'座號' (seat number) found in text field",
                  severity="high")

    # Layout artifacts to detect
    layout_patterns = [
        (r'准考證號碼', "Exam admission ticket number", "high"),
        (r'全.{0,2}頁', "Page count marker", "medium"),
        (r'第\s*\d+\s*頁', "Page number", "medium"),
        (r'背面尚有試題', "Layout: more questions on back", "high"),
        (r'背面還有試題', "Layout: more questions on back", "high"),
        (r'請翻面繼續作答', "Layout: continue on next page", "high"),
        (r'請接[背次]面', "Layout: continue on back", "high"),
        (r'以下空白', "Layout: blank space below", "medium"),
        (r'以上空白', "Layout: blank space above", "medium"),
    ]

    # Patterns only flagged in question/option content, not in notes
    question_only_patterns = [
        (r'代號：?\s*\d{3,}', "Exam code in question text", "high"),
    ]

    for pattern, desc, sev in layout_patterns:
        for m in re.finditer(pattern, text):
            matched = m.group()
            context_start = max(0, m.start() - 15)
            context_end = min(len(text), m.end() + 15)
            context = text[context_start:context_end]
            add_issue(filepath, "layout_artifact", location, context,
                      f"Layout artifact: {desc}", severity=sev)

    # Only in question stems and options
    if 'question' in location.lower() or 'option' in location.lower():
        for pattern, desc, sev in question_only_patterns:
            for m in re.finditer(pattern, text):
                context_start = max(0, m.start() - 15)
                context_end = min(len(text), m.end() + 15)
                context = text[context_start:context_end]
                add_issue(filepath, "layout_artifact", location, context,
                          f"Layout artifact: {desc}", severity=sev)

    # "姓名" only if it appears with 座號 (form field context)
    if '座號' in text and re.search(r'姓\s*名', text):
        m = re.search(r'姓\s*名', text)
        context_start = max(0, m.start() - 15)
        context_end = min(len(text), m.end() + 15)
        add_issue(filepath, "layout_artifact", location,
                  text[context_start:context_end],
                  "Form field artifact: '姓名' with '座號'",
                  severity="high")


# ── Check 7: Garbage in metadata fields ───────────────────────────────────
def check_metadata(metadata, filepath):
    """Check metadata fields for garbage/invalid content."""
    if not metadata or not isinstance(metadata, dict):
        add_issue(filepath, "metadata_garbage", "metadata", str(metadata)[:100],
                  "Metadata is missing or not a dict", severity="high")
        return

    # Check exam_name
    exam_name = metadata.get('exam_name', '')
    if not exam_name:
        add_issue(filepath, "metadata_missing", "metadata.exam_name", "",
                  "exam_name is empty", severity="medium")
    else:
        check_field_garbage(exam_name, filepath, "metadata.exam_name")

    # Check subject
    subject = metadata.get('subject', '')
    if not subject:
        add_issue(filepath, "metadata_missing", "metadata.subject", "",
                  "subject is empty", severity="medium")
    else:
        check_field_garbage(subject, filepath, "metadata.subject")

    # Check exam_time
    exam_time = metadata.get('exam_time', '')
    if not exam_time:
        add_issue(filepath, "metadata_missing", "metadata.exam_time", "",
                  "exam_time is empty", severity="low")
    else:
        check_field_garbage(exam_time, filepath, "metadata.exam_time")
        if not re.search(r'\d', exam_time):
            add_issue(filepath, "metadata_garbage", "metadata.exam_time",
                      exam_time, "exam_time contains no digits", severity="medium")
        if len(exam_time) > 30:
            add_issue(filepath, "metadata_garbage", "metadata.exam_time",
                      exam_time[:50], "exam_time is suspiciously long", severity="medium")

    # Check level
    level = metadata.get('level', '')
    if level:
        valid_levels = ['一等', '二等', '三等', '四等', '五等', '初等', '高等',
                       '普通', '特等', '佐級', '員級', '薦任', '委任', '簡任']
        if not any(vl in level for vl in valid_levels):
            check_field_garbage(level, filepath, "metadata.level")

    # Check code
    code = metadata.get('code', '')
    if code:
        if not re.match(r'^[A-Z0-9\-]+$', code):
            if not re.search(r'[\u4e00-\u9fff]', code):
                check_field_garbage(code, filepath, "metadata.code")


def check_field_garbage(text, filepath, location):
    """Check a metadata field for garbage content."""
    if not text:
        return

    check_mojibake(text, filepath, location)

    # Excessive special characters
    special_ratio = len(re.findall(r'[^\w\s\u4e00-\u9fff\u3000-\u303f，。、；：「」（）]', text)) / max(len(text), 1)
    if special_ratio > 0.3 and len(text) > 5:
        add_issue(filepath, "metadata_garbage", location, text,
                  f"High ratio of special characters ({special_ratio:.1%})",
                  severity="high")

    # Meaningless long character sequences
    if re.search(r'[a-zA-Z]{10,}', text) and not re.search(r'[a-zA-Z]+\s+[a-zA-Z]+', text):
        add_issue(filepath, "metadata_garbage", location, text,
                  "Long unbroken English character sequence in metadata",
                  severity="high")

    # Numeric garbage
    if re.match(r'^[\d\s\.\-]+$', text) and len(text) > 10:
        add_issue(filepath, "metadata_garbage", location, text,
                  "Metadata appears to be only numbers",
                  severity="medium")


# ── Check for suspicious answer values ────────────────────────────────────
def check_answer(answer, qtype, filepath, location):
    """Check if an answer field has unexpected format."""
    if not answer or not isinstance(answer, str):
        return

    answer = answer.strip()
    if qtype == 'choice':
        if not re.match(r'^[A-Ea-e]$', answer):
            if re.match(r'^[A-E,;、\s]+$', answer):
                return  # Multi-answer format
            if answer == '送分':
                add_issue(filepath, "answer_送分", location, answer,
                          "Answer is '送分' (free points) - verify this is correct",
                          severity="info")
                return
            add_issue(filepath, "suspicious_answer", location, answer,
                      "Choice answer is not a standard option letter",
                      severity="medium")


# ── Main scanning logic ──────────────────────────────────────────────────
def scan_text(text, filepath, location):
    """Run all text checks on a piece of text."""
    if not text or not isinstance(text, str):
        return

    check_random_english_in_chinese(text, filepath, location)
    check_mojibake(text, filepath, location)
    check_punctuation(text, filepath, location)
    check_truncated(text, filepath, location)
    check_circled_numbers(text, filepath, location)
    check_layout_artifacts(text, filepath, location)


def scan_file(filepath):
    """Scan a single JSON file for all text quality issues."""
    global file_count

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        add_issue(filepath, "json_error", "file", str(e),
                  "File is not valid JSON", severity="critical")
        return
    except Exception as e:
        add_issue(filepath, "file_error", "file", str(e),
                  f"Could not read file: {type(e).__name__}", severity="critical")
        return

    file_count += 1

    # Check metadata
    metadata = data.get('metadata', {})
    check_metadata(metadata, filepath)

    # Check notes
    notes = data.get('notes', [])
    if isinstance(notes, list):
        for i, note in enumerate(notes):
            if isinstance(note, str):
                scan_text(note, filepath, f"notes[{i}]")

    # Check questions
    questions = data.get('questions', [])
    if isinstance(questions, list):
        for qi, q in enumerate(questions):
            if not isinstance(q, dict):
                continue

            qnum = q.get('number', qi+1)

            # Check stem
            stem = q.get('stem', '')
            if isinstance(stem, str):
                scan_text(stem, filepath, f"question[{qnum}].stem")
                if not stem.strip():
                    add_issue(filepath, "empty_field", f"question[{qnum}].stem",
                              "", "Question stem is empty", severity="high")

            # Check options
            options = q.get('options', {})
            if isinstance(options, dict):
                for opt_key, opt_val in options.items():
                    if isinstance(opt_val, str):
                        scan_text(opt_val, filepath,
                                  f"question[{qnum}].option_{opt_key}")
                        if not opt_val.strip():
                            add_issue(filepath, "empty_field",
                                      f"question[{qnum}].option_{opt_key}",
                                      "", f"Option {opt_key} is empty",
                                      severity="high")

            # Check answer field
            answer = q.get('answer', '')
            check_answer(answer, q.get('type', ''), filepath, f"question[{qnum}].answer")

            # Check section field
            section = q.get('section', '')
            if isinstance(section, str) and section:
                scan_text(section, filepath, f"question[{qnum}].section")

    # Empty file check
    if not questions:
        add_issue(filepath, "empty_file", "questions", "",
                  "No questions found in file", severity="high")


def main():
    print(f"Starting Chinese text quality scan of {BASE_DIR}")
    print(f"Timestamp: {datetime.now().isoformat()}")

    # Find all exam JSON files (試題.json only, skip metadata/report files)
    json_files = []
    skip_names = {
        'answer_verification_report.json', 'download_summary.json',
        'extraction_stats.json', '失敗清單.json'
    }
    for root, dirs, files in os.walk(BASE_DIR):
        for fname in files:
            if fname.endswith('.json') and fname not in skip_names:
                fpath = os.path.join(root, fname)
                json_files.append(fpath)

    print(f"Found {len(json_files)} JSON files to scan")

    # Scan all files
    for i, fpath in enumerate(sorted(json_files)):
        if (i + 1) % 100 == 0:
            print(f"  Scanned {i+1}/{len(json_files)} files... ({len(issues)} issues so far)")
        scan_file(fpath)

    print(f"\nScan complete. Scanned {file_count} files, found {len(issues)} issues.")

    # Compute severity counts
    severity_counts = Counter()
    for issue in issues:
        severity_counts[issue.get('severity', 'medium')] += 1

    # Build summary
    summary = {
        "scan_info": {
            "agent": "Agent 3 - Chinese Text Quality Scanner",
            "timestamp": datetime.now().isoformat(),
            "base_directory": BASE_DIR,
            "total_files_scanned": file_count,
            "total_files_found": len(json_files),
            "total_issues_found": len(issues),
            "files_with_issues": len(files_with_issues),
            "files_without_issues": file_count - len(files_with_issues),
        },
        "severity_summary": {
            k: v for k, v in sorted(severity_counts.items(), key=lambda x: -x[1])
        },
        "issue_type_summary": {
            k: v for k, v in sorted(issue_type_counts.items(), key=lambda x: -x[1])
        },
        "issue_type_descriptions": {
            "random_english_in_chinese": "Random/spurious English characters mixed into Chinese text (likely OCR artifacts). Excludes legitimate terms like e化, K他命, X-ray, variable placeholders (X/Y/Z).",
            "mojibake": "Broken characters, garbled text, Private Use Area chars, or encoding issues (亂碼)",
            "excessive_punctuation": "Multiple consecutive identical punctuation marks (commas, periods, etc.)",
            "incorrect_punctuation": "Punctuation in wrong position (e.g., leading comma, period after open paren)",
            "truncated_text": "Text that appears cut off mid-sentence (unclosed brackets, trailing connectors)",
            "circled_number": "Circled numbers (①②③) found in text - common in exam notes, may need standardization",
            "layout_artifact_座號": "'座號' (seat number) found in text content",
            "layout_artifact": "Other exam page layout artifacts (page numbers, continuation instructions, etc.)",
            "metadata_missing": "Required metadata fields that are empty",
            "metadata_garbage": "Metadata fields containing garbage, mojibake, or invalid content",
            "answer_送分": "Answer marked as '送分' (free points/all correct) - informational",
            "suspicious_answer": "Answer field with unexpected format for choice questions",
            "empty_field": "Question stems or options that are empty",
            "empty_file": "Files with no questions at all",
            "json_error": "File is not valid JSON",
            "file_error": "File could not be read",
        },
        "top_30_files_by_issues": [
            {"file": f, "issue_count": c}
            for f, c in per_file_issue_counts.most_common(30)
        ],
        "issues": issues
    }

    # Write report
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\nReport saved to {OUTPUT_FILE}")
    print(f"\n{'='*70}")
    print(f" AGENT 3 - CHINESE TEXT QUALITY SCAN REPORT")
    print(f"{'='*70}")
    print(f"Files scanned:          {file_count}")
    print(f"Files with issues:      {len(files_with_issues)}")
    print(f"Total issues found:     {len(issues)}")
    print(f"\nSeverity breakdown:")
    for sev in ['critical', 'high', 'medium', 'low', 'info']:
        if sev in severity_counts:
            print(f"  {sev:12s} {severity_counts[sev]:6d}")
    print(f"\nIssue type breakdown:")
    for itype, count in sorted(issue_type_counts.items(), key=lambda x: -x[1]):
        print(f"  {itype:40s} {count:6d}")

    # Print sample issues for each type
    print(f"\n{'='*70}")
    print(f" SAMPLE ISSUES (up to 5 per type)")
    print(f"{'='*70}")
    by_type = defaultdict(list)
    for issue in issues:
        by_type[issue['issue_type']].append(issue)

    for itype in sorted(by_type.keys()):
        print(f"\n  [{itype}] ({len(by_type[itype])} total)")
        for sample in by_type[itype][:5]:
            print(f"    File:     {sample['file']}")
            print(f"    Location: {sample['location']}")
            print(f"    Severity: {sample['severity']}")
            print(f"    Snippet:  {sample['text_snippet'][:100]}")
            print(f"    Details:  {sample['details']}")
            print()


if __name__ == '__main__':
    main()
