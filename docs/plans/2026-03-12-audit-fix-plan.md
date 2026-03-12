# 考古題資料品質全面修復 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修復 22,655 題考古題資料中發現的 6 類品質問題（P0 遺失/誤標 + P1 空題幹/metadata 汙染/題號缺漏）

**Architecture:** 寫一個 Python 修復腳本 `fix_audit_issues.py`，按 F6→F4→F1→F2→F3→F5 順序處理。每個修復函式獨立，讀取 JSON → 修改 → 寫回。最後跑驗證腳本確認 0 問題。

**Tech Stack:** Python 3.11, json, re, glob, shutil (備份用)

---

## 前置發現（影響計畫）

- **所有年份均為三等**，國文選擇題（測驗部分）在同年同等級跨學系完全相同
- 106年來源：公共安全學系情報組（有完整 options + answer）
- 107年來源：公共安全學系情報組
- 112年來源：交通學系交通組（情報組的 metadata 有汙染）
- 113年來源：交通學系交通組
- **F2 不需要下載 PDF** — 112-113年其他學系都有正確的選擇題，只有矯治組缺失
- 犯罪防治矯治組（四等對應）的選擇題 stem 內嵌選項但無 `options` 欄位，需一併修復
- 原始 PDF 已不在專案中，F3 和 F5 需從考選部下載

---

### Task 1: 備份所有受影響的 JSON 檔案

**Files:**
- Create: `backups/audit_fix_20260312/` (備份目錄)

**Step 1: 建立備份腳本**

在 `fix_audit_issues.py` 開頭加入備份邏輯：

```python
# fix_audit_issues.py
import json
import re
import glob
import os
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
```

**Step 2: 執行腳本確認備份目錄建立正常**

Run: `cd "C:/Users/User/Desktop/pdf考古題檔案轉換/考古題下載" && python fix_audit_issues.py`
Expected: 腳本無錯誤退出

**Step 3: Commit**

```bash
git add fix_audit_issues.py
git commit -m "feat: 新增審計修復腳本骨架 + 備份功能"
```

---

### Task 2: F6 — 清理 8 筆 Metadata 滲入申論題幹

**Files:**
- Modify: `fix_audit_issues.py`
- Affected: `考古題庫/公共安全學系情報組/{106-113}年/國文*/試題.json` (8 檔)

**Step 1: 加入 F6 修復函式**

```python
def fix_f6_metadata_leak():
    """F6: 移除情報組國文 Q二 尾部混入的考試 metadata"""
    # 匹配 "乙、測驗部分" 開頭到結尾的所有文字
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
```

**Step 2: 在 main 中呼叫並執行**

```python
if __name__ == '__main__':
    os.makedirs(BACKUP_DIR, exist_ok=True)
    print(f'備份目錄: {BACKUP_DIR}')
    fix_f6_metadata_leak()
```

Run: `python fix_audit_issues.py`
Expected: `F6: 修復 8 筆 metadata 滲入`

**Step 3: 驗證修復結果**

```bash
python -c "
import json, glob
for f in sorted(glob.glob('考古題庫/公共安全學系情報組/*/國文*/試題.json')):
    data = json.load(open(f, encoding='utf-8'))
    for q in data['questions']:
        if q['type'] == 'essay' and '乙、測驗部分' in str(q.get('stem', '')):
            print(f'STILL DIRTY: {f}')
            break
    else:
        continue
print('F6 驗證完成')
"
```
Expected: 只印出 `F6 驗證完成`，無 STILL DIRTY

**Step 4: Commit**

```bash
git add fix_audit_issues.py
git commit -m "fix: F6 清理 8 筆情報組國文申論題幹中的考試 metadata"
```

---

### Task 3: F4 — 修復 528 題空題幹

**Files:**
- Modify: `fix_audit_issues.py`
- Affected: 102 個英文科目 JSON 檔案

**Step 1: 分析空題幹的模式**

先了解 passage 中的提示文字格式：

```bash
python -c "
import json, glob
samples = set()
for f in glob.glob('考古題庫/**/試題.json', recursive=True):
    data = json.load(open(f, encoding='utf-8'))
    for q in data['questions']:
        if q.get('type') == 'choice' and not q.get('stem','').strip() and q.get('passage'):
            # 取 passage 前 60 字
            p = q['passage'][:80]
            samples.add(p[:60])
            if len(samples) >= 10:
                break
for s in sorted(samples):
    print(s)
"
```

**Step 2: 加入 F4 修復函式**

```python
def fix_f4_empty_stems():
    """F4: 對有 passage 但 stem 為空的選擇題，從 passage 提取描述性題幹"""
    # passage 開頭通常是 "請依下文回答第X題至第Y題" 之類的提示
    prompt_pattern = re.compile(r'(請依下文回答第?\d+題至第?\d+題[:：]?)')

    fixed = 0
    files_fixed = 0
    for f in sorted(glob.glob(f'{BASE}/**/試題.json', recursive=True)):
        data = load_json(f)
        modified = False
        for q in data['questions']:
            if q.get('type') == 'choice' and (not q.get('stem') or not q['stem'].strip()):
                if q.get('passage'):
                    # 從 passage 提取提示文字作為 stem
                    match = prompt_pattern.search(q['passage'])
                    if match:
                        q['stem'] = match.group(1)
                    else:
                        # 克漏字填空題：題幹就是填入空格
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
```

**Step 3: 執行並驗證**

Run: `python fix_audit_issues.py`
Expected: `F4: 修復 528 題空題幹（102 個檔案）`

驗證：
```bash
python -c "
import json, glob
count = 0
for f in glob.glob('考古題庫/**/試題.json', recursive=True):
    data = json.load(open(f, encoding='utf-8'))
    for q in data['questions']:
        if q.get('type') == 'choice' and (not q.get('stem') or not q['stem'].strip()):
            count += 1
print(f'殘餘空題幹: {count}')
"
```
Expected: `殘餘空題幹: 0`

**Step 4: Commit**

```bash
git add fix_audit_issues.py
git commit -m "fix: F4 修復 528 題英文克漏字空題幹"
```

---

### Task 4: F1 — 複製 106-107年國文選擇題到缺失學系

**Files:**
- Modify: `fix_audit_issues.py`
- Affected: 106年 26 檔 + 107年 28 檔 = 54 檔

**Step 1: 加入 F1 修復函式**

```python
def fix_f1_copy_chinese_choice():
    """F1: 從已有選擇題的學系複製到缺失的學系（106-107年國文）"""
    # 來源檔案（已正確解析的學系）
    sources = {
        '106': '公共安全學系情報組',
        '107': '公共安全學系情報組',
    }

    fixed_files = 0
    fixed_questions = 0

    for year in ['106', '107']:
        # 載入來源選擇題
        source_files = glob.glob(f'{BASE}/{sources[year]}/{year}年/國文*/試題.json')
        if not source_files:
            print(f'  警告: 找不到 {year}年 來源檔案')
            continue
        source_data = load_json(source_files[0])
        source_choices = [q for q in source_data['questions'] if q['type'] == 'choice']
        print(f'  {year}年來源: {len(source_choices)} 題選擇題')

        # 遍歷所有國文檔案
        for f in sorted(glob.glob(f'{BASE}/*/{year}年/國文*/試題.json')):
            data = load_json(f)
            types = [q['type'] for q in data['questions']]
            has_2b = any('2B鉛筆' in n for n in data.get('notes', []))

            if 'choice' not in types and has_2b:
                backup_file(f)
                # 深拷貝選擇題避免引用問題
                import copy
                new_choices = copy.deepcopy(source_choices)
                data['questions'].extend(new_choices)

                # 更新 sections 如果有的話
                if 'sections' in data and data['sections']:
                    if not any('測驗' in str(s) for s in data.get('sections', [])):
                        data['sections'].append('乙、測驗題')

                save_json(f, data)
                fixed_files += 1
                fixed_questions += len(new_choices)

    print(f'F1: 複製選擇題到 {fixed_files} 個檔案（{fixed_questions} 題）')
    return fixed_files
```

**Step 2: 執行並驗證**

Run: `python fix_audit_issues.py`
Expected: `F1: 複製選擇題到 54 個檔案（540 題）`

驗證：
```bash
python -c "
import json, glob
missing = 0
for year in ['106', '107']:
    for f in glob.glob(f'考古題庫/*/{year}年/國文*/試題.json'):
        data = json.load(open(f, encoding='utf-8'))
        types = [q['type'] for q in data['questions']]
        has_2b = any('2B鉛筆' in n for n in data.get('notes', []))
        if 'choice' not in types and has_2b:
            missing += 1
            print(f'STILL MISSING: {f}')
print(f'殘餘缺失: {missing}')
"
```
Expected: `殘餘缺失: 0`

**Step 3: Commit**

```bash
git add fix_audit_issues.py
git commit -m "fix: F1 複製 106-107年國文選擇題到 54 個缺失學系"
```

---

### Task 5: F2 — 複製 112-113年國文選擇題到矯治組

**Files:**
- Modify: `fix_audit_issues.py`
- Affected: `考古題庫/犯罪防治學系矯治組/{112,113}年/國文(作文與測驗)/試題.json` (2 檔)

**Step 1: 加入 F2 修復函式**

```python
def fix_f2_copy_112_113_choice():
    """F2: 從同年其他學系複製選擇題到 112-113年矯治組"""
    # 用交通學系交通組作為來源（乾淨無 metadata 汙染）
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

        # 找矯治組
        target_files = glob.glob(f'{BASE}/犯罪防治學系矯治組/{year}年/國文*/試題.json')
        for f in target_files:
            data = load_json(f)
            types = [q['type'] for q in data['questions']]
            has_2b = any('2B鉛筆' in n for n in data.get('notes', []))

            if 'choice' not in types and has_2b:
                backup_file(f)
                import copy
                data['questions'].extend(copy.deepcopy(source_choices))
                save_json(f, data)
                fixed += 1
                print(f'  修復: {f}')

    print(f'F2: 修復 {fixed} 個檔案（{fixed * 10} 題）')
    return fixed
```

**Step 2: 執行並驗證**

Run: `python fix_audit_issues.py`
Expected: `F2: 修復 2 個檔案（20 題）`

**Step 3: Commit**

```bash
git add fix_audit_issues.py
git commit -m "fix: F2 複製 112-113年選擇題到矯治組"
```

---

### Task 6: F3 — 修正 108年外國文 40 題類型 + 補 options

**Files:**
- Modify: `fix_audit_issues.py`
- Affected: `考古題庫/公共安全學系情報組/108年/外國文（英文）/試題.json`

**注意**: 此任務需要從考選部下載 108年外國文 PDF，解析 Q1-Q40 的 options 和 answer。如果無法下載，至少先修正 type 標記。

**Step 1: 加入 F3 修復函式（type 修正 + options 解析）**

```python
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
        # Q1-Q40 should be choice, not essay
        if isinstance(num, int) and 1 <= num <= 40 and q['type'] == 'essay':
            q['type'] = 'choice'

            # 嘗試從 stem 中提取 options
            stem = q.get('stem', '')
            matches = option_pattern.findall(stem)
            if len(matches) >= 4:
                q['options'] = {}
                clean_stem_parts = []
                # 把選項從 stem 分離
                first_opt_pos = stem.find('(A)')
                if first_opt_pos == -1:
                    first_opt_pos = stem.find('（A）')
                if first_opt_pos > 0:
                    q['stem'] = stem[:first_opt_pos].strip()
                for letter, text in matches[:4]:
                    q['options'][letter.upper()] = text.strip()

            fixed += 1

    save_json(filepath, data)
    print(f'F3: 修正 {fixed} 題 essay→choice')
    return fixed
```

**Step 2: 執行並驗證**

Run: `python fix_audit_issues.py`
Expected: `F3: 修正 40 題 essay→choice`

驗證：
```bash
python -c "
import json, glob
for f in glob.glob('考古題庫/公共安全學系情報組/108年/外國文*英文*/試題.json'):
    data = json.load(open(f, encoding='utf-8'))
    essay_nums = [q['number'] for q in data['questions'] if q['type'] == 'essay']
    choice_nums = [q['number'] for q in data['questions'] if q['type'] == 'choice']
    choice_with_opts = sum(1 for q in data['questions'] if q['type'] == 'choice' and q.get('options'))
    print(f'Essay: {len(essay_nums)} (nums: {essay_nums})')
    print(f'Choice: {len(choice_nums)}, with options: {choice_with_opts}')
"
```
Expected: Essay 只剩 Q一、Q二、Q三（3 題申論），Choice 40 題

**Step 3: Commit**

```bash
git add fix_audit_issues.py
git commit -m "fix: F3 修正 108年外國文 40 題 essay→choice + 解析 options"
```

---

### Task 7: F5 — 補入水上警察 Q54

**Files:**
- Modify: `fix_audit_issues.py`
- Affected: `考古題庫/水上警察學系/106年/中華民國憲法與水上警察專業英文/試題.json`

**注意**: Q54 屬於閱讀測驗（passage: "請依下文回答第53題至第57題"），Q53 和 Q55 已存在。需要從考選部下載 PDF 取得 Q54 內容。若無法下載，先建立佔位題目。

**Step 1: 加入 F5 修復函式**

```python
def fix_f5_missing_q54():
    """F5: 補入水上警察 106年 Q54"""
    f = glob.glob(f'{BASE}/水上警察學系/106年/中華民國憲法與水上*專業英文/試題.json')
    if not f:
        print('F5: 找不到水上警察 106年英文檔案')
        return 0

    filepath = f[0]
    data = load_json(filepath)

    # 確認 Q54 確實缺失
    nums = [q['number'] for q in data['questions'] if q.get('type') == 'choice']
    if 54 in nums:
        print('F5: Q54 已存在，跳過')
        return 0

    backup_file(filepath)

    # 找到 Q53 的 passage（Q54 屬於同一閱讀測驗組）
    q53 = next((q for q in data['questions'] if q.get('number') == 53), None)
    passage = q53.get('passage', '') if q53 else ''

    # 建立 Q54 佔位（需要從 PDF 補完整內容）
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

    # 插入到 Q53 之後
    for i, q in enumerate(data['questions']):
        if q.get('number') == 53:
            data['questions'].insert(i + 1, q54)
            break

    save_json(filepath, data)
    print(f'F5: 補入 Q54 佔位（需從 PDF 補完整內容）')
    return 1
```

**Step 2: 執行並驗證**

Run: `python fix_audit_issues.py`
Expected: `F5: 補入 Q54 佔位（需從 PDF 補完整內容）`

驗證：
```bash
python -c "
import json, glob
for f in glob.glob('考古題庫/水上警察學系/106年/中華民國憲法與水上*專業英文/試題.json'):
    data = json.load(open(f, encoding='utf-8'))
    nums = sorted([q['number'] for q in data['questions'] if isinstance(q.get('number'), int)])
    expected = list(range(1, max(nums)+1))
    missing = set(expected) - set(nums)
    print(f'Missing: {missing if missing else \"None\"}')
"
```
Expected: `Missing: None`

**Step 3: Commit**

```bash
git add fix_audit_issues.py
git commit -m "fix: F5 補入水上警察 Q54 佔位"
```

---

### Task 8: 額外修復 — 四等選擇題缺 options 欄位

**Files:**
- Modify: `fix_audit_issues.py`
- Affected: 犯罪防治矯治組等四等類別的選擇題

**Step 1: 加入修復函式**

```python
def fix_extra_embedded_options():
    """額外: 修復選擇題 stem 中內嵌選項但無 options 欄位的問題"""
    option_pattern = re.compile(
        r'[\(（]([A-Da-d])[\)）]\s*(.+?)(?=[\(（][A-Da-d][\)）]|$)',
        re.DOTALL
    )

    fixed = 0
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
                    # 分離 stem 和 options
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

    print(f'額外: 修復 {fixed} 題內嵌選項')
    return fixed
```

**Step 2: 執行並驗證**

Run: `python fix_audit_issues.py`

**Step 3: Commit**

```bash
git add fix_audit_issues.py
git commit -m "fix: 修復選擇題 stem 內嵌 options 未分離的問題"
```

---

### Task 9: 全面驗證

**Files:**
- Create: `verify_audit_fix.py`

**Step 1: 寫驗證腳本**

```python
# verify_audit_fix.py
import json
import glob

def verify():
    errors = []
    total_files = 0
    total_questions = 0

    for f in sorted(glob.glob('考古題庫/**/試題.json', recursive=True)):
        data = json.load(open(f, encoding='utf-8'))
        total_files += 1

        for q in data.get('questions', []):
            total_questions += 1

            # F6 check: no metadata in essay stems
            if q['type'] == 'essay' and '乙、測驗部分' in str(q.get('stem', '')):
                errors.append(f'F6 FAIL: {f} Q{q["number"]} metadata in stem')

            # F4 check: no empty stems for choice
            if q['type'] == 'choice' and (not q.get('stem') or not q['stem'].strip()):
                errors.append(f'F4 FAIL: {f} Q{q["number"]} empty stem')

            # F1/F2 check: choice questions should have notes with 2B
            # (check at file level below)

        # File-level checks
        types = [q['type'] for q in data['questions']]
        has_2b = any('2B鉛筆' in n for n in data.get('notes', []))
        if has_2b and 'choice' not in types:
            errors.append(f'F1/F2 FAIL: {f} has 2B note but no choice questions')

    print(f'掃描: {total_files} 檔案, {total_questions} 題')
    if errors:
        print(f'\n發現 {len(errors)} 個問題:')
        for e in errors:
            print(f'  {e}')
    else:
        print('全部通過！零問題。')
    return len(errors)

if __name__ == '__main__':
    verify()
```

**Step 2: 執行驗證**

Run: `python verify_audit_fix.py`
Expected: `全部通過！零問題。`

**Step 3: Commit**

```bash
git add verify_audit_fix.py fix_audit_issues.py
git commit -m "feat: 新增全面驗證腳本 + 審計修復完成"
```

---

### Task 10: 從考選部下載 PDF 補完 F3 answer 和 F5 Q54 內容

**前置條件**: 需要能訪問 https://wwwq.moex.gov.tw/exam/

**Step 1: 下載 3 個 PDF**
1. 公共安全學系情報組/108年/外國文（英文）— 補 Q1-Q40 的 answer
2. 水上警察學系/106年/中華民國憲法與水上警察專業英文 — 補 Q54

**Step 2: 用 pdf_to_questions.py 解析**

```bash
python pdf_to_questions.py --input "下載的PDF路徑"
```

**Step 3: 手動將解析結果合併到 JSON**

**Step 4: 移除 Q54 的 `_todo` 標記**

**Step 5: 重跑驗證**

Run: `python verify_audit_fix.py`

**Step 6: Commit**

```bash
git add -A 考古題庫/
git commit -m "fix: 從考選部 PDF 補完 F3 answer + F5 Q54 內容"
```
