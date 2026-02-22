# -*- coding: utf-8 -*-
"""
答案驗證與整合工具
從答案.pdf / 更正答案.pdf 提取正確答案，寫入試題.json 並驗證一致性。

用法:
  python verify_answers.py                        # 處理全部
  python verify_answers.py --input 考古題庫/行政警察  # 只處理行政警察
  python verify_answers.py --dry-run               # 只驗證不寫入
"""

import os
import re
import json
import argparse
import unicodedata
from pathlib import Path
from datetime import datetime

try:
    import pdfplumber
except ImportError:
    print("需要安裝 pdfplumber: pip install pdfplumber")
    raise


# ===== 答案 PDF 解析 =====

def parse_answer_pdf(pdf_path):
    """
    解析答案 PDF（答案.pdf 或 更正答案.pdf）。
    Returns:
        answers: {int(題號): str(答案)} — 答案為 A/B/C/D 或 '#'（需更正）
        info: {'metadata': {...}, 'notes': {int: str}}
    """
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            text = ''
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + '\n'
    except Exception:
        return {}, {'metadata': {}, 'notes': {}}

    if not text:
        return {}, {'metadata': {}, 'notes': {}}

    answers = {}
    metadata = {}

    # 提取元資料
    m = re.search(r'單選題數[：:]\s*(\d+)\s*題', text)
    if m:
        metadata['total'] = int(m.group(1))

    m = re.search(r'單選每題配分[：:]\s*([\d.]+)\s*分', text)
    if m:
        metadata['score_per_q'] = float(m.group(1))

    m = re.search(r'試題代號[：:]\s*(\d+)', text)
    if m:
        metadata['code'] = m.group(1)

    # 是否為更正答案
    is_correction = '更正' in text[:100] or '更正' in str(pdf_path)

    # 解析答案表格
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if '題號' in line and '第' in line and '題' in line:
            nums = re.findall(r'第(\d+)題', line)
            if i + 1 < len(lines):
                ans_line = lines[i + 1].strip()
                if ans_line.startswith('答案'):
                    ans_part = ans_line[2:].strip()
                    ans_values = re.findall(r'([A-Da-d#])', ans_part)
                    for j, num in enumerate(nums):
                        if j < len(ans_values):
                            ans = ans_values[j]
                            answers[int(num)] = ans.upper() if ans != '#' else '#'
                    i += 2
                    continue
        i += 1

    # 解析備註（更正內容）
    notes = {}
    m = re.search(r'備\s*註[：:]\s*(.+)', text, re.DOTALL)
    if m:
        note_text = m.group(1).strip()
        # 各種更正格式
        for nm in re.finditer(
            r'第(\d+)題[^第]*?'
            r'(一律給分|送分|答\s*([A-Da-dＡ-Ｄａ-ｄ])\s*給分|'
            r'答\s*([A-Da-dＡ-Ｄａ-ｄ])\s*或\s*([A-Da-dＡ-Ｄａ-ｄ])\s*均給分|'
            r'([A-Da-dＡ-Ｄａ-ｄ])\s*或\s*([A-Da-dＡ-Ｄａ-ｄ])\s*均給分)',
            note_text
        ):
            q_num = int(nm.group(1))
            if '一律給分' in nm.group(0) or '送分' in nm.group(0):
                notes[q_num] = '*'
            elif nm.group(3):
                notes[q_num] = unicodedata.normalize('NFKC', nm.group(3)).upper()
            elif nm.group(4) and nm.group(5):
                a1 = unicodedata.normalize('NFKC', nm.group(4)).upper()
                a2 = unicodedata.normalize('NFKC', nm.group(5)).upper()
                notes[q_num] = f'{a1}|{a2}'
            elif nm.group(6) and nm.group(7):
                a1 = unicodedata.normalize('NFKC', nm.group(6)).upper()
                a2 = unicodedata.normalize('NFKC', nm.group(7)).upper()
                notes[q_num] = f'{a1}|{a2}'

    return answers, {'metadata': metadata, 'notes': notes, 'is_correction': is_correction}


def get_final_answers(answer_dir):
    """
    從一個科目目錄取得最終答案（整合答案 + 更正答案）。
    Returns:
        final: {int: str} — 最終答案
        source: str — 'answer' | 'corrected' | None
        metadata: dict
    """
    answer_dir = Path(answer_dir)
    answer_pdf = answer_dir / '答案.pdf'
    corrected_pdf = answer_dir / '更正答案.pdf'

    final = {}
    metadata = {}
    source = None

    # 1. 先讀取原始答案
    if answer_pdf.exists():
        answers, info = parse_answer_pdf(answer_pdf)
        final.update(answers)
        metadata.update(info.get('metadata', {}))
        source = 'answer'

    # 2. 如果有更正答案，覆蓋
    if corrected_pdf.exists():
        corr_answers, corr_info = parse_answer_pdf(corrected_pdf)
        corr_notes = corr_info.get('notes', {})

        # 更正答案中非 '#' 的直接覆蓋
        for num, ans in corr_answers.items():
            if ans != '#':
                final[num] = ans

        # 處理 '#' 標記：用備註中的更正值替換
        for num, note_val in corr_notes.items():
            final[num] = note_val

        source = 'corrected'

    # 3. 原始答案中的 '#' 也用備註處理（少數情況）
    if answer_pdf.exists():
        _, orig_info = parse_answer_pdf(answer_pdf)
        for num, note_val in orig_info.get('notes', {}).items():
            if final.get(num) == '#':
                final[num] = note_val

    # 移除空答案（超出實際題數的空位）
    final = {k: v for k, v in final.items() if v and v != '#'}

    return final, source, metadata


def verify_and_merge(json_path, dry_run=False):
    """
    驗證並整合答案到試題 JSON。
    Returns:
        dict: 驗證結果
    """
    json_path = Path(json_path)
    subject_dir = json_path.parent
    result = {
        'file': str(json_path),
        'status': 'unknown',
        'issues': [],
    }

    # 讀取試題 JSON
    try:
        with open(json_path, encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        result['status'] = 'error'
        result['issues'].append(f'JSON 讀取失敗: {e}')
        return result

    questions = data.get('questions', [])
    choice_qs = [q for q in questions if q.get('type') == 'choice']
    essay_qs = [q for q in questions if q.get('type') == 'essay']

    result['choice_count'] = len(choice_qs)
    result['essay_count'] = len(essay_qs)

    # 如果沒有選擇題，不需要答案
    if not choice_qs:
        result['status'] = 'no_choice'
        return result

    # 取得答案
    final_answers, source, ans_metadata = get_final_answers(subject_dir)

    if not final_answers:
        # 沒有答案 PDF
        has_answer_pdf = (subject_dir / '答案.pdf').exists()
        if has_answer_pdf:
            result['status'] = 'parse_failed'
            result['issues'].append('答案 PDF 存在但解析失敗')
        else:
            result['status'] = 'no_answer_pdf'
            result['issues'].append('沒有答案 PDF')
        return result

    result['answer_source'] = source
    result['answer_count'] = len(final_answers)

    # 答案 PDF 的題數為 ground truth
    expected_total = ans_metadata.get('total', len(final_answers))
    valid_range = set(range(1, expected_total + 1))

    # ===== 清除假陽性：移除不在合法範圍或重複的選擇題 =====
    removed = []
    if len(choice_qs) > expected_total:
        # 找出假陽性題目
        seen_nums = set()
        clean_questions = []
        for q in questions:
            if q.get('type') != 'choice':
                clean_questions.append(q)
                continue

            q_num = q.get('number')
            if isinstance(q_num, str):
                try:
                    q_num = int(q_num)
                except ValueError:
                    clean_questions.append(q)
                    continue

            # 不在合法範圍（如 340nm 的 340）
            if q_num not in valid_range:
                removed.append(q_num)
                continue

            # 重複題號（如英文閱讀中出現的 54.）
            if q_num in seen_nums:
                # 保留題幹較長的那個（假陽性通常是文章片段）
                # 找已保留的同號題
                existing = next(
                    (eq for eq in clean_questions
                     if eq.get('type') == 'choice' and eq.get('number') == q_num),
                    None
                )
                if existing and len(q.get('stem', '')) > len(existing.get('stem', '')):
                    # 新的更長，替換舊的
                    clean_questions.remove(existing)
                    clean_questions.append(q)
                    removed.append(f'{q_num}(dup-replaced)')
                else:
                    removed.append(f'{q_num}(dup)')
                continue

            seen_nums.add(q_num)
            clean_questions.append(q)

        if removed:
            result['removed_false_positives'] = removed
            result['issues'].append(f'移除假陽性題目: {removed}')
            questions = clean_questions
            data['questions'] = questions
            choice_qs = [q for q in questions if q.get('type') == 'choice']

    # 比對題數
    if len(choice_qs) != expected_total:
        result['issues'].append(
            f'選擇題數不匹配: JSON={len(choice_qs)}, 答案PDF={expected_total}'
        )

    # 逐題配對答案
    matched = 0
    unmatched = []
    for q in choice_qs:
        q_num = q.get('number')
        if isinstance(q_num, str):
            try:
                q_num = int(q_num)
            except ValueError:
                continue

        if q_num in final_answers:
            q['answer'] = final_answers[q_num]
            matched += 1
        else:
            unmatched.append(q_num)

    result['matched'] = matched
    if unmatched:
        result['issues'].append(f'找不到答案的題號: {unmatched}')

    # 檢查答案 PDF 中有但 JSON 中沒有的題號
    json_nums = set()
    for q in choice_qs:
        n = q.get('number')
        if isinstance(n, int):
            json_nums.add(n)
        elif isinstance(n, str):
            try:
                json_nums.add(int(n))
            except ValueError:
                pass

    extra_in_answer = set(final_answers.keys()) - json_nums
    if extra_in_answer:
        result['issues'].append(f'答案 PDF 多出的題號: {sorted(extra_in_answer)}')

    # 判定狀態
    if not result['issues']:
        result['status'] = 'ok'
    elif matched == expected_total:
        result['status'] = 'ok_cleaned'
    elif matched > 0 and not unmatched:
        result['status'] = 'ok_with_warnings'
    else:
        result['status'] = 'mismatch'

    # 寫入
    if not dry_run and matched > 0:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return result


def process_all(input_dir, dry_run=False):
    """處理所有試題 JSON"""
    input_dir = Path(input_dir)
    json_files = sorted(input_dir.rglob('試題.json'))

    if not json_files:
        print(f"找不到 JSON 檔案: {input_dir}")
        return

    print(f"{'=' * 70}")
    print(f"  答案驗證與整合工具 {'(DRY RUN)' if dry_run else ''}")
    print(f"{'=' * 70}")
    print(f"找到 {len(json_files)} 個試題 JSON")
    print(f"{'-' * 70}")

    stats = {
        'total': len(json_files),
        'ok': 0,
        'ok_cleaned': 0,
        'ok_with_warnings': 0,
        'no_choice': 0,
        'no_answer_pdf': 0,
        'mismatch': 0,
        'parse_failed': 0,
        'error': 0,
        'total_matched': 0,
        'total_removed': 0,
        'issues': [],
    }

    for jf in json_files:
        rel = jf.relative_to(input_dir)
        result = verify_and_merge(jf, dry_run=dry_run)
        status = result['status']
        stats[status] = stats.get(status, 0) + 1
        stats['total_matched'] += result.get('matched', 0)
        removed = result.get('removed_false_positives', [])
        stats['total_removed'] += len(removed)

        # 輸出
        if status == 'ok':
            matched = result.get('matched', 0)
            print(f"  OK      {rel.parent}  ({matched} 題)")
        elif status == 'ok_cleaned':
            matched = result.get('matched', 0)
            print(f"  FIXED   {rel.parent}  ({matched} 題，移除假陽性: {removed})")
        elif status == 'no_choice':
            pass  # 純申論不輸出
        elif status == 'no_answer_pdf':
            pass  # 無答案不輸出
        elif status in ('mismatch', 'ok_with_warnings', 'parse_failed', 'error'):
            icon = {'mismatch': 'WARN', 'ok_with_warnings': 'WARN',
                    'parse_failed': 'FAIL', 'error': 'ERR '}[status]
            print(f"  {icon}   {rel.parent}")
            for issue in result.get('issues', []):
                print(f"          -> {issue}")
                stats['issues'].append(f"{rel.parent}: {issue}")

    # 統計報告
    print(f"\n{'=' * 70}")
    print("驗證完成！")
    print(f"{'=' * 70}")
    print(f"總計: {stats['total']} 個試題")
    print(f"  完全匹配:       {stats['ok']}")
    print(f"  清除後匹配:     {stats['ok_cleaned']} (移除 {stats['total_removed']} 個假陽性)")
    print(f"  匹配(有警告):   {stats['ok_with_warnings']}")
    print(f"  純申論(跳過):   {stats['no_choice']}")
    print(f"  無答案 PDF:     {stats['no_answer_pdf']}")
    print(f"  題數不匹配:     {stats['mismatch']}")
    print(f"  解析失敗:       {stats['parse_failed']}")
    print(f"  錯誤:           {stats['error']}")
    print(f"  共配對答案:     {stats['total_matched']} 題")

    if stats['issues']:
        print(f"\n{'=' * 70}")
        print(f"問題清單 ({len(stats['issues'])} 項):")
        for issue in stats['issues']:
            print(f"  - {issue}")

    # 儲存報告
    report_path = input_dir / 'answer_verification_report.json'
    report = {
        'timestamp': datetime.now().isoformat(),
        'dry_run': dry_run,
        'stats': {k: v for k, v in stats.items() if k != 'issues'},
        'issues': stats['issues'],
    }
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n報告已儲存: {report_path}")


def main():
    parser = argparse.ArgumentParser(description='答案驗證與整合工具')
    parser.add_argument('--input', '-i', type=str,
                        default=os.path.join(os.path.dirname(__file__), '考古題庫'),
                        help='輸入路徑')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='只驗證不寫入')
    args = parser.parse_args()

    process_all(args.input, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
