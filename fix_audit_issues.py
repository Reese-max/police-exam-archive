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

if __name__ == '__main__':
    os.makedirs(BACKUP_DIR, exist_ok=True)
    print(f'備份目錄: {BACKUP_DIR}')
    fix_f6_metadata_leak()
    fix_f4_empty_stems()
    fix_f1_copy_chinese_choice()
    fix_f2_copy_112_113_choice()
