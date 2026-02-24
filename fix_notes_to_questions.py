# -*- coding: utf-8 -*-
"""
修復 notes 中遺漏的題目

S1: 112年國文 — notes 含 10 題選擇題
S2: 114年國文 — notes 含作文題
S3: 112年韓文 — notes 含 3 題申論題

用法:
  python fix_notes_to_questions.py          # 預覽
  python fix_notes_to_questions.py --apply  # 執行
"""

import json
import re
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent / '考古題庫' / '移民特考'

# 答案（已從答案 PDF 確認）
ANSWERS_112_GUOWEN = {
    1: 'C', 2: 'C', 3: 'A', 4: 'D', 5: 'C',
    6: 'D', 7: 'C', 8: 'D', 9: 'C', 10: 'C'
}


def is_header_line(s):
    """判斷是否為指示性標頭行"""
    return (not s or
            s.startswith('※') or
            s.startswith('本科目') or
            s.startswith('甲、') or
            s.startswith('乙、') or
            s.startswith('作答時') or
            s.startswith('橫式作答') or
            s.startswith('不得於') or
            s.startswith('本試題為') or
            s.startswith('禁止') or
            s.startswith('代號') or
            s.startswith('不必抄題') or
            s.startswith('請以藍') or
            re.match(r'^共\d+題', s) or
            re.match(r'^\d{5}-\d{5}$', s))


def parse_inline_options(line):
    """解析一行內多個選項: (A)text (B)text"""
    opts = {}
    # 匹配 (A)text (B)text 格式
    pattern = r'\(([A-D])\)\s*([^(]*?)(?=\s*\([A-D]\)|$)'
    for m in re.finditer(pattern, line):
        opts[m.group(1)] = m.group(2).strip()
    return opts


def parse_112_guowen_choice(notes):
    """針對 112年國文 notes 解析 10 題選擇題"""
    questions = []
    q_num = 0
    i = 0

    while i < len(notes):
        line = notes[i].strip()

        # 跳過標頭行和代號行
        if is_header_line(line):
            i += 1
            continue

        # 跳過純選項行（已處理的）
        if re.match(r'^\([A-D]\)', line) and not questions:
            i += 1
            continue

        # 嘗試偵測題幹開頭
        # 題幹特徵: 不以 (A-D) 開頭的實質文字
        if re.match(r'^\([A-D]\)', line):
            i += 1
            continue

        # 收集題幹
        stem_lines = [line]
        i += 1

        # 繼續收集到選項出現
        while i < len(notes):
            nxt = notes[i].strip()
            if is_header_line(nxt):
                i += 1
                continue
            if re.match(r'^\([A-D]\)', nxt):
                break
            # 含內嵌選項的行也算選項開始
            if '(A)' in nxt and '(B)' in nxt:
                break
            stem_lines.append(nxt)
            i += 1

        # 收集選項
        options = {}
        current_label = None
        current_text = []

        while i < len(notes):
            nxt = notes[i].strip()
            if is_header_line(nxt):
                i += 1
                continue

            # 一行兩個選項: (A)xx (B)yy
            if re.match(r'^\([A-D]\).*\([A-D]\)', nxt):
                # 先保存上一個
                if current_label:
                    options[current_label] = ' '.join(current_text).strip()
                    current_label = None
                    current_text = []
                inline = parse_inline_options(nxt)
                options.update(inline)
                i += 1
                continue

            # 單個選項開頭
            opt_m = re.match(r'^\(([A-D])\)\s*(.*)', nxt)
            if opt_m:
                if current_label:
                    options[current_label] = ' '.join(current_text).strip()
                current_label = opt_m.group(1)
                current_text = [opt_m.group(2)]
                i += 1
                continue

            # 選項續行
            if current_label:
                # 判斷是否為新題幹（D 之後的長文字）
                if current_label == 'D' and len(nxt) > 15:
                    # 可能是新題幹，停止
                    break
                current_text.append(nxt)
                i += 1
                continue

            # 既不是選項也不是選項續行 → 退出
            break

        if current_label:
            options[current_label] = ' '.join(current_text).strip()

        # 組裝題目
        if len(options) >= 2:
            q_num += 1
            stem = ' '.join(stem_lines).strip()

            if stem.startswith('承上題'):
                stem = stem

            questions.append({
                'number': q_num,
                'type': 'choice',
                'stem': stem,
                'options': options,
            })

            # 套用答案
            if q_num in ANSWERS_112_GUOWEN:
                questions[-1]['answer'] = ANSWERS_112_GUOWEN[q_num]

    return questions


def fix_112_guowen(apply=False):
    """S1: 112年國文"""
    fp = BASE / '112年' / '[三等] 國文(作文與測驗)' / '試題.json'
    if not fp.exists():
        print(f"  找不到: {fp}")
        return 0

    with open(fp, 'r', encoding='utf-8') as f:
        data = json.load(f)

    notes = data.get('notes', [])
    if not isinstance(notes, list) or len(notes) < 20:
        print(f"  notes 格式不符")
        return 0

    choice_qs = parse_112_guowen_choice(notes)
    print(f"  解析出 {len(choice_qs)} 題選擇題")

    for q in choice_qs:
        opts = len(q.get('options', {}))
        ans = q.get('answer', '?')
        print(f"    Q{q['number']}: {opts}選項 ans={ans} | {q['stem'][:60]}")

    if apply and choice_qs:
        backup = fp.with_suffix('.json.bak_notes')
        if not backup.exists():
            shutil.copy2(fp, backup)

        data['questions'].extend(choice_qs)
        data['total_questions'] = len(data['questions'])
        data['notes'] = [n for n in notes if is_header_line(n.strip()) and n.strip()]

        with open(fp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return len(choice_qs)


def fix_114_guowen(apply=False):
    """S2: 114年國文"""
    fp = BASE / '114年' / '[三等] 國文(作文與測驗)' / '試題.json'
    if not fp.exists():
        print(f"  找不到: {fp}")
        return 0

    with open(fp, 'r', encoding='utf-8') as f:
        data = json.load(f)

    notes = data.get('notes', [])
    if not isinstance(notes, list):
        print(f"  notes 格式不符")
        return 0

    # 找作文題: 「木桶原理」到結尾提示
    essay_lines = []
    capturing = False
    for line in notes:
        s = line.strip()
        if '前人曾提出' in s or '木桶原理' in s:
            capturing = True
        if capturing:
            if re.match(r'^\d{5}-\d{5}$', s):
                continue
            if s.startswith('乙、') or s.startswith('代號') or s.startswith('本試題為'):
                break
            if s:
                essay_lines.append(s)

    if not essay_lines:
        print(f"  找不到作文題")
        return 0

    essay_stem = '作文:(80 分)\n' + '\n'.join(essay_lines)
    print(f"  找到作文題 ({len(essay_stem)} chars)")
    print(f"    preview: {essay_stem[:120]}...")

    if apply:
        backup = fp.with_suffix('.json.bak_notes')
        if not backup.exists():
            shutil.copy2(fp, backup)

        essay_q = {
            'number': '一',
            'type': 'essay',
            'stem': essay_stem,
        }
        data['questions'].insert(0, essay_q)
        data['total_questions'] = len(data['questions'])
        data['notes'] = [n for n in notes if is_header_line(n.strip()) and n.strip()]

        with open(fp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return 1


def fix_112_korean(apply=False):
    """S3: 112年韓文"""
    fp = BASE / '112年' / '[三等] 外國文(韓文兼試移民專業英文)' / '試題.json'
    if not fp.exists():
        print(f"  找不到: {fp}")
        return 0

    with open(fp, 'r', encoding='utf-8') as f:
        data = json.load(f)

    notes = data.get('notes', [])
    if not isinstance(notes, list):
        print(f"  notes 格式不符")
        return 0

    # 找 3 題申論題
    essay_questions = []
    i = 0
    # 題目標記
    markers = [
        ('請將下列韓文翻譯成中文', '一'),
        ('請將下列中文翻譯成韓文', '二'),
        ('作文：', '三'),
    ]

    for marker_text, q_num in markers:
        # 找到起始位置
        start_idx = None
        for idx, line in enumerate(notes):
            if marker_text in line.strip():
                start_idx = idx
                break

        if start_idx is None:
            continue

        # 收集到下一個標記或結束
        stem_lines = []
        for j in range(start_idx, len(notes)):
            s = notes[j].strip()
            # 停止條件
            if j > start_idx and any(m[0] in s for m in markers if m[0] != marker_text):
                break
            if s.startswith('本試題為') or (s.startswith('共') and '題' in s):
                break
            if s:
                stem_lines.append(s)

        if stem_lines:
            essay_questions.append({
                'number': q_num,
                'type': 'essay',
                'stem': '\n'.join(stem_lines),
            })

    print(f"  解析出 {len(essay_questions)} 題申論題")
    for q in essay_questions:
        print(f"    #{q['number']}: {q['stem'][:80]}...")

    if apply and essay_questions:
        backup = fp.with_suffix('.json.bak_notes')
        if not backup.exists():
            shutil.copy2(fp, backup)

        data['questions'] = essay_questions + data['questions']
        data['total_questions'] = len(data['questions'])
        data['notes'] = [n for n in notes if
                        n.strip().startswith('※') or
                        n.strip().startswith('禁止')]

        with open(fp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return len(essay_questions)


def main():
    apply = '--apply' in sys.argv

    print(f"{'=' * 60}")
    print(f"修復 notes 中遺漏的題目")
    print(f"模式: {'實際修改' if apply else '預覽'}")
    print(f"{'=' * 60}\n")

    total = 0

    print("[S1] 112年國文 — 選擇題")
    total += fix_112_guowen(apply)

    print(f"\n[S2] 114年國文 — 作文題")
    total += fix_114_guowen(apply)

    print(f"\n[S3] 112年韓文 — 申論題")
    total += fix_112_korean(apply)

    print(f"\n{'=' * 60}")
    print(f"共修復 {total} 題")
    if not apply and total > 0:
        print(f"加 --apply 執行修改")


if __name__ == '__main__':
    main()
