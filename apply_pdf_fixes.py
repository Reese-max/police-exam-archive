#!/usr/bin/env python3
"""根據從考選部下載的 PDF 補完 F3 答案 + F5 Q54 內容"""
import json
import glob
import os
import shutil
from datetime import datetime

BACKUP_DIR = f'backups/pdf_fix_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
BASE = '考古題庫'


def backup_file(filepath):
    """備份檔案"""
    rel = os.path.relpath(filepath, '.')
    dest = os.path.join(BACKUP_DIR, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(filepath, dest)
    print(f'  備份: {dest}')


def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fix_f3_answers():
    """F3: 補入 108年外國文（英文）Q1-Q40 的答案

    來源: 考選部 108年 答案 PDF + 更正答案 PDF
    - 標準答案: 1-40 題
    - 更正: 第30題 答C或D或CD者均給分 -> 保留 C 或 D（使用更正答案 # 標記，改為 "C或D"）
    """
    print('=== F3: 補入 108年外國文（英文）答案 ===')

    # 從答案 PDF 解析出的標準答案（更正後）
    answers = {
        1: 'B', 2: 'B', 3: 'B', 4: 'C', 5: 'A',
        6: 'D', 7: 'A', 8: 'B', 9: 'D', 10: 'D',
        11: 'A', 12: 'D', 13: 'A', 14: 'C', 15: 'A',
        16: 'B', 17: 'A', 18: 'A', 19: 'B', 20: 'D',
        21: 'A', 22: 'D', 23: 'C', 24: 'A', 25: 'A',
        26: 'B', 27: 'A', 28: 'B', 29: 'C', 30: 'C或D',  # 更正答案: C或D均給分
        31: 'B', 32: 'D', 33: 'A', 34: 'B', 35: 'C',
        36: 'A', 37: 'B', 38: 'C', 39: 'D', 40: 'A',
    }

    f = glob.glob(f'{BASE}/公共安全學系情報組/108年/外國文*英文*/試題.json')
    if not f:
        print('  找不到 108年外國文檔案')
        return 0

    filepath = f[0]
    data = load_json(filepath)
    backup_file(filepath)

    fixed = 0
    for q in data['questions']:
        num = q.get('number')
        if isinstance(num, int) and num in answers:
            old_answer = q.get('answer', '')
            q['answer'] = answers[num]
            if not old_answer:
                fixed += 1
                print(f'  Q{num}: 補入答案 {answers[num]}')
            elif old_answer != answers[num]:
                fixed += 1
                print(f'  Q{num}: 更新答案 {old_answer} -> {answers[num]}')

    save_json(filepath, data)
    print(f'  共補入/更新 {fixed} 題答案')
    print(f'  檔案: {filepath}')
    return fixed


def fix_f5_q54():
    """F5: 補完 106年水上警察 Q54 的完整內容

    來源: 考選部 106年試題 PDF + 答案 PDF
    - Q54 passage: "...In total, this equates to the description of a 54 vessel..."
    - Q54 options: (A) cargo (B) fishing (C) naval (D) recreational
    - Q54 answer: C
    """
    print('\n=== F5: 補完 106年水上警察 Q54 ===')

    f = glob.glob(f'{BASE}/水上警察學系/106年/中華民國憲法與水上*專業英文/試題.json')
    if not f:
        print('  找不到水上警察 106年英文檔案')
        return 0

    filepath = f[0]
    data = load_json(filepath)
    backup_file(filepath)

    fixed = 0
    for q in data['questions']:
        if q.get('number') == 54:
            print(f'  找到 Q54，目前狀態:')
            print(f'    stem: {q.get("stem", "N/A")}')
            print(f'    options: {q.get("options", "N/A")}')
            print(f'    answer: {q.get("answer", "N/A")}')

            # 完整的 passage 文本（與 Q51-Q55 共享）
            full_passage = (
                "Patrol vessels around the world vary in size in direct proportion to the distance "
                "they are expected to operate offshore. High Seas boarding 51 a patrol vessel that "
                "can work comfortably at distances of 200 nautical miles and further from 52 . The "
                "vessel must have the speed, range, maneuverability, communications sophistication, "
                "and 53 technology to accomplish the patrol function efficiently. In total, this "
                "equates to the description of a 54 vessel. The problem is that not all member "
                "states have large vessels and the crews to run them. Still, we should discourage "
                "any thought of chartering a fishing vessel, or transport, or out-of-work research "
                "vessel and attempting to mount a 55 than qualified high seas patrol effort."
            )

            # 更新 Q54 完整內容
            q['stem'] = '請依下文回答第51題至第55題:'
            q['options'] = {
                'A': 'cargo',
                'B': 'fishing',
                'C': 'naval',
                'D': 'recreational'
            }
            q['answer'] = 'C'
            q['passage'] = full_passage

            # 移除 _todo 標記
            if '_todo' in q:
                del q['_todo']

            fixed = 1
            print(f'  已更新 Q54:')
            print(f'    stem: {q["stem"]}')
            print(f'    options: {q["options"]}')
            print(f'    answer: {q["answer"]}')
            break

    if fixed == 0:
        print('  Q54 未找到')

    # 同時更新 Q51-Q53, Q55 的 passage（確保完整一致）
    full_passage = (
        "Patrol vessels around the world vary in size in direct proportion to the distance "
        "they are expected to operate offshore. High Seas boarding 51 a patrol vessel that "
        "can work comfortably at distances of 200 nautical miles and further from 52 . The "
        "vessel must have the speed, range, maneuverability, communications sophistication, "
        "and 53 technology to accomplish the patrol function efficiently. In total, this "
        "equates to the description of a 54 vessel. The problem is that not all member "
        "states have large vessels and the crews to run them. Still, we should discourage "
        "any thought of chartering a fishing vessel, or transport, or out-of-work research "
        "vessel and attempting to mount a 55 than qualified high seas patrol effort."
    )
    for q in data['questions']:
        if isinstance(q.get('number'), int) and q['number'] in [51, 52, 53, 55]:
            if q.get('passage') != full_passage:
                q['passage'] = full_passage
                print(f'  Q{q["number"]}: 更新 passage 為完整文本')

    save_json(filepath, data)
    print(f'  檔案: {filepath}')
    return fixed


if __name__ == '__main__':
    os.makedirs(BACKUP_DIR, exist_ok=True)
    print(f'備份目錄: {BACKUP_DIR}')

    f3_count = fix_f3_answers()
    f5_count = fix_f5_q54()

    print('\n' + '=' * 50)
    print('修復摘要:')
    print(f'  F3: 補入 {f3_count} 題答案')
    print(f'  F5: 補完 {f5_count} 題 Q54 內容')
    print('=' * 50)
