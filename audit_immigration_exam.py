# -*- coding: utf-8 -*-
"""
國境警察學系移民組題庫 JSON 結構審計腳本
掃描 考古題庫/國境警察學系移民組/ 下所有 試題.json，進行完整的結構與 schema 檢查
"""

import json
import glob
import os
import re
from collections import defaultdict, Counter
from datetime import datetime

BASE_DIR = "C:/Users/User/Desktop/考古題下載/考古題庫"
TARGET_DIR = os.path.join(BASE_DIR, "國境警察學系移民組")
REF_DIR = os.path.join(BASE_DIR, "行政警察學系")

# ============================================================
# 問題收集器
# ============================================================
class Issue:
    def __init__(self, severity, category, file_path, detail):
        self.severity = severity  # CRITICAL, WARNING, INFO
        self.category = category
        self.file_path = file_path
        self.detail = detail

issues = []
stats = defaultdict(int)

def add_issue(severity, category, file_path, detail):
    issues.append(Issue(severity, category, file_path, detail))
    stats[f"{severity}_{category}"] += 1

# ============================================================
# 1. 先分析行政警察學系的 JSON 作為參考格式
# ============================================================
def analyze_reference_format():
    """分析行政警察學系 JSON 了解標準格式"""
    ref_files = glob.glob(os.path.join(REF_DIR, "**", "試題.json"), recursive=True)
    print(f"=== 參考格式分析：行政警察學系 ({len(ref_files)} 個 JSON) ===\n")

    ref_top_keys = Counter()
    ref_metadata_keys = Counter()
    ref_question_keys = Counter()
    ref_question_types = Counter()

    for f in ref_files:
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            for k in data.keys():
                ref_top_keys[k] += 1
            if 'metadata' in data and isinstance(data['metadata'], dict):
                for k in data['metadata'].keys():
                    ref_metadata_keys[k] += 1
            if 'questions' in data and isinstance(data['questions'], list):
                for q in data['questions']:
                    if isinstance(q, dict):
                        for k in q.keys():
                            ref_question_keys[k] += 1
                        ref_question_types[q.get('type', 'MISSING')] += 1
        except Exception:
            pass

    print("  頂層欄位出現次數:")
    for k, v in ref_top_keys.most_common():
        print(f"    {k}: {v}/{len(ref_files)}")
    print("\n  metadata 欄位出現次數:")
    for k, v in ref_metadata_keys.most_common():
        print(f"    {k}: {v}/{len(ref_files)}")
    print("\n  question 欄位出現次數:")
    for k, v in ref_question_keys.most_common():
        print(f"    {k}: {v}")
    print("\n  question type 分佈:")
    for k, v in ref_question_types.most_common():
        print(f"    {k}: {v}")
    print()

    return ref_top_keys, ref_metadata_keys, ref_question_keys

# ============================================================
# 2. 主要審計邏輯
# ============================================================
def audit_all_files():
    """掃描所有國境警察學系移民組 JSON 檔案"""
    files = sorted(glob.glob(os.path.join(TARGET_DIR, "**", "試題.json"), recursive=True))
    print(f"=== 開始審計：國境警察學系移民組 ({len(files)} 個 JSON) ===\n")

    total_questions = 0
    total_choice = 0
    total_essay = 0
    total_other = 0
    files_by_year = defaultdict(list)
    files_with_errors = []

    # 統計每年每等級的科目數
    year_level_subjects = defaultdict(lambda: defaultdict(list))

    for filepath in files:
        rel_path = os.path.relpath(filepath, TARGET_DIR)
        parts = rel_path.replace("\\", "/").split("/")
        year_str = parts[0] if len(parts) > 0 else "unknown"
        subject_str = parts[1] if len(parts) > 1 else "unknown"

        files_by_year[year_str].append(filepath)

        # 解析等級
        level_match = re.match(r'\[([^\]]+)\]', subject_str)
        level = level_match.group(1) if level_match else "unknown"
        year_level_subjects[year_str][level].append(subject_str)

        # ---- 檢查 1: JSON 合法性 ----
        try:
            with open(filepath, 'r', encoding='utf-8') as fh:
                raw = fh.read()
        except Exception as e:
            add_issue("CRITICAL", "檔案讀取失敗", rel_path, str(e))
            files_with_errors.append(rel_path)
            continue

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            add_issue("CRITICAL", "JSON解析失敗", rel_path, f"行 {e.lineno}, 欄 {e.colno}: {e.msg}")
            files_with_errors.append(rel_path)
            continue

        if not isinstance(data, dict):
            add_issue("CRITICAL", "頂層結構錯誤", rel_path, f"頂層不是 dict，而是 {type(data).__name__}")
            continue

        # ---- 檢查 2: Schema 一致性 (頂層欄位) ----
        top_keys = set(data.keys())
        expected_top = {"metadata", "notes", "sections", "questions"}
        optional_top = {"year", "category", "subject", "level", "original_subject",
                        "source_pdf", "file_type", "total_questions", "exam_name"}

        missing_top = expected_top - top_keys
        extra_top = top_keys - expected_top - optional_top

        for mk in missing_top:
            if mk == "sections":
                add_issue("INFO", "頂層欄位缺少", rel_path, f"缺少 '{mk}' 欄位（非必要）")
            elif mk == "notes":
                add_issue("WARNING", "頂層欄位缺少", rel_path, f"缺少 '{mk}' 欄位")
            else:
                add_issue("CRITICAL", "頂層欄位缺少", rel_path, f"缺少必要欄位 '{mk}'")

        for ek in extra_top:
            add_issue("INFO", "頂層額外欄位", rel_path, f"存在額外欄位 '{ek}'")

        # ---- 檢查 3: metadata 完整性 ----
        metadata = data.get("metadata", {})
        if not isinstance(metadata, dict):
            add_issue("CRITICAL", "metadata格式錯誤", rel_path, f"metadata 不是 dict，而是 {type(metadata).__name__}")
        else:
            # 必要 metadata 欄位
            required_meta = {"subject"}
            recommended_meta = {"level", "exam_time"}
            optional_meta = {"exam_name", "exam_type", "code"}

            for rm in required_meta:
                if rm not in metadata:
                    add_issue("WARNING", "metadata欄位缺少", rel_path, f"metadata 缺少 '{rm}'")
                elif not metadata[rm] or (isinstance(metadata[rm], str) and not metadata[rm].strip()):
                    add_issue("WARNING", "metadata欄位空值", rel_path, f"metadata.{rm} 為空值")

            for rm in recommended_meta:
                if rm not in metadata:
                    add_issue("INFO", "metadata欄位缺少", rel_path, f"metadata 缺少建議欄位 '{rm}'")

            # 檢查 exam_type 是否為年份
            if "exam_type" in metadata:
                et = str(metadata["exam_type"])
                if not re.match(r'^\d{3}$', et):
                    add_issue("INFO", "metadata格式異常", rel_path, f"exam_type='{et}' 非標準三位數年份格式")

            # 檢查 exam_name 是否存在
            if "exam_name" not in metadata and "exam_type" not in metadata:
                add_issue("INFO", "metadata欄位缺少", rel_path, "metadata 缺少 exam_name 和 exam_type")

        # ---- 檢查 4: questions 結構 ----
        questions = data.get("questions", [])
        if not isinstance(questions, list):
            add_issue("CRITICAL", "questions格式錯誤", rel_path, f"questions 不是 list，而是 {type(questions).__name__}")
            continue

        if len(questions) == 0:
            add_issue("CRITICAL", "題目為空", rel_path, "questions 陣列為空，沒有任何題目")
            continue

        total_questions += len(questions)

        choice_questions = []
        essay_questions = []
        other_questions = []

        for idx, q in enumerate(questions):
            if not isinstance(q, dict):
                add_issue("CRITICAL", "題目格式錯誤", rel_path, f"questions[{idx}] 不是 dict")
                continue

            q_type = q.get("type", "MISSING")
            q_number = q.get("number", "MISSING")

            # ---- 檢查 question 必要欄位 ----
            if "number" not in q:
                add_issue("WARNING", "題目缺少number", rel_path, f"questions[{idx}] 缺少 'number' 欄位")

            if "type" not in q:
                add_issue("WARNING", "題目缺少type", rel_path, f"questions[{idx}] 缺少 'type' 欄位")

            if "stem" not in q:
                add_issue("CRITICAL", "題目缺少stem", rel_path, f"questions[{idx}] (number={q_number}) 缺少 'stem' 欄位")
            else:
                stem = q["stem"]
                if not stem or (isinstance(stem, str) and not stem.strip()):
                    add_issue("CRITICAL", "題目stem為空", rel_path, f"questions[{idx}] (number={q_number}) stem 為空白")
                elif isinstance(stem, str) and len(stem.strip()) < 5:
                    add_issue("WARNING", "題目stem過短", rel_path, f"questions[{idx}] (number={q_number}) stem 僅 {len(stem.strip())} 字: '{stem.strip()}'")

            if q_type == "choice":
                choice_questions.append((idx, q))
                total_choice += 1
            elif q_type == "essay":
                essay_questions.append((idx, q))
                total_essay += 1
            elif q_type == "MISSING":
                other_questions.append((idx, q))
                total_other += 1
            else:
                other_questions.append((idx, q))
                total_other += 1
                add_issue("INFO", "未知題目類型", rel_path, f"questions[{idx}] type='{q_type}' 非 choice/essay")

        # ---- 檢查 5: 選擇題專項檢查 ----
        choice_numbers = []
        for idx, q in choice_questions:
            q_number = q.get("number", "?")

            # 答案檢查
            if "answer" not in q:
                add_issue("CRITICAL", "選擇題缺少answer", rel_path, f"第 {q_number} 題 (choice) 缺少 'answer' 欄位")
            else:
                ans = q["answer"]
                if ans is None or (isinstance(ans, str) and not ans.strip()):
                    add_issue("CRITICAL", "選擇題answer為空", rel_path, f"第 {q_number} 題 answer 為空值")
                elif isinstance(ans, str):
                    ans_clean = ans.strip()
                    # 允許 A/B/C/D、複選如 AB/ACD、或特殊標記如「送分」「一律給分」
                    if not re.match(r'^[A-D]{1,4}$', ans_clean):
                        if ans_clean not in ("送分", "一律給分", "刪除", "無答案"):
                            add_issue("WARNING", "選擇題answer格式異常", rel_path,
                                      f"第 {q_number} 題 answer='{ans_clean}' 非標準格式 (A/B/C/D)")

            # 選項檢查
            if "options" not in q:
                add_issue("CRITICAL", "選擇題缺少options", rel_path, f"第 {q_number} 題 (choice) 缺少 'options' 欄位")
            else:
                options = q["options"]
                if not isinstance(options, dict):
                    add_issue("CRITICAL", "選擇題options格式錯誤", rel_path,
                              f"第 {q_number} 題 options 不是 dict，而是 {type(options).__name__}")
                else:
                    opt_keys = set(options.keys())
                    expected_opts = {"A", "B", "C", "D"}

                    if opt_keys != expected_opts:
                        missing_opts = expected_opts - opt_keys
                        extra_opts = opt_keys - expected_opts

                        if missing_opts:
                            # 如果只有 2-3 個選項，可能是特殊題型
                            if len(opt_keys) < 4:
                                add_issue("WARNING", "選項不完整", rel_path,
                                          f"第 {q_number} 題缺少選項 {missing_opts}，僅有 {sorted(opt_keys)}")
                            else:
                                add_issue("WARNING", "選項不完整", rel_path,
                                          f"第 {q_number} 題缺少選項 {missing_opts}")

                        if extra_opts:
                            add_issue("INFO", "選項有額外項", rel_path,
                                      f"第 {q_number} 題有額外選項 {extra_opts}")

                    # 檢查選項值是否為空
                    for opt_key, opt_val in options.items():
                        if opt_val is None or (isinstance(opt_val, str) and not opt_val.strip()):
                            add_issue("WARNING", "選項值為空", rel_path,
                                      f"第 {q_number} 題選項 {opt_key} 為空白")

            # 記錄選擇題題號（用於連續性檢查）
            if isinstance(q_number, int):
                choice_numbers.append(q_number)
            elif isinstance(q_number, str) and q_number.isdigit():
                choice_numbers.append(int(q_number))

        # ---- 檢查 6: 題號連續性 (僅針對選擇題的數字題號) ----
        if choice_numbers:
            choice_numbers_sorted = sorted(choice_numbers)

            # 檢查是否從 1 開始
            if choice_numbers_sorted[0] != 1:
                add_issue("WARNING", "題號不從1開始", rel_path,
                          f"選擇題題號從 {choice_numbers_sorted[0]} 開始（預期從 1 開始）")

            # 檢查連續性
            for i in range(1, len(choice_numbers_sorted)):
                diff = choice_numbers_sorted[i] - choice_numbers_sorted[i-1]
                if diff == 0:
                    add_issue("WARNING", "題號重複", rel_path,
                              f"選擇題題號 {choice_numbers_sorted[i]} 重複出現")
                elif diff > 1:
                    missing_range = list(range(choice_numbers_sorted[i-1]+1, choice_numbers_sorted[i]))
                    if len(missing_range) <= 5:
                        add_issue("WARNING", "題號跳號", rel_path,
                                  f"選擇題題號跳號：{choice_numbers_sorted[i-1]} -> {choice_numbers_sorted[i]}（缺少 {missing_range}）")
                    else:
                        add_issue("WARNING", "題號跳號", rel_path,
                                  f"選擇題題號跳號：{choice_numbers_sorted[i-1]} -> {choice_numbers_sorted[i]}（缺少 {len(missing_range)} 個題號）")

            # 檢查重複（不用排序的原始列表）
            num_counter = Counter(choice_numbers)
            for num, count in num_counter.items():
                if count > 1:
                    add_issue("WARNING", "題號重複", rel_path,
                              f"選擇題題號 {num} 出現 {count} 次")

        # ---- 檢查 7: 申論題檢查 ----
        essay_numbers = []
        chinese_nums = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
                        "七": 7, "八": 8, "九": 9, "十": 10}

        for idx, q in essay_questions:
            q_number = q.get("number", "?")

            # 申論題不應有 options
            if "options" in q and q["options"]:
                add_issue("INFO", "申論題有options", rel_path,
                          f"申論題 {q_number} 不應有 options 欄位")

            # 申論題不需要 answer
            if "answer" in q and q["answer"]:
                add_issue("INFO", "申論題有answer", rel_path,
                          f"申論題 {q_number} 有 answer 欄位（通常不需要）")

            # 記錄題號
            if isinstance(q_number, str) and q_number in chinese_nums:
                essay_numbers.append(chinese_nums[q_number])
            elif isinstance(q_number, int):
                essay_numbers.append(q_number)

        # ---- 檢查 8: total_questions 一致性 ----
        if "total_questions" in data:
            declared_total = data["total_questions"]
            actual_total = len(questions)
            if declared_total != actual_total:
                add_issue("WARNING", "題數不一致", rel_path,
                          f"total_questions 宣告 {declared_total}，實際 {actual_total}")

    # ============================================================
    # 統計彙整
    # ============================================================
    print(f"\n{'='*80}")
    print(f"  國境警察學系移民組題庫 JSON 結構審計報告")
    print(f"  審計時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")

    print(f"【基本統計】")
    print(f"  檔案總數: {len(files)}")
    print(f"  題目總數: {total_questions}")
    print(f"    - 選擇題: {total_choice}")
    print(f"    - 申論題: {total_essay}")
    print(f"    - 其他/未標記: {total_other}")
    print(f"  涵蓋年度: {sorted(files_by_year.keys())}")
    print()

    print(f"【各年度檔案分佈】")
    for year in sorted(files_by_year.keys()):
        count = len(files_by_year[year])
        levels = sorted(year_level_subjects[year].keys())
        level_counts = {l: len(year_level_subjects[year][l]) for l in levels}
        print(f"  {year}: {count} 個檔案 ({level_counts})")
    print()

    # 依嚴重程度分類問題
    critical_issues = [i for i in issues if i.severity == "CRITICAL"]
    warning_issues = [i for i in issues if i.severity == "WARNING"]
    info_issues = [i for i in issues if i.severity == "INFO"]

    print(f"{'='*80}")
    print(f"【問題總覽】")
    print(f"  CRITICAL (嚴重): {len(critical_issues)}")
    print(f"  WARNING  (警告): {len(warning_issues)}")
    print(f"  INFO     (資訊): {len(info_issues)}")
    print(f"  總計: {len(issues)}")
    print(f"{'='*80}\n")

    # ---- CRITICAL ----
    if critical_issues:
        print(f"\n{'='*80}")
        print(f"  CRITICAL 嚴重問題 ({len(critical_issues)} 個)")
        print(f"{'='*80}")

        # 依類別分組
        crit_by_cat = defaultdict(list)
        for i in critical_issues:
            crit_by_cat[i.category].append(i)

        for cat, cat_issues in sorted(crit_by_cat.items()):
            print(f"\n  [{cat}] ({len(cat_issues)} 個)")
            for i in cat_issues[:50]:  # 最多顯示50個
                print(f"    - {i.file_path}")
                print(f"      {i.detail}")
            if len(cat_issues) > 50:
                print(f"    ... 還有 {len(cat_issues) - 50} 個同類問題")

    # ---- WARNING ----
    if warning_issues:
        print(f"\n{'='*80}")
        print(f"  WARNING 警告問題 ({len(warning_issues)} 個)")
        print(f"{'='*80}")

        warn_by_cat = defaultdict(list)
        for i in warning_issues:
            warn_by_cat[i.category].append(i)

        for cat, cat_issues in sorted(warn_by_cat.items()):
            print(f"\n  [{cat}] ({len(cat_issues)} 個)")
            for i in cat_issues[:30]:  # 最多顯示30個
                print(f"    - {i.file_path}")
                print(f"      {i.detail}")
            if len(cat_issues) > 30:
                print(f"    ... 還有 {len(cat_issues) - 30} 個同類問題")

    # ---- INFO ----
    if info_issues:
        print(f"\n{'='*80}")
        print(f"  INFO 資訊 ({len(info_issues)} 個)")
        print(f"{'='*80}")

        info_by_cat = defaultdict(list)
        for i in info_issues:
            info_by_cat[i.category].append(i)

        for cat, cat_issues in sorted(info_by_cat.items()):
            print(f"\n  [{cat}] ({len(cat_issues)} 個)")
            # 只顯示前 10 個
            for i in cat_issues[:10]:
                print(f"    - {i.file_path}")
                print(f"      {i.detail}")
            if len(cat_issues) > 10:
                print(f"    ... 還有 {len(cat_issues) - 10} 個同類問題")

    # ---- 問題類別統計摘要 ----
    print(f"\n{'='*80}")
    print(f"  問題類別統計摘要")
    print(f"{'='*80}")
    all_cats = defaultdict(lambda: {"CRITICAL": 0, "WARNING": 0, "INFO": 0})
    for i in issues:
        all_cats[i.category][i.severity] += 1

    print(f"  {'類別':<30} {'CRITICAL':>10} {'WARNING':>10} {'INFO':>8} {'合計':>8}")
    print(f"  {'-'*66}")
    for cat in sorted(all_cats.keys()):
        c = all_cats[cat]["CRITICAL"]
        w = all_cats[cat]["WARNING"]
        inf = all_cats[cat]["INFO"]
        total = c + w + inf
        print(f"  {cat:<30} {c:>10} {w:>10} {inf:>8} {total:>8}")

    total_c = len(critical_issues)
    total_w = len(warning_issues)
    total_i = len(info_issues)
    print(f"  {'-'*66}")
    print(f"  {'合計':<30} {total_c:>10} {total_w:>10} {total_i:>8} {len(issues):>8}")

    # ---- 受影響檔案統計 ----
    affected_files = set()
    for i in issues:
        affected_files.add(i.file_path)

    critical_files = set(i.file_path for i in critical_issues)
    warning_files = set(i.file_path for i in warning_issues)

    print(f"\n{'='*80}")
    print(f"  受影響檔案統計")
    print(f"{'='*80}")
    print(f"  總檔案數: {len(files)}")
    print(f"  有問題的檔案數: {len(affected_files)} ({len(affected_files)/len(files)*100:.1f}%)")
    print(f"  有 CRITICAL 問題的檔案數: {len(critical_files)} ({len(critical_files)/len(files)*100:.1f}%)")
    print(f"  有 WARNING 問題的檔案數: {len(warning_files)} ({len(warning_files)/len(files)*100:.1f}%)")
    print(f"  完全無問題的檔案數: {len(files) - len(affected_files)} ({(len(files)-len(affected_files))/len(files)*100:.1f}%)")

    # ---- 各年度問題分佈 ----
    print(f"\n{'='*80}")
    print(f"  各年度問題分佈")
    print(f"{'='*80}")
    year_issues = defaultdict(lambda: {"CRITICAL": 0, "WARNING": 0, "INFO": 0})
    for i in issues:
        parts = i.file_path.replace("\\", "/").split("/")
        year = parts[0] if parts else "unknown"
        year_issues[year][i.severity] += 1

    print(f"  {'年度':<10} {'CRITICAL':>10} {'WARNING':>10} {'INFO':>8} {'合計':>8}")
    print(f"  {'-'*46}")
    for year in sorted(year_issues.keys()):
        c = year_issues[year]["CRITICAL"]
        w = year_issues[year]["WARNING"]
        inf = year_issues[year]["INFO"]
        total = c + w + inf
        print(f"  {year:<10} {c:>10} {w:>10} {inf:>8} {total:>8}")


# ============================================================
# 主程式
# ============================================================
if __name__ == "__main__":
    print("=" * 80)
    print("  國境警察學系移民組題庫 JSON 結構審計工具")
    print("  目標路徑:", TARGET_DIR)
    print("  參考路徑:", REF_DIR)
    print("=" * 80)
    print()

    analyze_reference_format()
    audit_all_files()
