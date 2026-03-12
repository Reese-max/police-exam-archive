#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
deep_audit.py — 考古題庫 JSON 全面品質掃描（二次審計）
"""

import json
import os
import re
import sys
from collections import defaultdict, Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BASE_DIR = PROJECT_ROOT / "考古題庫"

# ── 嚴重度分類 ──
issues = {
    "P0": [],  # 嚴重：資料遺失或完全錯誤
    "P1": [],  # 中度：資料不完整但可用
    "P2": [],  # 輕微：格式問題或可改進
    "INFO": [],  # 統計資訊和觀察
}

# ── 統計計數器 ──
stats = {
    "total_files": 0,
    "total_questions": 0,
    "total_choice": 0,
    "total_essay": 0,
    "total_other_type": 0,
    "choice_with_options": 0,
    "choice_without_options": 0,
    "choice_with_answer": 0,
    "choice_without_answer": 0,
    "choice_with_valid_answer": 0,
    "choice_answer_placeholder": 0,
    "files_load_ok": 0,
    "files_load_fail": 0,
    "year_dist": Counter(),
    "category_dist": Counter(),
    "subject_dist": Counter(),
    "options_count_dist": Counter(),
}


def add_issue(severity, file_path, description, count=1):
    rel = str(file_path).replace(str(BASE_DIR), "考古題庫")
    issues[severity].append({
        "file": rel,
        "desc": description,
        "count": count,
    })


def extract_path_parts(json_path):
    """從路徑中提取學系、年份、科目"""
    parts = json_path.relative_to(BASE_DIR).parts
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    return None, None, None


def check_garbled_text(text):
    """檢查是否有明顯的亂碼或 OCR 錯誤"""
    if not text:
        return False
    # 連續多個特殊符號
    if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]{2,}', text):
        return True
    # 大量連續問號或替換字元
    if re.search(r'[�\ufffd]{2,}', text):
        return True
    return False


def check_exam_metadata_residual(text):
    """檢查 essay stem 中是否有殘留的考試 metadata"""
    patterns = [
        r'乙、測驗題',
        r'甲、申論題',
        r'代號[:：]\s*\d',
        r'頁次[:：]\s*\d',
        r'考\s*試\s*別',
        r'類\s*科\s*別',
        r'科\s*目',
        r'考試時間',
        r'座號',
        r'※注意',
        r'全\s*一\s*張',
        r'全\s*二\s*張',
        r'背面尚有試題',
        r'請接背面',
        r'調查局調查人員',
        r'司法人員',
    ]
    found = []
    for p in patterns:
        if re.search(p, text):
            found.append(p)
    return found


def parse_expected_choice_count(notes):
    """從 notes 中解析預期的選擇題數量"""
    if not notes:
        return None
    joined = " ".join(notes) if isinstance(notes, list) else str(notes)
    # 匹配 "共N題" 或 "共 N 題"
    m = re.search(r'共\s*(\d+)\s*題', joined)
    if m:
        return int(m.group(1))
    return None


def notes_mention_essay(notes):
    """notes 是否提到申論題"""
    if not notes:
        return False
    joined = " ".join(notes) if isinstance(notes, list) else str(notes)
    return '申論' in joined or '作文' in joined or '公文' in joined


def notes_mention_choice(notes):
    """notes 是否提到選擇/測驗題"""
    if not notes:
        return False
    joined = " ".join(notes) if isinstance(notes, list) else str(notes)
    return '選擇' in joined or '測驗' in joined or '2B' in joined or '試卡' in joined


# ── 中文數字轉換 ──
CN_NUM_MAP = {
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
    '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15,
    '十六': 16, '十七': 17, '十八': 18, '十九': 19, '二十': 20,
}


def cn_to_int(cn):
    if cn in CN_NUM_MAP:
        return CN_NUM_MAP[cn]
    return None


# ══════════════════════════════════════════════════════
#  主要掃描邏輯
# ══════════════════════════════════════════════════════

all_data = {}  # {file_path: parsed_json}
cross_check = defaultdict(list)  # {(year, subject): [(category, file_path, data)]}

json_files = sorted(BASE_DIR.rglob("試題.json"))
stats["total_files"] = len(json_files)

print(f"=== 開始掃描：共 {len(json_files)} 個 JSON 檔案 ===\n")

for jf in json_files:
    category, year, subject = extract_path_parts(jf)

    # ── 1. 基本結構檢查：能否載入 ──
    try:
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)
        stats["files_load_ok"] += 1
    except Exception as e:
        stats["files_load_fail"] += 1
        add_issue("P0", jf, f"JSON 載入失敗: {e}")
        continue

    all_data[jf] = data

    # ── 年份/學系統計 ──
    if year:
        stats["year_dist"][year] += 1
    if category:
        stats["category_dist"][category] += 1
    if subject:
        stats["subject_dist"][subject] += 1

    # ── 1b. 必要欄位檢查 ──
    questions = data.get("questions")
    metadata = data.get("metadata", {})
    notes = data.get("notes", [])

    if questions is None:
        add_issue("P0", jf, "缺少 questions 欄位")
        continue
    if not isinstance(questions, list):
        add_issue("P0", jf, f"questions 欄位不是陣列，而是 {type(questions).__name__}")
        continue
    if len(questions) == 0:
        add_issue("P0", jf, "questions 陣列為空（0 題）")
        continue

    # metadata 欄位
    if not metadata:
        add_issue("P2", jf, "缺少 metadata 欄位")

    # ── 跨學系追蹤 ──
    if year and subject:
        cross_check[(year, subject)].append((category, jf, data))

    # ── 分類題目 ──
    choice_qs = [q for q in questions if q.get("type") == "choice"]
    essay_qs = [q for q in questions if q.get("type") == "essay"]
    other_qs = [q for q in questions if q.get("type") not in ("choice", "essay")]

    stats["total_questions"] += len(questions)
    stats["total_choice"] += len(choice_qs)
    stats["total_essay"] += len(essay_qs)
    stats["total_other_type"] += len(other_qs)

    if other_qs:
        types = set(q.get("type") for q in other_qs)
        add_issue("P1", jf, f"存在非 choice/essay 的題目類型: {types}，共 {len(other_qs)} 題", len(other_qs))

    # ══════════════════════════════════════
    #  2. 選擇題完整性
    # ══════════════════════════════════════
    for q in choice_qs:
        qnum = q.get("number", "?")

        # stem
        stem = q.get("stem", "")
        if not stem or not stem.strip():
            add_issue("P0", jf, f"選擇題 #{qnum} 缺少 stem（題幹為空）")

        # options
        options = q.get("options")
        if options is None or options == {}:
            stats["choice_without_options"] += 1
            add_issue("P0", jf, f"選擇題 #{qnum} 缺少 options 欄位或為空")
        elif isinstance(options, dict):
            stats["choice_with_options"] += 1
            opt_keys = sorted(options.keys())
            stats["options_count_dist"][len(opt_keys)] += 1

            # 檢查選項 key
            standard_4 = ["A", "B", "C", "D"]
            if opt_keys != standard_4:
                if set(opt_keys) - {"A", "B", "C", "D", "E", "F"}:
                    add_issue("P1", jf, f"選擇題 #{qnum} 選項 key 異常: {opt_keys}")
                elif len(opt_keys) < 4:
                    add_issue("P2", jf, f"選擇題 #{qnum} 選項不足 4 個: {opt_keys}")
                elif len(opt_keys) > 4:
                    add_issue("P2", jf, f"選擇題 #{qnum} 選項超過 4 個: {opt_keys}")

            # 檢查選項值
            for k, v in options.items():
                if v == "[待補]" or v == "_todo":
                    add_issue("P1", jf, f"選擇題 #{qnum} 選項 {k} 為佔位值: {v}")
                if not v or not str(v).strip():
                    add_issue("P1", jf, f"選擇題 #{qnum} 選項 {k} 為空值")
        else:
            stats["choice_without_options"] += 1
            add_issue("P0", jf, f"選擇題 #{qnum} options 不是 dict，而是 {type(options).__name__}")

        # answer
        answer = q.get("answer")
        if answer is None or answer == "":
            stats["choice_without_answer"] += 1
            add_issue("P1", jf, f"選擇題 #{qnum} 缺少 answer")
        elif answer == "[待補]" or answer == "_todo":
            stats["choice_answer_placeholder"] += 1
            stats["choice_without_answer"] += 1
            add_issue("P1", jf, f"選擇題 #{qnum} answer 為佔位值: {answer}")
        else:
            stats["choice_with_answer"] += 1
            # 驗證 answer 是否合理
            valid_answers = {"A", "B", "C", "D", "E", "F"}
            # 也允許複合答案如 "C或D", "AB", "ACD" 等
            ans_str = str(answer).strip()
            is_valid = False
            if ans_str in valid_answers:
                is_valid = True
            elif re.match(r'^[A-F]或[A-F]$', ans_str):
                is_valid = True
            elif re.match(r'^[A-F]{2,}$', ans_str):
                is_valid = True
            elif re.match(r'^[A-F](,[A-F])+$', ans_str):
                is_valid = True
            elif re.match(r'^[A-F](、[A-F])+$', ans_str):
                is_valid = True
            elif re.match(r'^送分$', ans_str):
                is_valid = True
            elif re.match(r'^一律給分$', ans_str):
                is_valid = True

            if is_valid:
                stats["choice_with_valid_answer"] += 1
                # 進一步檢查 answer 是否在 options keys 中
                if options and isinstance(options, dict):
                    if ans_str in valid_answers and ans_str not in options:
                        add_issue("P1", jf, f"選擇題 #{qnum} answer={ans_str} 不在 options keys {list(options.keys())} 中")
            else:
                add_issue("P2", jf, f"選擇題 #{qnum} answer 值不尋常: '{ans_str}'")

        # 亂碼檢查
        if stem and check_garbled_text(stem):
            add_issue("P1", jf, f"選擇題 #{qnum} stem 可能含亂碼")

        # passage 欄位
        passage = q.get("passage")
        if passage and not passage.strip():
            add_issue("P2", jf, f"選擇題 #{qnum} passage 欄位存在但為空字串")

    # ══════════════════════════════════════
    #  3. 申論題完整性
    # ══════════════════════════════════════
    for q in essay_qs:
        qnum = q.get("number", "?")
        stem = q.get("stem", "")
        if not stem or not stem.strip():
            add_issue("P0", jf, f"申論題 #{qnum} 缺少 stem（題幹為空）")
        else:
            # 殘留考試 metadata
            residuals = check_exam_metadata_residual(stem)
            if residuals:
                add_issue("P2", jf, f"申論題 #{qnum} stem 中可能殘留考試 metadata: {residuals}")
            # 亂碼
            if check_garbled_text(stem):
                add_issue("P1", jf, f"申論題 #{qnum} stem 可能含亂碼")

    # ══════════════════════════════════════
    #  4. 題號連續性
    # ══════════════════════════════════════

    # 選擇題題號連續性
    if choice_qs:
        choice_nums = []
        for q in choice_qs:
            n = q.get("number")
            if isinstance(n, int):
                choice_nums.append(n)
            elif isinstance(n, str):
                try:
                    choice_nums.append(int(n))
                except ValueError:
                    pass

        if choice_nums:
            choice_nums_sorted = sorted(choice_nums)
            expected = list(range(choice_nums_sorted[0], choice_nums_sorted[-1] + 1))
            missing = sorted(set(expected) - set(choice_nums_sorted))
            duplicates = [n for n, cnt in Counter(choice_nums).items() if cnt > 1]

            if missing:
                add_issue("P1", jf, f"選擇題題號缺漏: {missing}（範圍 {choice_nums_sorted[0]}~{choice_nums_sorted[-1]}）", len(missing))
            if duplicates:
                add_issue("P1", jf, f"選擇題題號重複: {duplicates}", len(duplicates))

            # 檢查是否從 1 開始
            if choice_nums_sorted[0] != 1:
                add_issue("P2", jf, f"選擇題起始題號非 1，而是 {choice_nums_sorted[0]}")

    # 申論題題號合理性
    if essay_qs:
        essay_nums = []
        for q in essay_qs:
            n = q.get("number")
            if isinstance(n, str):
                cn_val = cn_to_int(n)
                if cn_val is not None:
                    essay_nums.append(cn_val)
            elif isinstance(n, int):
                essay_nums.append(n)

        if essay_nums:
            essay_sorted = sorted(essay_nums)
            expected_essay = list(range(essay_sorted[0], essay_sorted[-1] + 1))
            missing_essay = sorted(set(expected_essay) - set(essay_sorted))
            dup_essay = [n for n, cnt in Counter(essay_nums).items() if cnt > 1]

            if missing_essay:
                add_issue("P2", jf, f"申論題題號缺漏: {missing_essay}", len(missing_essay))
            if dup_essay:
                add_issue("P1", jf, f"申論題題號重複: {dup_essay}", len(dup_essay))

    # ══════════════════════════════════════
    #  5. Notes 與實際題目一致性
    # ══════════════════════════════════════
    expected_count = parse_expected_choice_count(notes)
    actual_choice_count = len(choice_qs)

    if expected_count is not None and expected_count != actual_choice_count:
        add_issue("P1", jf,
                  f"Notes 聲稱共 {expected_count} 題選擇，實際只有 {actual_choice_count} 題",
                  abs(expected_count - actual_choice_count))

    if notes_mention_essay(notes) and len(essay_qs) == 0:
        add_issue("P1", jf, "Notes 提到申論/作文/公文，但沒有 essay 類型題目")

    if notes_mention_choice(notes) and len(choice_qs) == 0:
        add_issue("P1", jf, "Notes 提到選擇/測驗/2B鉛筆，但沒有 choice 類型題目")

    # ══════════════════════════════════════
    #  7. 資料品質（_todo, [待補] 等）
    # ══════════════════════════════════════
    # 已在上面檢查中處理，這裡做額外的全域掃描
    raw_text = json.dumps(data, ensure_ascii=False)
    todo_count = raw_text.count("_todo")
    placeholder_count = raw_text.count("[待補]")
    if todo_count > 0:
        add_issue("P1", jf, f"檔案中存在 {todo_count} 處 _todo 佔位標記", todo_count)
    if placeholder_count > 0:
        # 已在選擇題檢查中個別列出，這裡記錄總數
        pass  # 避免重複

# ══════════════════════════════════════════════════════
#  6. 跨學系一致性（同年同科目）
# ══════════════════════════════════════════════════════
print("=== 跨學系一致性檢查 ===\n")

# 共用科目清單
SHARED_SUBJECTS = [
    "國文", "中華民國憲法與警察專業英文", "警察法規", "警察情境實務",
    "國文(作文、公文與測驗)",
]

cross_check_count = 0
for (year, subject), entries in sorted(cross_check.items()):
    if len(entries) < 2:
        continue

    # 檢查是否為可能的共用科目
    is_shared = any(s in subject for s in SHARED_SUBJECTS)
    if not is_shared:
        continue

    cross_check_count += 1

    # 比較各學系的選擇題
    choice_sets = {}
    answer_sets = {}
    for cat, fp, d in entries:
        qs = d.get("questions", [])
        cqs = [q for q in qs if q.get("type") == "choice"]
        # 用 (number, stem前30字) 做指紋
        fingerprints = set()
        ans_map = {}
        for q in cqs:
            n = q.get("number", "?")
            s = (q.get("stem") or "")[:50]
            fingerprints.add((str(n), s))
            ans_map[str(n)] = q.get("answer")
        choice_sets[cat] = fingerprints
        answer_sets[cat] = ans_map

    # 比較
    cats = list(choice_sets.keys())
    for i in range(len(cats)):
        for j in range(i + 1, len(cats)):
            c1, c2 = cats[i], cats[j]
            s1, s2 = choice_sets[c1], choice_sets[c2]

            if len(s1) == 0 or len(s2) == 0:
                continue

            # 題目指紋相同度
            common = s1 & s2
            if len(s1) > 0 and len(s2) > 0 and len(common) / max(len(s1), len(s2)) > 0.8:
                # 看起來是相同考卷，檢查答案差異
                a1 = answer_sets[c1]
                a2 = answer_sets[c2]
                # 一邊有答案另一邊沒有
                for num in a1:
                    if num in a2:
                        if a1[num] and not a2[num]:
                            add_issue("P2", f"{year}/{subject}",
                                      f"跨學系差異: {c1} 第{num}題有答案({a1[num]})，但 {c2} 沒有")
                        elif a2[num] and not a1[num]:
                            add_issue("P2", f"{year}/{subject}",
                                      f"跨學系差異: {c2} 第{num}題有答案({a2[num]})，但 {c1} 沒有")
            elif len(s1) != len(s2) and len(s1) > 0 and len(s2) > 0:
                # 題數不同
                if abs(len(s1) - len(s2)) > 5:
                    add_issue("P2", f"{year}/{subject}",
                              f"跨學系題數差異較大: {c1}={len(s1)}題 vs {c2}={len(s2)}題")


# ══════════════════════════════════════════════════════
#  輸出報告
# ══════════════════════════════════════════════════════
print("=" * 80)
print("  考古題庫 JSON 全面品質掃描報告（二次審計）")
print("=" * 80)
print()

# ── 統計摘要 ──
print("━" * 60)
print("  [INFO] 統計摘要")
print("━" * 60)
print(f"  總檔案數:         {stats['total_files']}")
print(f"  成功載入:         {stats['files_load_ok']}")
print(f"  載入失敗:         {stats['files_load_fail']}")
print(f"  總題數:           {stats['total_questions']}")
print(f"  選擇題:           {stats['total_choice']}")
print(f"  申論題:           {stats['total_essay']}")
print(f"  其他類型:         {stats['total_other_type']}")
print()
print(f"  選擇題有 options: {stats['choice_with_options']}")
print(f"  選擇題無 options: {stats['choice_without_options']}")
print(f"  選擇題有 answer:  {stats['choice_with_answer']}")
print(f"  選擇題無 answer:  {stats['choice_without_answer']}")
print(f"  answer 為佔位值:  {stats['choice_answer_placeholder']}")
print(f"  answer 值合法:    {stats['choice_with_valid_answer']}")
print()

print("  ── 選項數量分布 ──")
for k in sorted(stats["options_count_dist"]):
    print(f"    {k} 個選項: {stats['options_count_dist'][k]} 題")
print()

print("  ── 年份分布 ──")
for y in sorted(stats["year_dist"]):
    print(f"    {y}: {stats['year_dist'][y]} 個檔案")
print()

print("  ── 學系分布（前 20）──")
for cat, cnt in stats["category_dist"].most_common(20):
    print(f"    {cat}: {cnt} 個檔案")
print()

print(f"  跨學系一致性檢查組數: {cross_check_count}")
print()

# ── 按嚴重度輸出 ──
for severity in ["P0", "P1", "P2", "INFO"]:
    items = issues[severity]
    if not items:
        print(f"{'━' * 60}")
        print(f"  [{severity}] 無問題發現")
        print(f"{'━' * 60}")
        print()
        continue

    # 聚合相同描述的問題
    agg = defaultdict(list)
    for item in items:
        agg[item["desc"]].append(item["file"])

    print(f"{'━' * 60}")
    print(f"  [{severity}] 共 {len(items)} 個問題（{len(agg)} 類）")
    print(f"{'━' * 60}")

    for idx, (desc, files) in enumerate(sorted(agg.items()), 1):
        print(f"\n  {severity}-{idx:03d}: {desc}")
        print(f"         影響檔案數: {len(files)}")
        if len(files) <= 10:
            for fp in files:
                print(f"           - {fp}")
        else:
            for fp in files[:5]:
                print(f"           - {fp}")
            print(f"           ... 及其他 {len(files) - 5} 個檔案")
    print()

# ── 去重後的重點摘要（按檔案聚合） ──
print("━" * 60)
print("  [重點摘要] 缺少 options 的選擇題 —— 按檔案聚合")
print("━" * 60)

files_missing_opts = defaultdict(list)
for item in issues["P0"]:
    if "缺少 options" in item["desc"]:
        # 從描述中提取題號
        m = re.search(r'#(\S+)', item["desc"])
        if m:
            files_missing_opts[item["file"]].append(m.group(1))

print(f"\n  共 {len(files_missing_opts)} 個獨立檔案受影響，合計 {stats['choice_without_options']} 題缺 options")
print()
for fp in sorted(files_missing_opts):
    nums = files_missing_opts[fp]
    print(f"  {fp}")
    print(f"    缺 options 題號: {nums} ({len(nums)} 題)")
print()

# ── answer="*" 統計 ──
print("━" * 60)
print("  [重點摘要] answer='*' 的選擇題（可能為「送分題」或「刪題」）")
print("━" * 60)

star_files = defaultdict(list)
for item in issues["P2"]:
    if "answer 值不尋常: '*'" in item["desc"]:
        m = re.search(r'#(\S+)', item["desc"])
        if m:
            star_files[item["file"]].append(m.group(1))

star_total = sum(len(v) for v in star_files.values())
print(f"\n  共 {len(star_files)} 個獨立檔案，合計 {star_total} 題 answer='*'")
print("  注意: '*' 通常表示該題被考選部公告為送分/刪題")
print()

# ── Notes vs 實際題數不符 ──
print("━" * 60)
print("  [重點摘要] Notes 宣稱題數與實際不符")
print("━" * 60)
notes_mismatch = [item for item in issues["P1"] if "Notes 聲稱共" in item["desc"]]
if notes_mismatch:
    print(f"\n  共 {len(notes_mismatch)} 個檔案")
    for item in notes_mismatch:
        print(f"  {item['file']}: {item['desc']}")
else:
    print("\n  無")
print()

# ── Notes 提到申論但無 essay 題 ──
print("━" * 60)
print("  [重點摘要] Notes 提到申論/作文但無 essay 題（多為 114 年新格式）")
print("━" * 60)
no_essay = [item for item in issues["P1"] if "Notes 提到申論" in item["desc"]]
if no_essay:
    print(f"\n  共 {len(no_essay)} 個檔案")
    for item in no_essay[:10]:
        print(f"  {item['file']}")
    if len(no_essay) > 10:
        print(f"  ... 及其他 {len(no_essay) - 10} 個檔案")
else:
    print("\n  無")
print()

# ── 申論題號重複 ──
print("━" * 60)
print("  [重點摘要] 申論題題號重複")
print("━" * 60)
dup_essay_items = [item for item in issues["P1"] if "申論題題號重複" in item["desc"]]
if dup_essay_items:
    print(f"\n  共 {len(dup_essay_items)} 個檔案")
    for item in dup_essay_items:
        print(f"  {item['file']}: {item['desc']}")
else:
    print("\n  無")
print()

# ── 選項只有 3 個的題 + answer 不在 options 中 ──
print("━" * 60)
print("  [重點摘要] 選項數異常 + answer 不在 options keys 中")
print("━" * 60)
opt_anomaly = [item for item in issues["P2"] if "選項不足" in item["desc"]]
ans_not_in_opts = [item for item in issues["P1"] if "不在 options keys" in item["desc"]]
if opt_anomaly or ans_not_in_opts:
    for item in opt_anomaly + ans_not_in_opts:
        print(f"  {item['file']}: {item['desc']}")
else:
    print("  無")
print()

# ── 總結 ──
total_issues = sum(len(v) for v in issues.values())
print("=" * 80)
print("  總結")
print("=" * 80)
print(f"  P0 嚴重: {len(issues['P0'])} 個（{len(files_missing_opts)} 個獨立檔案缺 options）")
print(f"  P1 中度: {len(issues['P1'])} 個")
print(f"  P2 輕微: {len(issues['P2'])} 個（含 {star_total} 題 answer='*'）")
print(f"  INFO:    {len(issues['INFO'])} 個")
print(f"  合計:    {total_issues} 個")
print()

# 完整度計算
choice_complete = stats['choice_with_options']
choice_total = stats['total_choice']
pct = choice_complete / choice_total * 100 if choice_total else 0
print(f"  選擇題 options 完整率: {choice_complete}/{choice_total} = {pct:.2f}%")
ans_complete = stats['choice_with_valid_answer']
pct2 = ans_complete / choice_total * 100 if choice_total else 0
print(f"  選擇題 answer 合法率:  {ans_complete}/{choice_total} = {pct2:.2f}%")
print()

if len(issues["P0"]) == 0:
    print("  [PASS] 無嚴重問題（P0），資料庫基本結構完整。")
else:
    print(f"  [FAIL] 存在 {len(issues['P0'])} 個嚴重問題（P0），需要優先修復！")

if len(issues["P1"]) == 0:
    print("  [PASS] 無中度問題（P1），資料完整性良好。")
else:
    print(f"  [WARN] 存在 {len(issues['P1'])} 個中度問題（P1），建議修復。")

print()
print("=" * 80)
print("  報告結束")
print("=" * 80)
