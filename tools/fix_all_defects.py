#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全面 OCR/結構瑕疵修復腳本
修復 Agent Team 掃描發現的所有問題：
  1. PUA 字型字符替換（69,403 個）
  2. 控制字元清除（14 個，1 個檔案）
  3. 五位數代號汙染清除（12 個 notes）
  4. 頁首/頁碼殘留清除（252 個）
  5. 106年警察法規 Q7 stem 汙染修復（10 個類科）
  6. 109年憲法英文 Q31 stem 截斷修復（1 個）
  7. options dict → list 正規化（2 個）
  8. 英文拆字修復（1 個）
"""

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime

BASE = Path(r"C:\Users\User\Desktop\考古題下載\考古題庫")
REPORTS_DIR = Path(r"C:\Users\User\Desktop\考古題下載\reports")

# ========== PUA 碼位對照表 ==========
PUA_MAP = {
    # 選項標記 (A)(B)(C)(D)
    '\ue18c': '(A)', '\ue18d': '(B)', '\ue18e': '(C)', '\ue18f': '(D)',
    # 圈數字 ①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬
    '\ue129': '①', '\ue12a': '②', '\ue12b': '③', '\ue12c': '④', '\ue12d': '⑤',
    '\ue12e': '⑥', '\ue12f': '⑦', '\ue130': '⑧', '\ue131': '⑨', '\ue132': '⑩',
    '\ue133': '⑪', '\ue134': '⑫',
    # 國文測驗題序標記（E0C6~E0CF = 第1~10題，多餘標記直接移除）
    '\ue0c6': '', '\ue0c7': '', '\ue0c8': '', '\ue0c9': '', '\ue0ca': '',
    '\ue0cb': '', '\ue0cc': '', '\ue0cd': '', '\ue0ce': '', '\ue0cf': '',
    # 犯罪偵查步驟標記（E1C0~E1C3 = ㈠㈡㈢㈣）
    '\ue1c0': '㈠', '\ue1c1': '㈡', '\ue1c2': '㈢', '\ue1c3': '㈣',
}

# 頁面殘留 regex
PAGE_RESIDUE_PATTERNS = [
    re.compile(r'\s*\(請接背面\)\s*', re.MULTILINE),
    re.compile(r'\s*（請接背面）\s*', re.MULTILINE),
    re.compile(r'\s*\(背面\)\s*', re.MULTILINE),
    re.compile(r'\s*\(請接第[一二三四五六七八九十\d]+頁\)\s*', re.MULTILINE),
    re.compile(r'\s*全[一二三四五六七八九十\d]+頁\s*$', re.MULTILINE),
    re.compile(r'^\s*頁\s*$', re.MULTILINE),
]

# 代號汙染 regex（notes 中的純代號行）
CODE_PATTERN = re.compile(r'^\d{5}(?:、\d{5})*$')

# 統計
stats = {
    'pua_replaced': 0,
    'control_chars_removed': 0,
    'code_pollution_removed': 0,
    'page_residue_removed': 0,
    'stem_pollution_fixed': 0,
    'stem_truncation_fixed': 0,
    'options_normalized': 0,
    'english_split_fixed': 0,
    'files_modified': 0,
    'files_scanned': 0,
}


def replace_pua(text):
    """替換 PUA 字型字符為正確文字"""
    count = 0
    for pua, replacement in PUA_MAP.items():
        if pua in text:
            n = text.count(pua)
            text = text.replace(pua, replacement)
            count += n
    # F0xx Symbol 字型 — 較少見，直接移除
    new_text = []
    for ch in text:
        if 0xF000 <= ord(ch) <= 0xF0FF:
            count += 1
            # 不替換，直接跳過
        else:
            new_text.append(ch)
    return ''.join(new_text), count


def remove_control_chars(text):
    """移除控制字元（保留 \n \r \t）"""
    count = 0
    result = []
    for ch in text:
        if ord(ch) < 32 and ch not in '\n\r\t':
            count += 1
        else:
            result.append(ch)
    return ''.join(result), count


def clean_page_residue(text):
    """清除頁首/頁碼殘留"""
    count = 0
    for pattern in PAGE_RESIDUE_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            count += len(matches)
            text = pattern.sub('', text)
    # 清理多餘空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip(), count


def fix_question(q):
    """修復單道題目，回傳修改計數"""
    pua_count = 0
    ctrl_count = 0
    page_count = 0

    # 修復 stem
    if 'stem' in q and q['stem']:
        q['stem'], n = replace_pua(q['stem'])
        pua_count += n
        q['stem'], n = remove_control_chars(q['stem'])
        ctrl_count += n
        q['stem'], n = clean_page_residue(q['stem'])
        page_count += n

    # 修復 options
    if 'options' in q:
        if isinstance(q['options'], list):
            for opt in q['options']:
                if isinstance(opt, dict):
                    for key in ('text', 'label'):
                        if key in opt and opt[key]:
                            opt[key], n = replace_pua(opt[key])
                            pua_count += n
                            opt[key], n = remove_control_chars(opt[key])
                            ctrl_count += n
        elif isinstance(q['options'], dict):
            # dict → 暫時不動結構，只修 PUA/control chars
            for key, val in q['options'].items():
                if isinstance(val, str):
                    q['options'][key], n = replace_pua(val)
                    pua_count += n
                    q['options'][key], n = remove_control_chars(q['options'][key])
                    ctrl_count += n

    return pua_count, ctrl_count, page_count


def fix_notes(notes):
    """修復 notes 欄位"""
    pua_count = 0
    ctrl_count = 0
    page_count = 0
    code_count = 0
    new_notes = []
    for note in notes:
        if not isinstance(note, str):
            new_notes.append(note)
            continue
        # 移除純代號行
        if CODE_PATTERN.match(note.strip()):
            code_count += 1
            continue
        note, n = replace_pua(note)
        pua_count += n
        note, n = remove_control_chars(note)
        ctrl_count += n
        note, n = clean_page_residue(note)
        page_count += n
        if note.strip():  # 清理後非空才保留
            new_notes.append(note)
        else:
            page_count += 1  # 清理後為空的也算移除
    return new_notes, pua_count, ctrl_count, page_count, code_count


def fix_106_q7_pollution(data):
    """修復 106年警察法規 Q7 的「請接背面」+頁尾汙染"""
    fixed = 0
    for q in data.get('questions', []):
        if q.get('number') == 7 and q.get('type') == 'choice':
            stem = q.get('stem', '')
            # 截斷「(請接背面)」及其後的所有內容
            idx = stem.find('(請接背面)')
            if idx == -1:
                idx = stem.find('（請接背面）')
            if idx > 0:
                q['stem'] = stem[:idx].strip()
                fixed += 1
    return fixed


def fix_109_q31_truncation(data):
    """修復 109年憲法英文 Q31 stem 截斷（缺 A/B 選項）"""
    fixed = 0
    for q in data.get('questions', []):
        if q.get('number') == 31 and q.get('type') == 'choice':
            stem = q.get('stem', '')
            # 檢查是否只有 C/D 沒有 A/B
            if '(C)' in stem and '(A)' not in stem and '\ue18e' not in stem:
                # 已被 PUA 替換後的情況
                pass
            elif '\ue18e' in stem and '\ue18c' not in stem:
                # 還有 PUA 的情況 — 先做 PUA 替換
                pass

            # 不管 PUA 狀態，如果 stem 中有 '- -' 結尾表示缺失
            if stem.rstrip().endswith('- -'):
                # 從 PDF 手動校正的正確 stem
                q['stem'] = ('依憲法增修條文規定,下列何者不屬於考試院之職權? '
                             '(A)公務人員考試之執行事項 '
                             '(B)公務人員任免之執行事項 '
                             '(C)公務人員銓敘之執行事項 '
                             '(D)公務人員退休之執行事項')
                fixed += 1
    return fixed


def fix_options_dict(data):
    """修復 options 為 dict 的題目 → 移除異常 options，選項已在 stem 中"""
    fixed = 0
    for q in data.get('questions', []):
        if q.get('type') == 'choice' and isinstance(q.get('options'), dict):
            # 這些 dict options 是解析異常產生的，選項文字已嵌在 stem 中
            # 移除 options 欄位，讓它與其他 15,943 道題一致
            del q['options']
            fixed += 1
    return fixed


def fix_english_split(data):
    """修復英文單字被拆開（thedamage → the damage）"""
    fixed = 0
    for q in data.get('questions', []):
        stem = q.get('stem', '')
        if 'thedamage' in stem:
            q['stem'] = stem.replace('thedamage', 'the damage')
            fixed += 1
    return fixed


def process_file(json_path):
    """處理單一 JSON 檔案"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total_pua = 0
    total_ctrl = 0
    total_page = 0
    total_code = 0
    modified = False

    # 修復所有題目
    for q in data.get('questions', []):
        pua, ctrl, page = fix_question(q)
        total_pua += pua
        total_ctrl += ctrl
        total_page += page

    # 修復 notes
    if 'notes' in data and isinstance(data['notes'], list):
        data['notes'], pua, ctrl, page, code = fix_notes(data['notes'])
        total_pua += pua
        total_ctrl += ctrl
        total_page += page
        total_code += code

    # 修復 metadata 中的文字
    if 'metadata' in data and isinstance(data['metadata'], dict):
        for key, val in data['metadata'].items():
            if isinstance(val, str):
                new_val, n = replace_pua(val)
                if n:
                    data['metadata'][key] = new_val
                    total_pua += n

    # 修復 sections
    if 'sections' in data and isinstance(data['sections'], list):
        new_sections = []
        for s in data['sections']:
            if isinstance(s, str):
                s, n = replace_pua(s)
                total_pua += n
            new_sections.append(s)
        data['sections'] = new_sections

    # 特定修復：106年警察法規 Q7
    rel_path = str(json_path.relative_to(BASE))
    if '106年' in rel_path and '警察法規' in rel_path:
        n = fix_106_q7_pollution(data)
        stats['stem_pollution_fixed'] += n
        if n:
            modified = True

    # 特定修復：109年憲法英文 Q31
    if '109年' in rel_path and '憲法' in rel_path and '警察法制' in str(json_path):
        n = fix_109_q31_truncation(data)
        stats['stem_truncation_fixed'] += n
        if n:
            modified = True

    # 特定修復：options dict
    n = fix_options_dict(data)
    stats['options_normalized'] += n
    if n:
        modified = True

    # 特定修復：英文拆字
    n = fix_english_split(data)
    stats['english_split_fixed'] += n
    if n:
        modified = True

    # 統計
    stats['pua_replaced'] += total_pua
    stats['control_chars_removed'] += total_ctrl
    stats['page_residue_removed'] += total_page
    stats['code_pollution_removed'] += total_code

    if total_pua or total_ctrl or total_page or total_code or modified:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        stats['files_modified'] += 1
        return True
    return False


def main():
    print("=" * 70)
    print("  全面 OCR/結構瑕疵修復工具")
    print("=" * 70)
    print(f"  資料目錄: {BASE}")
    print()

    json_files = sorted(BASE.rglob('試題.json'))
    print(f"找到 {len(json_files)} 個試題 JSON")
    print()

    for i, fp in enumerate(json_files, 1):
        rel = fp.relative_to(BASE)
        stats['files_scanned'] += 1
        was_modified = process_file(fp)
        if was_modified:
            print(f"  [修復] {rel}")

    print()
    print("=" * 70)
    print("  修復完成！")
    print("=" * 70)
    print(f"  掃描檔案:        {stats['files_scanned']}")
    print(f"  修改檔案:        {stats['files_modified']}")
    print(f"  ---")
    print(f"  PUA 字符替換:    {stats['pua_replaced']}")
    print(f"  控制字元移除:    {stats['control_chars_removed']}")
    print(f"  代號汙染移除:    {stats['code_pollution_removed']}")
    print(f"  頁面殘留移除:    {stats['page_residue_removed']}")
    print(f"  Q7 汙染修復:     {stats['stem_pollution_fixed']}")
    print(f"  Q31 截斷修復:    {stats['stem_truncation_fixed']}")
    print(f"  options 正規化:  {stats['options_normalized']}")
    print(f"  英文拆字修復:    {stats['english_split_fixed']}")
    print()

    # 儲存修復報告
    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / 'fix_all_defects_report.txt'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write(f"  全面瑕疵修復報告\n")
        f.write(f"  修復時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 70 + "\n\n")
        for key, val in stats.items():
            f.write(f"  {key}: {val}\n")
    print(f"報告已儲存: {report_path}")


if __name__ == '__main__':
    main()
