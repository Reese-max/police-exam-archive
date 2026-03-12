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

if __name__ == '__main__':
    os.makedirs(BACKUP_DIR, exist_ok=True)
    print(f'備份目錄: {BACKUP_DIR}')
    fix_f6_metadata_leak()
    fix_f4_empty_stems()
