# -*- coding: utf-8 -*-
"""
國境警察學系移民組 vs 警察特考 跨分類對比審查腳本
比較 JSON 結構、科目命名規範、品質指標、轉換邏輯差異
"""

import os
import re
import json
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).parent / '考古題庫'
CATEGORIES = [d.name for d in sorted(BASE_DIR.iterdir()) if d.is_dir()]

# ========================================================================
# 工具函式
# ========================================================================

def load_all_jsons(category):
    """載入某分類下所有 試題.json，回傳 [(year, subject, data, path), ...]"""
    results = []
    cat_dir = BASE_DIR / category
    if not cat_dir.exists():
        return results
    for year_dir in sorted(cat_dir.iterdir()):
        if not year_dir.is_dir():
            continue
        m = re.match(r'(\d{3})年$', year_dir.name)
        if not m:
            continue
        year = int(m.group(1))
        for subj_dir in sorted(year_dir.iterdir()):
            if not subj_dir.is_dir():
                continue
            jp = subj_dir / '試題.json'
            if jp.exists():
                try:
                    with open(jp, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    results.append((year, subj_dir.name, data, str(jp)))
                except Exception as e:
                    results.append((year, subj_dir.name, None, str(jp)))
    return results


def collect_keys_recursive(obj, prefix=''):
    """遞迴收集 dict/list 中所有 key 路徑"""
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            full = f"{prefix}.{k}" if prefix else k
            keys.add(full)
            keys |= collect_keys_recursive(v, full)
    elif isinstance(obj, list) and obj:
        keys |= collect_keys_recursive(obj[0], f"{prefix}[]")
    return keys


# ========================================================================
# 1. JSON 結構對比
# ========================================================================

def audit_json_structure():
    print("\n" + "=" * 80)
    print("  1. JSON 結構對比")
    print("=" * 80)

    category_schemas = {}

    for cat in CATEGORIES:
        records = load_all_jsons(cat)
        if not records:
            continue

        # 收集所有 top-level keys 和 question keys
        top_keys_all = set()
        q_keys_all = set()
        q_key_types = defaultdict(set)
        top_key_types = defaultdict(set)
        sample_count = 0

        for year, subj, data, path in records:
            if data is None:
                continue
            sample_count += 1
            if isinstance(data, dict):
                for k, v in data.items():
                    top_keys_all.add(k)
                    top_key_types[k].add(type(v).__name__)
                for q in data.get('questions', []):
                    if isinstance(q, dict):
                        for k, v in q.items():
                            q_keys_all.add(k)
                            q_key_types[k].add(type(v).__name__)

        category_schemas[cat] = {
            'top_keys': top_keys_all,
            'q_keys': q_keys_all,
            'top_types': dict(top_key_types),
            'q_types': dict(q_key_types),
            'sample_count': sample_count,
        }

    # 以國境警察學系移民組為基準，與其他分類比較
    imm = category_schemas.get('國境警察學系移民組')
    if not imm:
        print("  [錯誤] 找不到國境警察學系移民組資料")
        return

    print(f"\n  國境警察學系移民組 Top-level 欄位: {sorted(imm['top_keys'])}")
    print(f"  國境警察學系移民組 Question 欄位:  {sorted(imm['q_keys'])}")
    print()

    # 表格：各分類 top-level 欄位比較
    all_top_keys = set()
    for s in category_schemas.values():
        all_top_keys |= s['top_keys']
    all_top_keys = sorted(all_top_keys)

    print(f"  {'分類':<16} {'樣本數':>6}  ", end='')
    for k in all_top_keys:
        print(f"{k[:12]:>13}", end='')
    print()
    print("  " + "-" * (22 + 13 * len(all_top_keys)))

    for cat in ['國境警察學系移民組'] + [c for c in CATEGORIES if c != '國境警察學系移民組']:
        s = category_schemas.get(cat)
        if not s:
            continue
        print(f"  {cat:<16} {s['sample_count']:>6}  ", end='')
        for k in all_top_keys:
            if k in s['top_keys']:
                print(f"{'V':>13}", end='')
            else:
                print(f"{'--':>13}", end='')
        print()

    # 國境警察學系移民組獨有欄位
    print(f"\n  --- 國境警察學系移民組獨有的 Top-level 欄位（其他分類沒有）---")
    for cat in CATEGORIES:
        if cat == '國境警察學系移民組':
            continue
        s = category_schemas.get(cat)
        if not s:
            continue
        only_imm = imm['top_keys'] - s['top_keys']
        only_other = s['top_keys'] - imm['top_keys']
        if only_imm or only_other:
            print(f"  vs {cat}:")
            if only_imm:
                print(f"    國境警察學系移民組獨有: {sorted(only_imm)}")
            if only_other:
                print(f"    {cat}獨有: {sorted(only_other)}")

    # Question 欄位比較
    print(f"\n  --- Question 欄位比較 ---")
    all_q_keys = set()
    for s in category_schemas.values():
        all_q_keys |= s['q_keys']
    all_q_keys = sorted(all_q_keys)

    print(f"  {'分類':<16}  ", end='')
    for k in all_q_keys:
        print(f"{k:>10}", end='')
    print()
    print("  " + "-" * (18 + 10 * len(all_q_keys)))

    for cat in ['國境警察學系移民組'] + [c for c in CATEGORIES if c != '國境警察學系移民組']:
        s = category_schemas.get(cat)
        if not s:
            continue
        print(f"  {cat:<16}  ", end='')
        for k in all_q_keys:
            if k in s['q_keys']:
                print(f"{'V':>10}", end='')
            else:
                print(f"{'--':>10}", end='')
        print()

    return category_schemas


# ========================================================================
# 2. 科目命名規範
# ========================================================================

def audit_naming_conventions():
    print("\n" + "=" * 80)
    print("  2. 科目命名規範")
    print("=" * 80)

    # 檢查 [等級] 前綴
    print("\n  --- [等級] 前綴使用情況 ---")
    prefix_pat = re.compile(r'^\[([^\]]+)\]\s*')

    for cat in CATEGORIES:
        cat_dir = BASE_DIR / cat
        if not cat_dir.is_dir():
            continue
        has_prefix = 0
        no_prefix = 0
        prefix_levels = set()
        for year_dir in cat_dir.iterdir():
            if not year_dir.is_dir():
                continue
            for subj_dir in year_dir.iterdir():
                if not subj_dir.is_dir():
                    continue
                m = prefix_pat.match(subj_dir.name)
                if m:
                    has_prefix += 1
                    prefix_levels.add(m.group(1))
                else:
                    no_prefix += 1
        total = has_prefix + no_prefix
        if total > 0:
            pct = has_prefix / total * 100
            levels_str = ', '.join(sorted(prefix_levels)) if prefix_levels else 'N/A'
            print(f"  {cat:<16}: 有前綴 {has_prefix:>4} / 無前綴 {no_prefix:>4} "
                  f"({pct:5.1f}% 有前綴)  等級: {levels_str}")

    # 檢查括號使用（全形 vs 半形）
    print("\n  --- 括號使用規範（全形 vs 半形）---")
    for cat in CATEGORIES:
        cat_dir = BASE_DIR / cat
        if not cat_dir.is_dir():
            continue
        full_width = 0  # 使用全形括號 （）
        half_width = 0  # 使用半形括號 ()
        mixed = 0       # 同一科目混用

        for year_dir in cat_dir.iterdir():
            if not year_dir.is_dir():
                continue
            for subj_dir in year_dir.iterdir():
                if not subj_dir.is_dir():
                    continue
                name = subj_dir.name
                # 去掉 [等級] 前綴
                name_core = prefix_pat.sub('', name)
                has_full = '（' in name_core or '）' in name_core
                has_half = '(' in name_core or ')' in name_core
                if has_full and has_half:
                    mixed += 1
                elif has_full:
                    full_width += 1
                elif has_half:
                    half_width += 1

        total = full_width + half_width + mixed
        if total > 0:
            print(f"  {cat:<16}: 全形 {full_width:>4} / 半形 {half_width:>4} / 混用 {mixed:>4}")

    # 檢查同一科目跨年命名不一致
    print("\n  --- 國境警察學系移民組科目名稱跨年一致性問題 ---")
    cat_dir = BASE_DIR / '國境警察學系移民組'
    # 提取科目核心名（去掉年份和 [等級] 前綴）
    subj_by_year = defaultdict(set)
    for year_dir in sorted(cat_dir.iterdir()):
        if not year_dir.is_dir():
            continue
        m = re.match(r'(\d{3})年$', year_dir.name)
        if not m:
            continue
        year = m.group(1)
        for subj_dir in year_dir.iterdir():
            if not subj_dir.is_dir():
                continue
            subj_by_year[year].add(subj_dir.name)

    # 找同一等級下名稱有微小差異的科目
    years = sorted(subj_by_year.keys())
    if len(years) >= 2:
        # 將科目按等級分組，比較跨年名稱
        level_subjects = defaultdict(lambda: defaultdict(set))
        for year, subjects in subj_by_year.items():
            for s in subjects:
                m = prefix_pat.match(s)
                if m:
                    level = m.group(1)
                    core = prefix_pat.sub('', s)
                else:
                    level = 'N/A'
                    core = s
                level_subjects[level][year].add(core)

        for level in sorted(level_subjects.keys()):
            yearly = level_subjects[level]
            all_names = set()
            for names in yearly.values():
                all_names |= names

            # 找出只在部分年份出現的名稱
            for name in sorted(all_names):
                present_years = [y for y in years if name in yearly.get(y, set())]
                if 0 < len(present_years) < len(years):
                    # 可能是名稱變動
                    # 找最相似的
                    absent_years = [y for y in years if y not in present_years]
                    if len(absent_years) <= 3:
                        print(f"  [{level}] \"{name[:50]}...\" "
                              f"僅在 {','.join(present_years[:3])}... 出現 "
                              f"(缺 {','.join(absent_years[:3])}...)")

    # 特別檢查括號不一致（同一科目在不同年份使用不同括號）
    print("\n  --- 國境警察學系移民組：同科目跨年括號不一致的例子 ---")
    # 取核心名稱（去掉等級前綴、去掉括號型態差異後）
    def normalize_for_compare(name):
        n = prefix_pat.sub('', name)
        n = n.replace('（', '(').replace('）', ')')
        return n

    found_inconsistent = 0
    for level in sorted(level_subjects.keys()):
        yearly = level_subjects[level]
        # 把每年的科目名統一化後比對
        normalized_to_originals = defaultdict(set)
        for year in years:
            for name in yearly.get(year, set()):
                norm = name.replace('（', '(').replace('）', ')')
                normalized_to_originals[norm].add((year, name))

        for norm, instances in normalized_to_originals.items():
            unique_names = set(name for _, name in instances)
            if len(unique_names) > 1:
                if found_inconsistent < 10:
                    print(f"  [{level}] 同科目不同寫法:")
                    for name in sorted(unique_names):
                        yrs = [y for y, n in instances if n == name]
                        print(f"    \"{name[:60]}\" => {','.join(sorted(yrs))}")
                found_inconsistent += 1

    if found_inconsistent > 10:
        print(f"  ... 共 {found_inconsistent} 組不一致")


# ========================================================================
# 3. 品質指標對比
# ========================================================================

def audit_quality_metrics():
    print("\n" + "=" * 80)
    print("  3. 品質指標對比")
    print("=" * 80)

    cat_stats = {}

    for cat in CATEGORIES:
        records = load_all_jsons(cat)
        if not records:
            continue

        total_files = 0
        total_questions = 0
        total_choice = 0
        total_essay = 0
        total_with_answer = 0
        total_choice_with_options = 0
        total_choice_with_4opts = 0
        files_with_0_q = 0
        year_set = set()

        for year, subj, data, path in records:
            if data is None:
                files_with_0_q += 1
                total_files += 1
                continue
            total_files += 1
            year_set.add(year)
            questions = data.get('questions', [])
            total_questions += len(questions)
            if len(questions) == 0:
                files_with_0_q += 1

            for q in questions:
                if q.get('type') == 'choice':
                    total_choice += 1
                    if q.get('answer'):
                        total_with_answer += 1
                    opts = q.get('options', {})
                    if opts and len(opts) >= 2:
                        total_choice_with_options += 1
                    if opts and len(opts) >= 4:
                        total_choice_with_4opts += 1
                elif q.get('type') == 'essay':
                    total_essay += 1

        avg_q_per_file = total_questions / total_files if total_files > 0 else 0
        answer_rate = total_with_answer / total_choice * 100 if total_choice > 0 else 0
        opt_complete_rate = total_choice_with_4opts / total_choice * 100 if total_choice > 0 else 0
        opt_any_rate = total_choice_with_options / total_choice * 100 if total_choice > 0 else 0
        empty_rate = files_with_0_q / total_files * 100 if total_files > 0 else 0

        cat_stats[cat] = {
            'files': total_files,
            'years': len(year_set),
            'total_q': total_questions,
            'choice': total_choice,
            'essay': total_essay,
            'avg_q': avg_q_per_file,
            'answer_rate': answer_rate,
            'opt_4_rate': opt_complete_rate,
            'opt_any_rate': opt_any_rate,
            'empty_pct': empty_rate,
        }

    # 表格輸出
    header = (f"  {'分類':<16} {'檔案':>5} {'年份':>4} {'總題':>6} "
              f"{'選擇':>6} {'申論':>6} {'平均題/檔':>9} "
              f"{'有答案%':>8} {'4選項%':>7} {'空檔%':>6}")
    print(f"\n{header}")
    print("  " + "-" * (len(header) - 2))

    # 先印國境警察學系移民組
    for cat in ['國境警察學系移民組'] + [c for c in sorted(CATEGORIES) if c != '國境警察學系移民組']:
        s = cat_stats.get(cat)
        if not s:
            continue
        marker = " <<<" if cat == '國境警察學系移民組' else ""
        print(f"  {cat:<16} {s['files']:>5} {s['years']:>4} {s['total_q']:>6} "
              f"{s['choice']:>6} {s['essay']:>6} {s['avg_q']:>9.1f} "
              f"{s['answer_rate']:>7.1f}% {s['opt_4_rate']:>6.1f}% {s['empty_pct']:>5.1f}%{marker}")

    # 計算整體平均（不含國境警察學系移民組）
    other_cats = [c for c in CATEGORIES if c != '國境警察學系移民組' and c in cat_stats]
    if other_cats:
        avg_q = sum(cat_stats[c]['avg_q'] for c in other_cats) / len(other_cats)
        avg_ans = sum(cat_stats[c]['answer_rate'] for c in other_cats) / len(other_cats)
        avg_opt = sum(cat_stats[c]['opt_4_rate'] for c in other_cats) / len(other_cats)
        avg_empty = sum(cat_stats[c]['empty_pct'] for c in other_cats) / len(other_cats)
        imm = cat_stats.get('國境警察學系移民組', {})

        print()
        print(f"  {'其他分類平均':<16} {'':>5} {'':>4} {'':>6} "
              f"{'':>6} {'':>6} {avg_q:>9.1f} "
              f"{avg_ans:>7.1f}% {avg_opt:>6.1f}% {avg_empty:>5.1f}%")
        if imm:
            diff_q = imm['avg_q'] - avg_q
            diff_ans = imm['answer_rate'] - avg_ans
            diff_opt = imm['opt_4_rate'] - avg_opt
            print(f"  {'移民 vs 平均差距':<16} {'':>5} {'':>4} {'':>6} "
                  f"{'':>6} {'':>6} {diff_q:>+9.1f} "
                  f"{diff_ans:>+7.1f}% {diff_opt:>+6.1f}%")

    return cat_stats


# ========================================================================
# 4. 轉換腳本差異分析
# ========================================================================

def audit_script_differences():
    print("\n" + "=" * 80)
    print("  4. process_immigration.py vs pdf_to_questions.py 差異分析")
    print("=" * 80)

    script_dir = Path(__file__).parent

    features = [
        ("PUA Unicode 轉換", "process_immigration.py 有", "pdf_to_questions.py 無"),
        ("preprocess_immigration_text()", "有（將 PUA 字元轉為 (A)(B)(C)(D)）", "無"),
        ("clean_bogus_questions()", "有（清除假題目）", "無"),
        ("fix_missing_options()", "有（從題幹提取內嵌選項）", "無"),
        ("merge_answer_data()", "有（合併答案PDF）", "無"),
        ("更正答案處理", "有（讀取 更正答案.pdf）", "無"),
        ("選擇題→申論題降級", "有（選項<2 個時降級）", "無"),
        ("shorten_subject()", "有（縮短科目名稱）", "無"),
        ("MD5 重複偵測", "有（跳過相同 PDF）", "無"),
        ("[等級] 前綴", "有（加入 [三等] 等前綴）", "無"),
        ("level 欄位", "有", "無"),
        ("original_subject 欄位", "有", "無"),
        ("total_questions 欄位", "兩者都有", "兩者都有"),
        ("OCR 修復 (fix_ocr)", "無（透過 import 使用）", "有"),
        ("normalize_text()", "匯入使用", "原始定義"),
        ("fallback_extract_essays()", "匯入使用", "原始定義"),
        ("category 推斷", "硬編碼 '國境警察學系移民組'", "從目錄結構推斷"),
    ]

    print(f"\n  {'功能/特性':<35} {'process_immigration.py':<35} {'pdf_to_questions.py':<30}")
    print("  " + "-" * 100)
    for feat, imm, pdf in features:
        print(f"  {feat:<35} {imm:<35} {pdf:<30}")

    print("\n  --- 關鍵差異分析 ---")
    print("""
  1. process_immigration.py 額外做了 PUA Unicode 預處理。考選部的國境警察學系移民組 PDF
     使用私有 Unicode 字元（U+E18C~U+E18F）作為選項標記，需要先轉換為標準
     (A)(B)(C)(D) 格式。pdf_to_questions.py 不需要這步，因為警察特考 PDF 直接
     使用標準格式。

  2. process_immigration.py 有更多後處理步驟：
     - clean_bogus_questions：清除誤解析的假題目（年份/代號數字）
     - fix_missing_options：從題幹中提取被遺漏的內嵌選項
     - 選擇題降級為申論題（當選項不足時）
     這些步驟是 pdf_to_questions.py 所沒有的，可能導致警察特考題庫
     也存在類似問題但未被修復。

  3. process_immigration.py 獨有的答案合併功能（merge_answer_data）：
     支援三種格式的答案解析，還處理「更正答案」。
     pdf_to_questions.py 完全沒有答案處理邏輯。

  4. process_immigration.py 輸出的 JSON 多了 'level' 和 'original_subject' 欄位，
     這是其他分類 JSON 所沒有的。
""")


# ========================================================================
# 5. 共用科目檢查
# ========================================================================

def audit_shared_subjects():
    print("\n" + "=" * 80)
    print("  5. 共用科目檢查")
    print("=" * 80)

    # 共用科目關鍵字
    shared_keywords = ['國文', '法學知識與英文', '行政法']

    # 收集所有分類中包含這些關鍵字的科目
    all_records = {}
    for cat in CATEGORIES:
        records = load_all_jsons(cat)
        all_records[cat] = records

    # 5a. JSON 格式一致性
    print("\n  --- 5a. 共用科目 JSON 格式一致性 ---")

    for keyword in shared_keywords:
        print(f"\n  科目關鍵字: 「{keyword}」")
        cat_formats = {}
        for cat in CATEGORIES:
            for year, subj, data, path in all_records.get(cat, []):
                if data is None:
                    continue
                # 去掉 [等級] 前綴後檢查
                subj_core = re.sub(r'^\[[^\]]+\]\s*', '', subj)
                if keyword not in subj_core:
                    continue
                top_keys = sorted(data.keys()) if isinstance(data, dict) else []
                q_keys = set()
                for q in data.get('questions', []):
                    if isinstance(q, dict):
                        q_keys |= set(q.keys())
                q_keys = sorted(q_keys)
                fmt_key = (tuple(top_keys), tuple(q_keys))
                if cat not in cat_formats:
                    cat_formats[cat] = set()
                cat_formats[cat].add(fmt_key)

        # 比較國境警察學系移民組 vs 其他
        imm_fmts = cat_formats.get('國境警察學系移民組', set())
        for cat in CATEGORIES:
            if cat == '國境警察學系移民組':
                continue
            other_fmts = cat_formats.get(cat, set())
            if not other_fmts:
                continue
            if imm_fmts and other_fmts:
                imm_top = set()
                imm_q = set()
                other_top = set()
                other_q = set()
                for t, q in imm_fmts:
                    imm_top |= set(t)
                    imm_q |= set(q)
                for t, q in other_fmts:
                    other_top |= set(t)
                    other_q |= set(q)

                top_diff_imm = imm_top - other_top
                top_diff_other = other_top - imm_top
                q_diff_imm = imm_q - other_q
                q_diff_other = other_q - imm_q

                if top_diff_imm or top_diff_other or q_diff_imm or q_diff_other:
                    print(f"    國境警察學系移民組 vs {cat}:")
                    if top_diff_imm:
                        print(f"      移民獨有 top-level: {sorted(top_diff_imm)}")
                    if top_diff_other:
                        print(f"      {cat}獨有 top-level: {sorted(top_diff_other)}")
                    if q_diff_imm:
                        print(f"      移民獨有 question: {sorted(q_diff_imm)}")
                    if q_diff_other:
                        print(f"      {cat}獨有 question: {sorted(q_diff_other)}")

    # 5b. 同年同科目是否重複
    print(f"\n  --- 5b. 同年共用科目試題重複檢查 ---")
    print("  (比較國境警察學系移民組與警察特考的同年「國文」「法學知識與英文」是否為相同試題)")

    comparison_cats = ['行政警察學系', '刑事警察學系', '國境警察學系境管組']

    for keyword in ['國文', '法學知識與英文']:
        print(f"\n  科目: 「{keyword}」")

        # 收集國境警察學系移民組的題目
        imm_by_year = {}
        for year, subj, data, path in all_records.get('國境警察學系移民組', []):
            if data is None:
                continue
            subj_core = re.sub(r'^\[[^\]]+\]\s*', '', subj)
            if keyword not in subj_core:
                continue
            questions = data.get('questions', [])
            choice_stems = set()
            for q in questions:
                if q.get('type') == 'choice' and q.get('stem'):
                    choice_stems.add(q['stem'][:50])  # 取前50字比較
            if choice_stems:
                if year not in imm_by_year:
                    imm_by_year[year] = {'stems': choice_stems, 'subj': subj, 'count': len(questions)}
                else:
                    # 可能有多個等級
                    imm_by_year[year]['stems'] |= choice_stems

        for comp_cat in comparison_cats:
            found_overlap = False
            for year, subj, data, path in all_records.get(comp_cat, []):
                if data is None:
                    continue
                subj_core = re.sub(r'^\[[^\]]+\]\s*', '', subj)
                if keyword not in subj_core:
                    continue
                if year not in imm_by_year:
                    continue

                questions = data.get('questions', [])
                comp_stems = set()
                for q in questions:
                    if q.get('type') == 'choice' and q.get('stem'):
                        comp_stems.add(q['stem'][:50])

                if comp_stems and imm_by_year[year]['stems']:
                    overlap = comp_stems & imm_by_year[year]['stems']
                    overlap_pct = len(overlap) / min(len(comp_stems), len(imm_by_year[year]['stems'])) * 100 if min(len(comp_stems), len(imm_by_year[year]['stems'])) > 0 else 0
                    if overlap:
                        status = "相同試題" if overlap_pct > 80 else "部分重疊" if overlap_pct > 20 else "不同試題"
                        print(f"    {year}年 國境警察學系移民組 vs {comp_cat}: "
                              f"重疊 {len(overlap)} 題 / "
                              f"移民 {len(imm_by_year[year]['stems'])} 題 vs {comp_cat} {len(comp_stems)} 題 "
                              f"({overlap_pct:.0f}%) => {status}")
                        found_overlap = True

            if not found_overlap:
                print(f"    國境警察學系移民組 vs {comp_cat}: 無重疊年份或無選擇題可比較")

    # 5c. 等級標注問題
    print(f"\n  --- 5c. 國境警察學系移民組等級標注 vs 警察特考 ---")
    print("  國境警察學系移民組有 [二等]/[三等]/[四等] 前綴，警察特考各分類沒有。")
    print("  這導致：")
    print("    - 國境警察學系移民組同一年有多個等級的同科目（如 [三等] 國文 和 [四等] 國文）")
    print("    - 警察特考每年每科只有一個目錄（無等級區分）")

    # 統計各分類每年科目數
    print(f"\n  每年平均科目數比較:")
    for cat in ['國境警察學系移民組'] + comparison_cats:
        records = all_records.get(cat, [])
        year_counts = defaultdict(int)
        for year, subj, data, path in records:
            year_counts[year] += 1
        if year_counts:
            avg = sum(year_counts.values()) / len(year_counts)
            min_c = min(year_counts.values())
            max_c = max(year_counts.values())
            print(f"    {cat:<16}: 平均 {avg:.1f} 科/年 (最少 {min_c}, 最多 {max_c})")


# ========================================================================
# 主程式
# ========================================================================

def main():
    print("=" * 80)
    print("  國境警察學系移民組 vs 警察特考 跨分類對比審查報告")
    print(f"  檢查目錄: {BASE_DIR}")
    print(f"  分類數: {len(CATEGORIES)} ({', '.join(CATEGORIES)})")
    print("=" * 80)

    audit_json_structure()
    audit_naming_conventions()
    audit_quality_metrics()
    audit_script_differences()
    audit_shared_subjects()

    print("\n" + "=" * 80)
    print("  審查完成")
    print("=" * 80)


if __name__ == '__main__':
    main()
