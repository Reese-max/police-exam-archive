# -*- coding: utf-8 -*-
"""
修復移民特考閱讀測驗空 stem 題目

問題描述：
  在「考古題庫/移民特考/」的試題.json 中，有 344 道選擇題的 stem 為空字串 ""。
  這些全是英文閱讀測驗題組（克漏字填空型）。
  閱讀段落（passage）被錯誤地合併到前面某一題的選項 D 中。

修復策略：
  1. 掃描所有 JSON 檔案，找出 stem 為空的選擇題
  2. 往前搜尋含有「請依下文回答第X題至第Y題」引導文字的題目
  3. 從該題的選項中提取 passage（引導文字之後的英文段落）
  4. 修復被汙染的選項值（只保留引導文字之前的真正選項）
  5. 為空 stem 題目新增 passage 欄位

用法：
  python fix_empty_stems.py          # dry-run 模式（預設）
  python fix_empty_stems.py --apply  # 實際寫入修改
"""

import json
import glob
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict


# ── 常數 ────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR / "考古題庫" / "移民特考"
BACKUP_DIR = SCRIPT_DIR / "backups" / f"fix_empty_stems_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# 匹配所有引導文字變體
INTRO_PATTERN = re.compile(
    r'請(?:依下文)?回答(?:下列)?第?\s*(\d+)\s*題?\s*至?\s*第?\s*(\d+)\s*題\s*[:：]?\s*'
)


# ── 核心函式 ──────────────────────────────────────────────────

def find_json_files():
    """遞迴找出所有試題.json檔案"""
    pattern = str(BASE_DIR / "**" / "試題.json")
    files = glob.glob(pattern, recursive=True)
    return sorted(files)


def find_empty_stem_groups(questions):
    """
    找出所有 stem 為空的選擇題，並按連續索引分組。
    回傳: list of list[int]，每個子清單是一組連續空 stem 題目的索引
    """
    empty_indices = []
    for i, q in enumerate(questions):
        if q.get("type") == "choice" and q.get("stem", "x").strip() == "":
            empty_indices.append(i)

    if not empty_indices:
        return []

    # 將連續的索引分組
    groups = []
    current_group = [empty_indices[0]]
    for idx in empty_indices[1:]:
        if idx == current_group[-1] + 1:
            current_group.append(idx)
        else:
            groups.append(current_group)
            current_group = [idx]
    groups.append(current_group)

    return groups


def find_intro_and_passage(questions, group, all_intros_in_file):
    """
    針對一組空 stem 題目，在前方題目中搜尋對應的引導文字和 passage。

    參數:
      questions: 所有題目清單
      group: 此題組的索引清單 (如 [10, 11, 12, 13, 14])
      all_intros_in_file: 預先掃描出的所有引導文字資訊

    回傳: dict 或 None
      {
        'intro_q_idx': int,        # 引導文字所在的題目索引
        'intro_location': str,     # 'stem' 或 'opt_X'
        'intro_text': str,         # 完整引導文字（如「請依下文回答第11題至第15題」）
        'passage': str,            # 英文段落
        'real_option_value': str,  # 被汙染選項的真正值
        'option_key': str,         # 被汙染的選項鍵（如 'D'）
        'range_start': int,        # 引導文字指定的起始題號
        'range_end': int,          # 引導文字指定的結束題號
      }
    """
    first_empty_num = questions[group[0]].get("number")
    if not isinstance(first_empty_num, int):
        return None

    # 在預掃描的引導文字中尋找匹配
    for intro_info in all_intros_in_file:
        if intro_info["range_start"] <= first_empty_num <= intro_info["range_end"]:
            return intro_info

    return None


def scan_all_intros(questions):
    """
    預先掃描一份試卷中所有的引導文字。
    回傳: list of dict
    """
    intros = []

    for i, q in enumerate(questions):
        # 檢查 stem
        stem = q.get("stem", "")
        for m in INTRO_PATTERN.finditer(stem):
            range_start = int(m.group(1))
            range_end = int(m.group(2))
            passage = stem[m.end():].strip()
            real_stem = stem[:m.start()].strip()
            intros.append({
                "intro_q_idx": i,
                "intro_location": "stem",
                "intro_text": m.group(0).strip(),
                "passage": passage,
                "real_option_value": None,
                "real_stem_value": real_stem,
                "option_key": None,
                "range_start": range_start,
                "range_end": range_end,
                "match_start": m.start(),
            })

        # 檢查每個選項
        if isinstance(q.get("options"), dict):
            for opt_key, opt_val in q["options"].items():
                opt_str = str(opt_val) if opt_val else ""
                for m in INTRO_PATTERN.finditer(opt_str):
                    range_start = int(m.group(1))
                    range_end = int(m.group(2))
                    passage = opt_str[m.end():].strip()
                    real_opt = opt_str[:m.start()].strip()
                    intros.append({
                        "intro_q_idx": i,
                        "intro_location": f"opt_{opt_key}",
                        "intro_text": m.group(0).strip(),
                        "passage": passage,
                        "real_option_value": real_opt,
                        "real_stem_value": None,
                        "option_key": opt_key,
                        "range_start": range_start,
                        "range_end": range_end,
                        "match_start": m.start(),
                    })

    return intros


def process_file(filepath, apply=False):
    """
    處理單一 JSON 檔案。

    回傳: dict 統計資訊
      {
        'file': str,
        'total_empty': int,
        'fixed': int,
        'unfixed': int,
        'details': list[str],
        'modified': bool,
      }
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    questions = data.get("questions", []) if isinstance(data, dict) else data
    groups = find_empty_stem_groups(questions)

    stats = {
        "file": filepath,
        "total_empty": sum(len(g) for g in groups),
        "fixed": 0,
        "unfixed": 0,
        "details": [],
        "modified": False,
        "option_fixes": 0,
    }

    if not groups:
        return stats

    # 預掃描所有引導文字
    all_intros = scan_all_intros(questions)

    for group in groups:
        empty_nums = [questions[idx].get("number") for idx in group]
        intro_info = find_intro_and_passage(questions, group, all_intros)

        if intro_info is None:
            stats["unfixed"] += len(group)
            stats["details"].append(
                f"  [未修復] Q#{empty_nums}: 找不到對應的引導文字和 passage"
            )
            if apply:
                # 無法找到 passage，在 stem 中填入提示
                for idx in group:
                    questions[idx]["stem"] = "（承上題組）"
                stats["modified"] = True
            continue

        passage = intro_info["passage"]
        intro_text = intro_info["intro_text"]
        intro_q_idx = intro_info["intro_q_idx"]
        intro_q_num = questions[intro_q_idx].get("number")

        if not passage.strip():
            stats["unfixed"] += len(group)
            stats["details"].append(
                f"  [未修復] Q#{empty_nums}: 引導文字在 Q#{intro_q_num} 中找到，但 passage 為空"
            )
            if apply:
                for idx in group:
                    questions[idx]["stem"] = "（承上題組）"
                stats["modified"] = True
            continue

        # 成功找到 passage
        passage_preview = passage[:80].replace("\n", " ")
        stats["details"].append(
            f"  [修復] Q#{empty_nums} <- Q#{intro_q_num} ({intro_info['intro_location']})"
        )
        stats["details"].append(
            f"         引導: {intro_text}"
        )
        stats["details"].append(
            f"         passage: {passage_preview}... ({len(passage)} chars)"
        )

        if apply:
            # 1. 為空 stem 題目新增 passage 欄位
            for idx in group:
                questions[idx]["passage"] = passage
                questions[idx]["passage_intro"] = intro_text

            # 2. 修復被汙染的選項值或 stem
            if intro_info["option_key"] is not None:
                opt_key = intro_info["option_key"]
                real_val = intro_info["real_option_value"]
                old_val = questions[intro_q_idx]["options"][opt_key]
                if old_val != real_val:
                    questions[intro_q_idx]["options"][opt_key] = real_val
                    stats["option_fixes"] += 1
                    stats["details"].append(
                        f"         選項修復: Q#{intro_q_num}.{opt_key} "
                        f"\"{old_val[:40]}...\" -> \"{real_val}\""
                    )
            elif intro_info["real_stem_value"] is not None:
                real_stem = intro_info["real_stem_value"]
                old_stem = questions[intro_q_idx]["stem"]
                if old_stem != real_stem:
                    questions[intro_q_idx]["stem"] = real_stem
                    stats["details"].append(
                        f"         stem 修復: Q#{intro_q_num}"
                    )

            stats["modified"] = True

        stats["fixed"] += len(group)

    # 寫回檔案
    if apply and stats["modified"]:
        # 備份
        rel_path = os.path.relpath(filepath, str(SCRIPT_DIR))
        backup_path = BACKUP_DIR / rel_path
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(filepath, backup_path)

        # 寫入修改後的資料
        if isinstance(data, dict):
            data["questions"] = questions
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return stats


def main():
    """主程式入口"""
    apply = "--apply" in sys.argv

    print("=" * 70)
    print("移民特考閱讀測驗空 stem 修復工具")
    print("=" * 70)

    if apply:
        print(f"模式: 實際寫入 (--apply)")
        print(f"備份目錄: {BACKUP_DIR}")
    else:
        print(f"模式: dry-run（預覽模式，不會修改檔案）")
        print(f"  提示: 加上 --apply 參數以實際執行修改")

    print(f"掃描目錄: {BASE_DIR}")
    print()

    # 掃描檔案
    json_files = find_json_files()
    print(f"找到 {len(json_files)} 個試題.json 檔案")
    print()

    # 處理每個檔案
    total_stats = {
        "files_scanned": len(json_files),
        "files_with_empty": 0,
        "files_modified": 0,
        "total_empty": 0,
        "total_fixed": 0,
        "total_unfixed": 0,
        "total_option_fixes": 0,
    }

    # 按科目分類統計
    subject_stats = defaultdict(lambda: {"empty": 0, "fixed": 0, "unfixed": 0})

    affected_files = []

    for filepath in json_files:
        stats = process_file(filepath, apply=apply)

        if stats["total_empty"] > 0:
            total_stats["files_with_empty"] += 1
            affected_files.append(stats)

            if stats["modified"]:
                total_stats["files_modified"] += 1

            total_stats["total_empty"] += stats["total_empty"]
            total_stats["total_fixed"] += stats["fixed"]
            total_stats["total_unfixed"] += stats["unfixed"]
            total_stats["total_option_fixes"] += stats["option_fixes"]

            # 科目分類
            rel = os.path.relpath(filepath, str(BASE_DIR))
            parts = Path(rel).parts
            if len(parts) >= 2:
                subject = parts[1]  # 科目名稱
            else:
                subject = "未知"

            subject_stats[subject]["empty"] += stats["total_empty"]
            subject_stats[subject]["fixed"] += stats["fixed"]
            subject_stats[subject]["unfixed"] += stats["unfixed"]

    # ── 輸出詳細報告 ──────────────────────────────────────────
    print("-" * 70)
    print("詳細修改清單")
    print("-" * 70)

    for stats in affected_files:
        rel = os.path.relpath(stats["file"], str(BASE_DIR))
        print(f"\n{rel}")
        print(f"  空 stem: {stats['total_empty']} 題 | "
              f"修復: {stats['fixed']} | 未修復: {stats['unfixed']}")
        for detail in stats["details"]:
            print(detail)

    # ── 科目統計 ───────────────────────────────────────────────
    print()
    print("-" * 70)
    print("按科目統計")
    print("-" * 70)
    print(f"{'科目':<50} {'空stem':>6} {'修復':>6} {'未修復':>6}")
    print("-" * 70)

    for subject in sorted(subject_stats.keys()):
        s = subject_stats[subject]
        print(f"{subject:<50} {s['empty']:>6} {s['fixed']:>6} {s['unfixed']:>6}")

    # ── 總結 ──────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("修復統計總結")
    print("=" * 70)
    print(f"掃描檔案數:       {total_stats['files_scanned']}")
    print(f"含空 stem 的檔案:  {total_stats['files_with_empty']}")
    if apply:
        print(f"已修改的檔案:     {total_stats['files_modified']}")
    print(f"空 stem 題目總數:  {total_stats['total_empty']}")
    print(f"成功修復:          {total_stats['total_fixed']}")
    print(f"無法自動修復:      {total_stats['total_unfixed']}")
    if apply:
        print(f"選項值修復:        {total_stats['total_option_fixes']}")
        print(f"備份位置:          {BACKUP_DIR}")

    print()
    if not apply:
        print("以上為預覽結果，實際檔案未被修改。")
        print("若確認無誤，請執行: python fix_empty_stems.py --apply")
    else:
        print("修復完成！原始檔案已備份。")

    return 0 if total_stats["total_unfixed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
