import json
import re
import glob
import os
import copy
import shutil
from datetime import datetime

BACKUP_DIR = f'backups/audit_fix_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
BASE = '考古題庫'

def backup_file(filepath):
    """備份檔案到 BACKUP_DIR，保留目錄結構"""
    rel = os.path.relpath(filepath, '.')
    dest = os.path.join(BACKUP_DIR, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(filepath, dest)

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def fix_f6_metadata_leak():
    """F6: 移除情報組國文 Q二 尾部混入的考試 metadata"""
    pattern = re.compile(r'\s*乙、測驗部分.*$', re.DOTALL)
    fixed = 0
    for f in sorted(glob.glob(f'{BASE}/公共安全學系情報組/*/國文*/試題.json')):
        data = load_json(f)
        modified = False
        for q in data['questions']:
            if q['type'] == 'essay' and '乙、測驗部分' in str(q.get('stem', '')):
                backup_file(f)
                q['stem'] = pattern.sub('', q['stem']).rstrip()
                modified = True
                fixed += 1
        if modified:
            save_json(f, data)
    print(f'F6: 修復 {fixed} 筆 metadata 滲入')
    return fixed

def fix_f4_empty_stems():
    """F4: 對有 passage 但 stem 為空的選擇題，從 passage 提取描述性題幹"""
    prompt_pattern = re.compile(r'(請依下文回答第?\d+題至第?\d+題[:：]?)')

    fixed = 0
    files_fixed = 0
    for f in sorted(glob.glob(f'{BASE}/**/試題.json', recursive=True)):
        data = load_json(f)
        modified = False
        for q in data['questions']:
            if q.get('type') == 'choice' and (not q.get('stem') or not q['stem'].strip()):
                if q.get('passage'):
                    match = prompt_pattern.search(q['passage'])
                    if match:
                        q['stem'] = match.group(1)
                    else:
                        q['stem'] = f'(見文章第 {q["number"]} 題空格)'
                    if not modified:
                        backup_file(f)
                    modified = True
                    fixed += 1
        if modified:
            save_json(f, data)
            files_fixed += 1
    print(f'F4: 修復 {fixed} 題空題幹（{files_fixed} 個檔案）')
    return fixed

def fix_f1_copy_chinese_choice():
    """F1: 從已有選擇題的學系複製到缺失的學系（106-107年國文）"""
    sources = {
        '106': '公共安全學系情報組',
        '107': '公共安全學系情報組',
    }

    fixed_files = 0
    fixed_questions = 0

    for year in ['106', '107']:
        source_files = glob.glob(f'{BASE}/{sources[year]}/{year}年/國文*/試題.json')
        if not source_files:
            print(f'  警告: 找不到 {year}年來源檔案')
            continue
        source_data = load_json(source_files[0])
        source_choices = [q for q in source_data['questions'] if q['type'] == 'choice']
        print(f'  {year}年來源: {len(source_choices)} 題選擇題')

        for f in sorted(glob.glob(f'{BASE}/*/{year}年/國文*/試題.json')):
            data = load_json(f)
            types = [q['type'] for q in data['questions']]
            has_2b = any('2B鉛筆' in n for n in data.get('notes', []))

            if 'choice' not in types and has_2b:
                backup_file(f)
                new_choices = copy.deepcopy(source_choices)
                data['questions'].extend(new_choices)
                if 'sections' in data and data['sections']:
                    if not any('測驗' in str(s) for s in data.get('sections', [])):
                        data['sections'].append('乙、測驗題')
                save_json(f, data)
                fixed_files += 1
                fixed_questions += len(new_choices)

    print(f'F1: 複製選擇題到 {fixed_files} 個檔案（{fixed_questions} 題）')
    return fixed_files

def fix_f2_copy_112_113_choice():
    """F2: 從同年其他學系複製選擇題到 112-113年矯治組"""
    sources = {
        '112': '交通學系交通組',
        '113': '交通學系交通組',
    }

    fixed = 0
    for year in ['112', '113']:
        source_files = glob.glob(f'{BASE}/{sources[year]}/{year}年/國文*/試題.json')
        if not source_files:
            print(f'  警告: 找不到 {year}年來源')
            continue
        source_data = load_json(source_files[0])
        source_choices = [q for q in source_data['questions'] if q['type'] == 'choice']

        target_files = glob.glob(f'{BASE}/犯罪防治*矯治組/{year}年/國文*/試題.json')
        for f in target_files:
            data = load_json(f)
            types = [q['type'] for q in data['questions']]
            has_2b = any('2B鉛筆' in n for n in data.get('notes', []))

            if 'choice' not in types and has_2b:
                backup_file(f)
                data['questions'].extend(copy.deepcopy(source_choices))
                save_json(f, data)
                fixed += 1
                print(f'  修復: {f}')

    print(f'F2: 修復 {fixed} 個檔案（{fixed * 10} 題）')
    return fixed

def fix_f3_english_mistyped():
    """F3: 修正 108年外國文 essay→choice + 嘗試從 stem 解析 options"""
    f = glob.glob(f'{BASE}/公共安全學系情報組/108年/外國文*英文*/試題.json')
    if not f:
        print('F3: 找不到 108年外國文檔案')
        return 0

    filepath = f[0]
    data = load_json(filepath)
    backup_file(filepath)

    option_pattern = re.compile(
        r'[\(（]([A-Da-d])[\)）]\s*(.+?)(?=[\(（][A-Da-d][\)）]|$)',
        re.DOTALL
    )

    fixed = 0
    for q in data['questions']:
        num = q['number']
        # Q1-Q40 (int) should be choice, not essay
        if isinstance(num, int) and 1 <= num <= 40 and q['type'] == 'essay':
            q['type'] = 'choice'

            # 嘗試從 stem 中提取 options
            stem = q.get('stem', '')
            matches = option_pattern.findall(stem)
            if len(matches) >= 4:
                q['options'] = {}
                # 找到第一個選項位置來分離 stem
                for marker in ['(A)', '（A）']:
                    pos = stem.find(marker)
                    if pos > 0:
                        q['stem'] = stem[:pos].strip()
                        break
                for letter, text in matches[:4]:
                    q['options'][letter.upper()] = text.strip()

            fixed += 1

    save_json(filepath, data)
    print(f'F3: 修正 {fixed} 題 essay→choice')
    return fixed

def fix_f5_missing_q54():
    """F5: 補入水上警察 106年 Q54"""
    f = glob.glob(f'{BASE}/水上警察學系/106年/中華民國憲法與水上*專業英文/試題.json')
    if not f:
        print('F5: 找不到水上警察 106年英文檔案')
        return 0

    filepath = f[0]
    data = load_json(filepath)

    nums = [q['number'] for q in data['questions'] if isinstance(q.get('number'), int)]
    if 54 in nums:
        print('F5: Q54 已存在，跳過')
        return 0

    backup_file(filepath)

    q53 = next((q for q in data['questions'] if q.get('number') == 53), None)
    passage = q53.get('passage', '') if q53 else ''

    q54 = {
        'number': 54,
        'type': 'choice',
        'stem': '(見文章第 54 題空格)',
        'section': q53.get('section', '乙、測驗題') if q53 else '乙、測驗題',
        'passage': passage,
        'options': {'A': '[待補]', 'B': '[待補]', 'C': '[待補]', 'D': '[待補]'},
        'answer': '[待補]',
        '_todo': '需從考選部 PDF 補完整內容'
    }

    for i, q in enumerate(data['questions']):
        if q.get('number') == 53:
            data['questions'].insert(i + 1, q54)
            break

    save_json(filepath, data)
    print('F5: 補入 Q54 佔位（需從 PDF 補完整內容）')
    return 1

def fix_extra_embedded_options():
    """額外: 修復選擇題 stem 中內嵌選項但無 options 欄位的問題"""
    option_pattern = re.compile(
        r'[\(（]([A-Da-d])[\)）]\s*(.+?)(?=\s*[\(（][A-Da-d][\)）]|\s*$)',
        re.DOTALL
    )

    fixed = 0
    files_fixed = 0
    for f in sorted(glob.glob(f'{BASE}/**/試題.json', recursive=True)):
        data = load_json(f)
        modified = False
        for q in data['questions']:
            if q.get('type') == 'choice' and not q.get('options'):
                stem = q.get('stem', '')
                matches = option_pattern.findall(stem)
                if len(matches) >= 4:
                    if not modified:
                        backup_file(f)
                    for marker in ['(A)', '（A）']:
                        pos = stem.find(marker)
                        if pos > 0:
                            q['stem'] = stem[:pos].strip()
                            break
                    q['options'] = {letter.upper(): text.strip() for letter, text in matches[:4]}
                    modified = True
                    fixed += 1
        if modified:
            save_json(f, data)
            files_fixed += 1

    print(f'額外: 修復 {fixed} 題內嵌選項（{files_fixed} 個檔案）')
    return fixed

if __name__ == '__main__':
    os.makedirs(BACKUP_DIR, exist_ok=True)
    print(f'備份目錄: {BACKUP_DIR}')
    fix_f6_metadata_leak()
    fix_f4_empty_stems()
    fix_f1_copy_chinese_choice()
    fix_f2_copy_112_113_choice()
    fix_f3_english_mistyped()
    fix_f5_missing_q54()
    fix_extra_embedded_options()
