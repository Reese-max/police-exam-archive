#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""驗證所有選擇題都有 ABCD 四個非空選項"""

import json
import os
import glob

BASE = os.path.dirname(os.path.abspath(__file__))
QUIZ_DIR = os.path.join(BASE, "考古題庫")

issues = []
total_choice = 0
total_files = 0

for fpath in glob.glob(os.path.join(QUIZ_DIR, "**", "試題.json"), recursive=True):
    # 排除 backups 目錄
    if "backups" in fpath:
        continue
    total_files += 1
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        issues.append(f"[ERROR] 無法讀取 {fpath}: {e}")
        continue

    rel_path = os.path.relpath(fpath, BASE)
    year = data.get("year", "?")
    category = data.get("category", "?")
    subject = data.get("subject", "?")

    for q in data.get("questions", []):
        if q.get("type") != "choice":
            continue
        total_choice += 1
        qnum = q.get("number", "?")
        options = q.get("options", {})

        # 檢查是否有 ABCD 四個 key
        missing_keys = [k for k in ["A", "B", "C", "D"] if k not in options]
        if missing_keys:
            issues.append(
                f"[incomplete_option_keys] {category}/{year}年/{subject} Q{qnum}: "
                f"缺少選項 {', '.join(missing_keys)}"
            )

        # 檢查是否有空字串或「(原始資料缺失)」
        for k in ["A", "B", "C", "D"]:
            if k in options:
                val = options[k]
                if val == "":
                    issues.append(
                        f"[empty_option] {category}/{year}年/{subject} Q{qnum}: "
                        f"選項 {k} 為空字串"
                    )
                elif val == "(原始資料缺失)":
                    issues.append(
                        f"[missing_option_text] {category}/{year}年/{subject} Q{qnum}: "
                        f"選項 {k} 為「(原始資料缺失)」"
                    )
                elif "考 試 試 題" in val or val.startswith("保障與正當"):
                    issues.append(
                        f"[garbage_text] {category}/{year}年/{subject} Q{qnum}: "
                        f"選項 {k} 含垃圾文字: {val[:50]}"
                    )

print(f"掃描完成：{total_files} 個 JSON 檔案，{total_choice} 題選擇題")
print(f"{'='*60}")

if issues:
    print(f"發現 {len(issues)} 個問題：")
    for issue in issues:
        print(f"  {issue}")
else:
    print("所有選擇題都有 ABCD 四個非空選項，沒有發現任何問題！")

print(f"{'='*60}")
