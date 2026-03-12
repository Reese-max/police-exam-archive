# -*- coding: utf-8 -*-
"""深入分析空白 stem 和其他問題的模式"""
import json, glob, os, re
from collections import defaultdict

TARGET_DIR = "C:/Users/User/Desktop/考古題下載/考古題庫/國境警察學系移民組"
files = sorted(glob.glob(os.path.join(TARGET_DIR, "**", "試題.json"), recursive=True))

# ========================================
# 1. 空白 stem 深入分析
# ========================================
print("=" * 80)
print("  空白 stem 深入分析")
print("=" * 80)

empty_stem_files = {}

for filepath in files:
    rel = os.path.relpath(filepath, TARGET_DIR)
    with open(filepath, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    items = []
    for idx, q in enumerate(data.get("questions", [])):
        stem = q.get("stem", "")
        if isinstance(stem, str) and not stem.strip():
            items.append((idx, q.get("number", "?"), q.get("type", "?")))
    if items:
        empty_stem_files[rel] = items

print(f"\n受影響檔案數: {len(empty_stem_files)}")
print(f"空白 stem 題目總數: {sum(len(v) for v in empty_stem_files.values())}")

# 依科目分類
subject_counts = defaultdict(int)
subject_files = defaultdict(int)
for rel, items in empty_stem_files.items():
    # 提取科目名
    parts = rel.replace("\\", "/").split("/")
    subject = parts[1] if len(parts) > 1 else "unknown"
    # 簡化科目名
    if "外國文" in subject:
        key = "外國文（兼試移民專業英文）"
    elif "國文" in subject:
        key = "國文（作文、公文與測驗）"
    elif "法學知識" in subject:
        key = "法學知識與英文"
    elif "入出國" in subject and "概要" in subject:
        key = "入出國及移民法規概要"
    elif "入出國" in subject:
        key = "入出國及移民法規"
    elif "國土安全" in subject and "概要" in subject:
        key = "國土安全概要與移民政策概要"
    elif "國土安全與移民" in subject:
        key = "國土安全與移民政策"
    elif "國境執法" in subject and "概要" in subject:
        key = "國境執法概要與刑事法概要"
    elif "國境執法" in subject:
        key = "國境執法與刑事法"
    elif "行政法" in subject and "概要" in subject:
        key = "行政法概要"
    elif "行政法" in subject and "研究" in subject:
        key = "行政法研究"
    elif "行政法" in subject:
        key = "行政法"
    elif "憲法與英文" in subject:
        key = "憲法與英文"
    elif "國土安全與國境" in subject:
        key = "國土安全與國境執法研究"
    elif "移民情勢" in subject:
        key = "移民情勢與移民政策分析研究"
    else:
        key = subject
    subject_counts[key] += len(items)
    subject_files[key] += 1

print("\n空白 stem 依科目分佈:")
for k, v in sorted(subject_counts.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v} 題（{subject_files[k]} 個檔案）")

# 看每個檔案的空白 stem 題號模式
print("\n" + "=" * 80)
print("  各檔案空白 stem 詳細題號")
print("=" * 80)

for rel, items in sorted(empty_stem_files.items()):
    numbers = [n for _, n, _ in items]
    types = set(t for _, _, t in items)
    total_q = None
    filepath = os.path.join(TARGET_DIR, rel)
    with open(filepath, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    total_q = len(data.get("questions", []))
    choice_count = sum(1 for q in data.get("questions", []) if q.get("type") == "choice")
    print(f"\n  {rel}")
    print(f"    總題數: {total_q}, 選擇題: {choice_count}, 空白stem: {len(items)}")
    print(f"    空白題號: {numbers} (type: {types})")

# ========================================
# 2. 選項不完整的詳細分析
# ========================================
print("\n" + "=" * 80)
print("  選項不完整詳細分析")
print("=" * 80)

for filepath in files:
    rel = os.path.relpath(filepath, TARGET_DIR)
    with open(filepath, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    for idx, q in enumerate(data.get("questions", [])):
        if q.get("type") != "choice":
            continue
        options = q.get("options", {})
        if not isinstance(options, dict):
            continue
        opt_keys = set(options.keys())
        expected = {"A", "B", "C", "D"}
        if opt_keys != expected:
            missing = expected - opt_keys
            extra = opt_keys - expected
            print(f"\n  {rel}")
            print(f"    第 {q.get('number','?')} 題: 現有選項 {sorted(opt_keys)}, 缺少 {sorted(missing)}")
            stem = q.get("stem", "")[:100]
            print(f"    題目: {stem}...")
            # 顯示現有選項
            for k in sorted(options.keys()):
                val = options[k][:80] if options[k] else "(空)"
                print(f"    {k}: {val}")

# ========================================
# 3. 題號跳號詳細
# ========================================
print("\n" + "=" * 80)
print("  題號跳號/重複詳細分析")
print("=" * 80)

for filepath in files:
    rel = os.path.relpath(filepath, TARGET_DIR)
    with open(filepath, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    choice_numbers = []
    for q in data.get("questions", []):
        if q.get("type") != "choice":
            continue
        n = q.get("number")
        if isinstance(n, int):
            choice_numbers.append(n)
        elif isinstance(n, str) and n.isdigit():
            choice_numbers.append(int(n))

    if not choice_numbers:
        continue

    sorted_nums = sorted(choice_numbers)
    problems = []

    if sorted_nums[0] != 1:
        problems.append(f"起始題號: {sorted_nums[0]}")

    for i in range(1, len(sorted_nums)):
        d = sorted_nums[i] - sorted_nums[i-1]
        if d == 0:
            problems.append(f"重複: {sorted_nums[i]}")
        elif d > 1:
            gaps = list(range(sorted_nums[i-1]+1, sorted_nums[i]))
            problems.append(f"跳號: {sorted_nums[i-1]}->{sorted_nums[i]} (缺{gaps})")

    from collections import Counter
    dups = {k: v for k, v in Counter(choice_numbers).items() if v > 1}
    if dups:
        for num, cnt in dups.items():
            problems.append(f"重複題號 {num} 出現 {cnt} 次")

    if problems:
        print(f"\n  {rel}")
        print(f"    選擇題題號範圍: {sorted_nums[0]}-{sorted_nums[-1]}, 共 {len(choice_numbers)} 題")
        for p in problems:
            print(f"    {p}")

# ========================================
# 4. metadata 格式差異分析
# ========================================
print("\n" + "=" * 80)
print("  metadata 格式差異分析")
print("=" * 80)

meta_patterns = defaultdict(list)
for filepath in files:
    rel = os.path.relpath(filepath, TARGET_DIR)
    with open(filepath, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    meta = data.get("metadata", {})
    key = tuple(sorted(meta.keys()))
    meta_patterns[key].append(rel)

print(f"\n共有 {len(meta_patterns)} 種 metadata 格式:")
for pattern, file_list in sorted(meta_patterns.items(), key=lambda x: -len(x[1])):
    print(f"\n  欄位: {list(pattern)} ({len(file_list)} 個檔案)")
    for f in file_list[:3]:
        print(f"    例: {f}")
    if len(file_list) > 3:
        print(f"    ... 還有 {len(file_list) - 3} 個")

# ========================================
# 5. 對比行政警察學系的格式差異
# ========================================
print("\n" + "=" * 80)
print("  國境警察學系移民組 vs 行政警察學系 格式差異")
print("=" * 80)

REF_DIR = "C:/Users/User/Desktop/考古題下載/考古題庫/行政警察學系"
ref_files = glob.glob(os.path.join(REF_DIR, "**", "試題.json"), recursive=True)

ref_has_exam_name = 0
ref_has_year = 0
ref_has_category = 0
ref_has_total_questions = 0
imm_has_exam_name = 0
imm_has_year = 0
imm_has_category = 0
imm_has_total_questions = 0

for f in ref_files:
    with open(f, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if "exam_name" in data.get("metadata", {}): ref_has_exam_name += 1
    if "year" in data: ref_has_year += 1
    if "category" in data: ref_has_category += 1
    if "total_questions" in data: ref_has_total_questions += 1

for f in files:
    with open(f, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if "exam_name" in data.get("metadata", {}): imm_has_exam_name += 1
    if "year" in data: imm_has_year += 1
    if "category" in data: imm_has_category += 1
    if "total_questions" in data: imm_has_total_questions += 1

print(f"\n  {'欄位':<30} {'行政警察學系':<20} {'國境警察學系移民組':<20}")
print(f"  {'-'*70}")
print(f"  {'metadata.exam_name':<30} {ref_has_exam_name}/{len(ref_files):<20} {imm_has_exam_name}/{len(files):<20}")
print(f"  {'頂層 year':<30} {ref_has_year}/{len(ref_files):<20} {imm_has_year}/{len(files):<20}")
print(f"  {'頂層 category':<30} {ref_has_category}/{len(ref_files):<20} {imm_has_category}/{len(files):<20}")
print(f"  {'頂層 total_questions':<30} {ref_has_total_questions}/{len(ref_files):<20} {imm_has_total_questions}/{len(files):<20}")
