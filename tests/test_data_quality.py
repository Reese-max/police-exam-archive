#!/usr/bin/env python3
"""考古題資料庫品質驗證測試套件

涵蓋結構完整性、語意品質、文字品質三大面向。
用 pytest 執行: python -m pytest tests/ -v
"""

import json
import glob
import re
import os
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "考古題庫"

# ── 載入所有非重複 JSON 檔案 ──

def load_all_files():
    """載入所有非重複的試題 JSON"""
    files = []
    for fp in glob.glob(str(DATA_DIR / "**" / "試題.json"), recursive=True):
        with open(fp, 'r', encoding='utf-8') as f:
            d = json.load(f)
        if d.get('metadata', {}).get('_is_duplicate'):
            continue
        files.append((fp, d))
    return files


ALL_FILES = load_all_files()
ALL_QUESTIONS = [(fp, q) for fp, d in ALL_FILES for q in d.get('questions', [])]
CHOICE_QUESTIONS = [(fp, q) for fp, q in ALL_QUESTIONS if q.get('type') == 'choice']
ESSAY_QUESTIONS = [(fp, q) for fp, q in ALL_QUESTIONS if q.get('type') == 'essay']


# ══════════════════════════════════════════════
#  結構完整性測試
# ══════════════════════════════════════════════

class TestDataScale:
    """資料規模基本檢查"""

    def test_file_count(self):
        assert len(ALL_FILES) == 2000, f"預期 2000 個非重複檔案，實際 {len(ALL_FILES)}"

    def test_total_questions(self):
        assert len(ALL_QUESTIONS) == 41811, f"預期 41811 題，實際 {len(ALL_QUESTIONS)}"

    def test_choice_count(self):
        assert len(CHOICE_QUESTIONS) == 36210, f"預期 36210 選擇題，實際 {len(CHOICE_QUESTIONS)}"

    def test_essay_count(self):
        assert len(ESSAY_QUESTIONS) == 5601, f"預期 5601 申論題，實際 {len(ESSAY_QUESTIONS)}"


class TestStructuralIntegrity:
    """結構完整性"""

    def test_all_choice_have_4_options(self):
        """每個選擇題都有 A/B/C/D 四個選項"""
        missing = []
        for fp, q in CHOICE_QUESTIONS:
            opts = q.get('options', {})
            if not (len(opts) == 4 and all(k in opts for k in 'ABCD')):
                missing.append((fp, q.get('number')))
        assert len(missing) == 0, f"{len(missing)} 題缺選項: {missing[:5]}"

    def test_all_choice_have_valid_answer(self):
        """每個選擇題都有合法答案"""
        valid_answers = {'A', 'B', 'C', 'D', '送分', 'C或D'}
        invalid = []
        for fp, q in CHOICE_QUESTIONS:
            ans = q.get('answer', '')
            if ans not in valid_answers:
                invalid.append((fp, q.get('number'), ans))
        assert len(invalid) == 0, f"{len(invalid)} 題答案不合法: {invalid[:5]}"

    def test_no_empty_stem_without_passage(self):
        """選擇題不能既無題幹又無段落"""
        empty = []
        for fp, q in CHOICE_QUESTIONS:
            stem = (q.get('stem') or '').strip()
            passage = (q.get('passage') or '').strip()
            if not stem and not passage:
                empty.append((fp, q.get('number')))
        assert len(empty) == 0, f"{len(empty)} 題空題幹+無段落: {empty[:5]}"

    def test_no_missing_answer(self):
        """選擇題不能缺答案"""
        missing = [(fp, q.get('number')) for fp, q in CHOICE_QUESTIONS if not q.get('answer')]
        assert len(missing) == 0, f"{len(missing)} 題缺答案"

    def test_question_numbers_no_gaps(self):
        """同一檔案中選擇題號不能有缺漏"""
        gaps = []
        for fp, d in ALL_FILES:
            nums = sorted(
                q.get('number') for q in d.get('questions', [])
                if q.get('type') == 'choice' and isinstance(q.get('number'), int)
            )
            if nums:
                expected = set(range(nums[0], nums[-1] + 1))
                missing = expected - set(nums)
                if missing:
                    gaps.append((fp, sorted(missing)))
        assert len(gaps) == 0, f"{len(gaps)} 個檔案有題號缺漏: {gaps[:3]}"

    def test_question_numbers_no_duplicates(self):
        """同一檔案中選擇題號不能重複"""
        dups = []
        for fp, d in ALL_FILES:
            nums = [
                q.get('number') for q in d.get('questions', [])
                if q.get('type') == 'choice' and isinstance(q.get('number'), int)
            ]
            seen = set()
            for n in nums:
                if n in seen:
                    dups.append((fp, n))
                seen.add(n)
        assert len(dups) == 0, f"{len(dups)} 個重複題號"


# ══════════════════════════════════════════════
#  文字品質測試
# ══════════════════════════════════════════════

class TestTextQuality:
    """PDF 萃取文字品質"""

    def test_no_pua_characters(self):
        """無 PUA 私用字元殘留"""
        pua_count = 0
        for fp, q in ALL_QUESTIONS:
            for text in _all_text_fields(q):
                pua_count += len(re.findall(r'[\ue000-\uf8ff]', text))
        assert pua_count == 0, f"{pua_count} 個 PUA 字元殘留"

    def test_no_camelcase_concat(self):
        """無英文 camelCase 連字"""
        concat_count = 0
        for fp, q in ALL_QUESTIONS:
            for text in _all_text_fields(q):
                if re.search(r'[a-z]{2,}[A-Z][a-z]{2,}', text):
                    concat_count += 1
        assert concat_count == 0, f"{concat_count} 處 camelCase 連字"

    def test_no_control_characters(self):
        """無控制字元"""
        ctrl_count = 0
        for fp, q in ALL_QUESTIONS:
            for text in _all_text_fields(q):
                ctrl_count += len(re.findall(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', text))
        assert ctrl_count == 0, f"{ctrl_count} 個控制字元"

    def test_no_option_prefix_markers(self):
        """選項值不以 (A)/(B)/(C)/(D) 開頭"""
        prefix_count = 0
        for fp, q in CHOICE_QUESTIONS:
            for v in (q.get('options') or {}).values():
                if re.match(r'^[\(（][A-D][\)）]', str(v).strip()):
                    prefix_count += 1
        assert prefix_count == 0, f"{prefix_count} 個選項含前綴標記"


# ══════════════════════════════════════════════
#  語意品質測試
# ══════════════════════════════════════════════

class TestSemanticQuality:
    """語意品質"""

    def test_no_unmarked_duplicate_options(self):
        """無未標記的重複選項（已知瑕疵需有 _note）"""
        dup_count = 0
        for fp, q in CHOICE_QUESTIONS:
            if q.get('_note'):  # 已知瑕疵，跳過
                continue
            opt_vals = [str(v).strip() for v in (q.get('options') or {}).values()]
            if len(set(opt_vals)) < len(opt_vals):
                dup_count += 1
        assert dup_count == 0, f"{dup_count} 題有未標記的重複選項"

    def test_no_answer_in_stem(self):
        """題幹不包含答案洩露"""
        leak_count = 0
        for fp, q in CHOICE_QUESTIONS:
            stem = q.get('stem') or ''
            if re.search(r'答案[:：]\s*[A-D]', stem):
                leak_count += 1
        assert leak_count == 0, f"{leak_count} 題題幹洩露答案"

    def test_no_metadata_in_stem(self):
        """題幹不包含考試 metadata"""
        meta_count = 0
        for fp, q in ALL_QUESTIONS:
            stem = q.get('stem') or ''
            if re.search(r'乙、測驗|代號[:：]\s*\d{4}', stem):
                meta_count += 1
        assert meta_count == 0, f"{meta_count} 題題幹含 metadata"

    def test_all_files_have_questions(self):
        """每個檔案至少有 1 題"""
        empty = [(fp, d) for fp, d in ALL_FILES if len(d.get('questions', [])) == 0]
        assert len(empty) == 0, f"{len(empty)} 個檔案無題目"


# ── 輔助函式 ──

def _all_text_fields(q):
    """取得一題的所有文字欄位"""
    texts = []
    for field in ('stem', 'passage'):
        v = q.get(field) or ''
        if v:
            texts.append(v)
    for v in (q.get('options') or {}).values():
        texts.append(str(v))
    return texts
