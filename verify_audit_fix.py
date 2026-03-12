#!/usr/bin/env python3
"""全面驗證腳本：檢查所有 6 類審計修復是否完成。"""

import json
import glob


def verify():
    errors = []
    total_files = 0
    total_questions = 0
    stats = {
        'essay': 0,
        'choice': 0,
        'choice_with_options': 0,
        'choice_with_answer': 0,
    }

    for f in sorted(glob.glob('考古題庫/**/試題.json', recursive=True)):
        data = json.load(open(f, encoding='utf-8'))
        total_files += 1

        for q in data.get('questions', []):
            total_questions += 1
            qtype = q.get('type', '')
            stats[qtype] = stats.get(qtype, 0) + 1

            # F6: metadata 不應出現在 essay stems
            if qtype == 'essay' and '乙、測驗部分' in str(q.get('stem', '')):
                errors.append(f'F6 FAIL: {f} Q{q["number"]} metadata in stem')

            # F4: choice 題不應有空 stem
            if qtype == 'choice' and (not q.get('stem') or not q['stem'].strip()):
                errors.append(f'F4 FAIL: {f} Q{q["number"]} empty stem')

            # 統計 options 和 answer
            if qtype == 'choice':
                if q.get('options'):
                    stats['choice_with_options'] += 1
                if q.get('answer'):
                    stats['choice_with_answer'] += 1

        # F1/F2: 有 2B 提示的檔案應有 choice 題
        types = [q['type'] for q in data['questions']]
        has_2b = any('2B鉛筆' in n for n in data.get('notes', []))
        if has_2b and 'choice' not in types:
            errors.append(f'F1/F2 FAIL: {f} has 2B note but no choice questions')

    # F3: 108年外國文應有 choice
    for f in glob.glob('考古題庫/公共安全學系情報組/108年/外國文*英文*/試題.json'):
        data = json.load(open(f, encoding='utf-8'))
        choice_count = sum(1 for q in data['questions'] if q['type'] == 'choice')
        if choice_count < 40:
            errors.append(f'F3 FAIL: {f} only {choice_count} choice (expected 40)')

    # F5: Q54 應存在
    for f in glob.glob('考古題庫/水上警察學系/106年/中華民國憲法與水上*專業英文/試題.json'):
        data = json.load(open(f, encoding='utf-8'))
        nums = [q['number'] for q in data['questions'] if isinstance(q.get('number'), int)]
        if 54 not in nums:
            errors.append(f'F5 FAIL: {f} Q54 missing')

    print(f'=== 全面驗證報告 ===')
    print(f'掃描: {total_files} 檔案, {total_questions} 題')
    print(f'題型統計: essay={stats["essay"]}, choice={stats["choice"]}')
    print(f'選擇題有 options: {stats["choice_with_options"]}')
    print(f'選擇題有 answer: {stats["choice_with_answer"]}')
    print()

    if errors:
        print(f'發現 {len(errors)} 個問題:')
        for e in errors:
            print(f'  {e}')
        return len(errors)
    else:
        print('全部通過！零問題。')
        return 0


if __name__ == '__main__':
    exit(verify())
