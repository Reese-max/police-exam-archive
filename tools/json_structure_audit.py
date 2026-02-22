#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON 結構品質掃描工具
掃描所有試題 JSON 檔案，檢查 10 項品質指標並產出報告。
"""

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


# 專案根目錄
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "考古題庫"
REPORT_DIR = BASE_DIR / "reports"
REPORT_FILE = REPORT_DIR / "json_audit_report.txt"

# 中文數字對應
CHINESE_NUMS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
                "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十"]

# 亂碼字元模式（U+FFFD replacement character 及其他常見亂碼）
GARBLED_PATTERN = re.compile(r'[\ufffd\ufffe\uffff]')

# 合法答案模式
VALID_ANSWER_PATTERN = re.compile(r'^[A-Da-d]([|*#][A-Da-d])*$|^[A-Da-d]$|^送分$|^一律給分$')


def load_json(filepath):
    """載入 JSON 檔案"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f), None
    except json.JSONDecodeError as e:
        return None, f"JSON 解析失敗: {e}"
    except Exception as e:
        return None, f"讀取失敗: {e}"


def extract_year_from_path(filepath):
    """從路徑中擷取年份"""
    parts = Path(filepath).parts
    for part in parts:
        if part.endswith("年"):
            try:
                return int(part[:-1])
            except ValueError:
                pass
        # 也嘗試純數字
        try:
            y = int(part)
            if 100 <= y <= 120:
                return y
        except ValueError:
            pass
    return None


def extract_category_from_path(filepath):
    """從路徑中擷取類科"""
    rel = os.path.relpath(filepath, DATA_DIR)
    parts = Path(rel).parts
    if len(parts) >= 1:
        return parts[0]
    return "未知"


def check_required_fields(data, filepath):
    """檢查 1：必要欄位完整性"""
    issues = []
    required_top = ["metadata", "questions", "year", "category", "subject"]
    for field in required_top:
        if field not in data:
            issues.append(f"缺少頂層欄位: {field}")
        elif data[field] is None:
            issues.append(f"頂層欄位為 null: {field}")

    # questions 應為 list
    if "questions" in data and not isinstance(data.get("questions"), list):
        issues.append(f"questions 欄位不是陣列（實際類型: {type(data.get('questions')).__name__}）")

    return issues


def check_choice_structure(questions):
    """檢查 2：選擇題結構"""
    issues = []
    for q in questions:
        if q.get("type") != "choice":
            continue
        qnum = q.get("number", "?")

        # stem 必須存在且非空
        stem = q.get("stem", "")
        if not stem or not stem.strip():
            issues.append(f"選擇題 #{qnum}: stem 為空")

        # answer 必須存在
        if "answer" not in q:
            issues.append(f"選擇題 #{qnum}: 缺少 answer 欄位")
        else:
            answer = str(q["answer"]).strip()
            if not answer:
                issues.append(f"選擇題 #{qnum}: answer 為空字串")

    return issues


def check_number_continuity(questions):
    """檢查 3：題號連續性"""
    issues = []
    choice_nums = []
    for q in questions:
        if q.get("type") == "choice":
            num = q.get("number")
            if isinstance(num, int):
                choice_nums.append(num)
            elif isinstance(num, str):
                try:
                    choice_nums.append(int(num))
                except ValueError:
                    issues.append(f"選擇題題號非數字: '{num}'")

    if not choice_nums:
        return issues

    # 排序後檢查
    sorted_nums = sorted(choice_nums)

    # 檢查重複
    seen = set()
    for n in choice_nums:
        if n in seen:
            issues.append(f"選擇題題號重複: {n}")
        seen.add(n)

    # 檢查跳號（從最小到最大）
    if sorted_nums:
        expected = sorted_nums[0]
        for n in sorted_nums:
            if n != expected:
                # 找出跳過的號碼
                while expected < n:
                    issues.append(f"選擇題跳號: 缺少 #{expected}")
                    expected += 1
            expected = n + 1

    return issues


def check_options_completeness(questions):
    """檢查 4：選項完整性"""
    issues = []
    for q in questions:
        if q.get("type") != "choice":
            continue
        qnum = q.get("number", "?")

        if "options" in q:
            opts = q["options"]
            if isinstance(opts, list):
                if len(opts) < 2:
                    issues.append(f"選擇題 #{qnum}: 選項數量不足（僅 {len(opts)} 個）")
            else:
                issues.append(f"選擇題 #{qnum}: options 欄位不是陣列")
    return issues


def check_empty_stems(questions):
    """檢查 5：空白題幹"""
    issues = []
    for q in questions:
        qnum = q.get("number", "?")
        qtype = q.get("type", "?")
        stem = q.get("stem", "")
        if not stem or not stem.strip():
            issues.append(f"{qtype} 題 #{qnum}: 題幹為空")
    return issues


def check_answer_domain(questions):
    """檢查 6：答案值域"""
    issues = []
    for q in questions:
        if q.get("type") != "choice":
            continue
        qnum = q.get("number", "?")
        answer = q.get("answer")
        if answer is None:
            continue  # 已在 check_choice_structure 中檢查

        answer_str = str(answer).strip()
        if not answer_str:
            continue

        # 合法答案: A/B/C/D（大小寫），或含 | * # 的多答案，或「送分」「一律給分」
        # 也允許 AB, AC 等複選
        valid = re.match(
            r'^[A-Da-d]{1,4}$|^[A-Da-d]([|*#,][A-Da-d])*$|^送分$|^一律給分$|^\*$|^#$',
            answer_str
        )
        if not valid:
            issues.append(f"選擇題 #{qnum}: 答案值域異常 → '{answer_str}'")

    return issues


def check_essay_structure(questions):
    """檢查 7：申論題結構"""
    issues = []
    for q in questions:
        if q.get("type") != "essay":
            continue
        qnum = q.get("number", "?")

        # stem 應存在
        stem = q.get("stem", "")
        if not stem or not stem.strip():
            issues.append(f"申論題 #{qnum}: 題幹為空")

        # 題號應為中文數字（但也容許特殊情況）
        if isinstance(qnum, int):
            issues.append(f"申論題 #{qnum}: 題號為數字而非中文（可能分類錯誤）")

    return issues


def check_encoding_issues(data, filepath):
    """檢查 8：編碼問題"""
    issues = []
    text = json.dumps(data, ensure_ascii=False)

    # U+FFFD replacement character
    matches = list(GARBLED_PATTERN.finditer(text))
    if matches:
        # 找出具體在哪些題目
        for q in data.get("questions", []):
            qnum = q.get("number", "?")
            stem = q.get("stem", "")
            if GARBLED_PATTERN.search(stem):
                issues.append(f"題 #{qnum} 題幹含亂碼字元 (U+FFFD)")
            for opt in q.get("options", []):
                opt_text = opt.get("text", "") if isinstance(opt, dict) else str(opt)
                if GARBLED_PATTERN.search(opt_text):
                    issues.append(f"題 #{qnum} 選項含亂碼字元")

        # 也檢查 notes
        for i, note in enumerate(data.get("notes", [])):
            if GARBLED_PATTERN.search(note):
                issues.append(f"notes[{i}] 含亂碼字元")

        # 如果沒有具體定位到題目，但整體有亂碼
        if not issues:
            issues.append(f"檔案含 {len(matches)} 個亂碼字元 (U+FFFD)")

    return issues


def check_year_consistency(data, filepath):
    """檢查 9：年份一致性"""
    issues = []
    path_year = extract_year_from_path(filepath)
    json_year = data.get("year")

    if path_year is None:
        issues.append("無法從路徑中擷取年份")
    elif json_year is None:
        issues.append("JSON 中缺少 year 欄位")
    else:
        if isinstance(json_year, str):
            try:
                json_year = int(json_year)
            except ValueError:
                issues.append(f"year 欄位非數字: '{json_year}'")
                return issues

        if json_year != path_year:
            issues.append(f"年份不一致: JSON={json_year} vs 路徑={path_year}")

    return issues


def audit_all_files():
    """主掃描函式"""
    # 收集所有試題 JSON
    json_files = sorted(DATA_DIR.rglob("試題.json"))
    total = len(json_files)
    print(f"找到 {total} 個試題 JSON 檔案")

    # 統計資料結構
    stats = {
        "total_files": total,
        "parse_errors": [],      # 無法解析的檔案
        "field_issues": [],      # 1. 必要欄位
        "choice_issues": [],     # 2. 選擇題結構
        "number_issues": [],     # 3. 題號連續性
        "option_issues": [],     # 4. 選項完整性
        "empty_stem_issues": [], # 5. 空白題幹
        "answer_issues": [],     # 6. 答案值域
        "essay_issues": [],      # 7. 申論題結構
        "encoding_issues": [],   # 8. 編碼問題
        "year_issues": [],       # 9. 年份一致性
    }

    # 統計摘要用
    by_category = defaultdict(lambda: {
        "total": 0, "choice_count": 0, "essay_count": 0,
        "issue_count": 0, "files_with_issues": 0
    })
    by_year = defaultdict(lambda: {
        "total": 0, "choice_count": 0, "essay_count": 0,
        "issue_count": 0, "files_with_issues": 0
    })

    total_choice = 0
    total_essay = 0
    total_other = 0
    files_with_issues = 0
    total_issues = 0

    for idx, filepath in enumerate(json_files):
        if (idx + 1) % 100 == 0:
            print(f"  進度: {idx + 1}/{total}")

        rel_path = os.path.relpath(filepath, DATA_DIR)
        category = extract_category_from_path(filepath)
        path_year = extract_year_from_path(filepath)
        year_key = f"{path_year}年" if path_year else "未知"

        # 載入 JSON
        data, err = load_json(filepath)
        if err:
            stats["parse_errors"].append((rel_path, err))
            by_category[category]["total"] += 1
            by_category[category]["issue_count"] += 1
            by_category[category]["files_with_issues"] += 1
            by_year[year_key]["total"] += 1
            by_year[year_key]["issue_count"] += 1
            by_year[year_key]["files_with_issues"] += 1
            files_with_issues += 1
            total_issues += 1
            continue

        questions = data.get("questions", [])

        # 統計題型
        file_choice = sum(1 for q in questions if q.get("type") == "choice")
        file_essay = sum(1 for q in questions if q.get("type") == "essay")
        file_other = sum(1 for q in questions if q.get("type") not in ("choice", "essay"))
        total_choice += file_choice
        total_essay += file_essay
        total_other += file_other

        by_category[category]["total"] += 1
        by_category[category]["choice_count"] += file_choice
        by_category[category]["essay_count"] += file_essay
        by_year[year_key]["total"] += 1
        by_year[year_key]["choice_count"] += file_choice
        by_year[year_key]["essay_count"] += file_essay

        # 執行所有檢查
        file_issues = []

        issues_1 = check_required_fields(data, filepath)
        if issues_1:
            for iss in issues_1:
                stats["field_issues"].append((rel_path, iss))
                file_issues.append(iss)

        issues_2 = check_choice_structure(questions)
        if issues_2:
            for iss in issues_2:
                stats["choice_issues"].append((rel_path, iss))
                file_issues.append(iss)

        issues_3 = check_number_continuity(questions)
        if issues_3:
            for iss in issues_3:
                stats["number_issues"].append((rel_path, iss))
                file_issues.append(iss)

        issues_4 = check_options_completeness(questions)
        if issues_4:
            for iss in issues_4:
                stats["option_issues"].append((rel_path, iss))
                file_issues.append(iss)

        issues_5 = check_empty_stems(questions)
        if issues_5:
            for iss in issues_5:
                stats["empty_stem_issues"].append((rel_path, iss))
                file_issues.append(iss)

        issues_6 = check_answer_domain(questions)
        if issues_6:
            for iss in issues_6:
                stats["answer_issues"].append((rel_path, iss))
                file_issues.append(iss)

        issues_7 = check_essay_structure(questions)
        if issues_7:
            for iss in issues_7:
                stats["essay_issues"].append((rel_path, iss))
                file_issues.append(iss)

        issues_8 = check_encoding_issues(data, filepath)
        if issues_8:
            for iss in issues_8:
                stats["encoding_issues"].append((rel_path, iss))
                file_issues.append(iss)

        issues_9 = check_year_consistency(data, filepath)
        if issues_9:
            for iss in issues_9:
                stats["year_issues"].append((rel_path, iss))
                file_issues.append(iss)

        if file_issues:
            files_with_issues += 1
            by_category[category]["issue_count"] += len(file_issues)
            by_category[category]["files_with_issues"] += 1
            by_year[year_key]["issue_count"] += len(file_issues)
            by_year[year_key]["files_with_issues"] += 1
        total_issues += len(file_issues)

    # 產出報告
    generate_report(stats, by_category, by_year,
                    total, files_with_issues, total_issues,
                    total_choice, total_essay, total_other)


def generate_report(stats, by_category, by_year,
                    total_files, files_with_issues, total_issues,
                    total_choice, total_essay, total_other):
    """產出文字報告"""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    lines = []

    def w(text=""):
        lines.append(text)

    w("=" * 80)
    w("JSON 結構品質掃描報告")
    w(f"產出時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    w("=" * 80)
    w()

    # ===== 總覽 =====
    w("【總覽】")
    w(f"  掃描檔案數: {total_files}")
    w(f"  有問題的檔案: {files_with_issues} ({files_with_issues/total_files*100:.1f}%)")
    w(f"  無問題的檔案: {total_files - files_with_issues}")
    w(f"  問題總數: {total_issues}")
    w()
    w(f"  選擇題總數: {total_choice}")
    w(f"  申論題總數: {total_essay}")
    w(f"  其他題型: {total_other}")
    w(f"  題目總數: {total_choice + total_essay + total_other}")
    w()

    # ===== 各項檢查摘要 =====
    w("-" * 80)
    w("【各項檢查摘要】")
    w()

    checks = [
        ("parse_errors", "JSON 解析錯誤"),
        ("field_issues", "1. 必要欄位完整性"),
        ("choice_issues", "2. 選擇題結構"),
        ("number_issues", "3. 題號連續性"),
        ("option_issues", "4. 選項完整性"),
        ("empty_stem_issues", "5. 空白題幹"),
        ("answer_issues", "6. 答案值域"),
        ("essay_issues", "7. 申論題結構"),
        ("encoding_issues", "8. 編碼問題"),
        ("year_issues", "9. 年份一致性"),
    ]

    for key, label in checks:
        issue_list = stats[key]
        count = len(issue_list)
        status = "PASS" if count == 0 else "FAIL"
        affected = len(set(path for path, _ in issue_list))
        w(f"  {label}: {status} ({count} 個問題, 影響 {affected} 個檔案)")

    w()

    # ===== 詳細問題列表 =====
    w("-" * 80)
    w("【詳細問題列表】")
    w()

    for key, label in checks:
        issue_list = stats[key]
        if not issue_list:
            continue

        w(f"--- {label} ({len(issue_list)} 個問題) ---")
        w()

        # 按檔案分組
        by_file = defaultdict(list)
        for path, issue in issue_list:
            by_file[path].append(issue)

        for path in sorted(by_file.keys()):
            w(f"  [{path}]")
            for issue in by_file[path]:
                w(f"    - {issue}")
            w()

    # ===== 統計摘要：按類科 =====
    w("-" * 80)
    w("【10. 統計摘要 — 按類科】")
    w()
    w(f"  {'類科':<20} {'檔案數':>6} {'選擇題':>8} {'申論題':>8} {'問題數':>8} {'問題檔案':>10}")
    w(f"  {'-'*18:<20} {'-'*6:>6} {'-'*8:>8} {'-'*8:>8} {'-'*8:>8} {'-'*10:>10}")
    for cat in sorted(by_category.keys()):
        s = by_category[cat]
        w(f"  {cat:<20} {s['total']:>6} {s['choice_count']:>8} {s['essay_count']:>8} "
          f"{s['issue_count']:>8} {s['files_with_issues']:>10}")
    w()

    # ===== 統計摘要：按年份 =====
    w("-" * 80)
    w("【10. 統計摘要 — 按年份】")
    w()
    w(f"  {'年份':<10} {'檔案數':>6} {'選擇題':>8} {'申論題':>8} {'問題數':>8} {'問題檔案':>10}")
    w(f"  {'-'*8:<10} {'-'*6:>6} {'-'*8:>8} {'-'*8:>8} {'-'*8:>8} {'-'*10:>10}")
    for year in sorted(by_year.keys()):
        s = by_year[year]
        w(f"  {year:<10} {s['total']:>6} {s['choice_count']:>8} {s['essay_count']:>8} "
          f"{s['issue_count']:>8} {s['files_with_issues']:>10}")
    w()

    w("=" * 80)
    w("報告結束")
    w("=" * 80)

    report_text = "\n".join(lines)

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(f"\n報告已儲存至: {REPORT_FILE}")
    print(f"問題總數: {total_issues}, 影響 {files_with_issues}/{total_files} 個檔案")

    # 同時輸出到 stdout
    print()
    print(report_text)


if __name__ == "__main__":
    audit_all_files()
