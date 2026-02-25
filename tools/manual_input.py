#!/usr/bin/env python3
"""
考古題手動補入工具

互動式命令列工具，讓使用者方便地對照 PDF 手動補入遺漏題目。
支援：
  - 任務清單模式（預設）
  - 互動式逐題輸入
  - 英文閱讀測驗批次輸入（一次輸入，自動寫入多類科）
  - CSV 批次匯入
  - 進度追蹤與備份

用法：
  python tools/manual_input.py              # 互動模式
  python tools/manual_input.py --batch input.csv  # CSV 批次匯入
  python tools/manual_input.py --scan       # 重新掃描缺失清單
"""

import argparse
import csv
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# === 常數 ===

BASE_DIR = Path(__file__).resolve().parent.parent
EXAM_DIR = BASE_DIR / "考古題庫"
PROGRESS_FILE = Path(__file__).resolve().parent / "manual_input_progress.json"
BACKUP_BASE = BASE_DIR / "backups"


# === 缺失清單定義 ===

def scan_missing_questions() -> list[dict]:
    """掃描所有 JSON 檔案，找出缺失的題目。回傳任務清單。"""
    tasks: list[dict] = []
    task_id = 0

    # --- 英文閱讀測驗缺失（共用試題，輸入一次寫入多類科） ---

    # 106年 警察英文 Q59-60（11 類科共用）
    depts_106 = _find_depts_missing_questions(
        year="106年",
        subject_pattern="中華民國憲法與警察專業英文",
        missing_nums=[59, 60],
    )
    if depts_106:
        task_id += 1
        tasks.append({
            "id": task_id,
            "type": "shared_english",
            "label": "106年 警察英文 Q59-60",
            "description": f"閱讀測驗（{len(depts_106)} 類科共用）",
            "year": "106年",
            "subject": "中華民國憲法與警察專業英文",
            "missing_nums": [59, 60],
            "target_files": depts_106,
            "total_questions": len(depts_106) * 2,
        })

    # 107年 警察英文 Q56-60（12 類科共用）
    depts_107 = _find_depts_missing_questions(
        year="107年",
        subject_pattern="中華民國憲法與警察專業英文",
        missing_nums=list(range(56, 61)),
    )
    if depts_107:
        task_id += 1
        tasks.append({
            "id": task_id,
            "type": "shared_english",
            "label": "107年 警察英文 Q56-60",
            "description": f"閱讀測驗（{len(depts_107)} 類科共用）",
            "year": "107年",
            "subject": "中華民國憲法與警察專業英文",
            "missing_nums": list(range(56, 61)),
            "target_files": depts_107,
            "total_questions": len(depts_107) * 5,
        })

    # 106年 消防英文 Q56-60
    fire_106 = _find_depts_missing_questions(
        year="106年",
        subject_pattern="中華民國憲法與消防警察專業英文",
        missing_nums=list(range(56, 61)),
        dept_filter="消防",
    )
    if fire_106:
        task_id += 1
        tasks.append({
            "id": task_id,
            "type": "shared_english",
            "label": "106年 消防英文 Q56-60",
            "description": f"閱讀測驗（{len(fire_106)} 類科）",
            "year": "106年",
            "subject": "中華民國憲法與消防警察專業英文",
            "missing_nums": list(range(56, 61)),
            "target_files": fire_106,
            "total_questions": len(fire_106) * 5,
        })

    # 107年 消防英文 Q56-60
    fire_107 = _find_depts_missing_questions(
        year="107年",
        subject_pattern="中華民國憲法與消防警察專業英文",
        missing_nums=list(range(56, 61)),
        dept_filter="消防",
    )
    if fire_107:
        task_id += 1
        tasks.append({
            "id": task_id,
            "type": "shared_english",
            "label": "107年 消防英文 Q56-60",
            "description": f"閱讀測驗（{len(fire_107)} 類科）",
            "year": "107年",
            "subject": "中華民國憲法與消防警察專業英文",
            "missing_nums": list(range(56, 61)),
            "target_files": fire_107,
            "total_questions": len(fire_107) * 5,
        })

    # 107年 水上英文 Q51-60
    water_107 = _find_depts_missing_questions(
        year="107年",
        subject_pattern="中華民國憲法與水上警察專業英文",
        missing_nums=list(range(51, 61)),
        dept_filter="水上",
    )
    if water_107:
        task_id += 1
        tasks.append({
            "id": task_id,
            "type": "shared_english",
            "label": "107年 水上英文 Q51-60",
            "description": f"閱讀測驗（{len(water_107)} 類科）",
            "year": "107年",
            "subject": "中華民國憲法與水上警察專業英文",
            "missing_nums": list(range(51, 61)),
            "target_files": water_107,
            "total_questions": len(water_107) * 10,
        })

    # 112年 消防英文 Q60
    fire_112 = _find_depts_missing_questions(
        year="112年",
        subject_pattern="中華民國憲法與消防警察專業英文",
        missing_nums=[60],
        dept_filter="消防",
    )
    if fire_112:
        task_id += 1
        tasks.append({
            "id": task_id,
            "type": "shared_english",
            "label": "112年 消防英文 Q60",
            "description": f"閱讀測驗（{len(fire_112)} 類科）",
            "year": "112年",
            "subject": "中華民國憲法與消防警察專業英文",
            "missing_nums": [60],
            "target_files": fire_112,
            "total_questions": len(fire_112),
        })

    # 犯罪防治學系矯治組 法學英文（各年度獨立）
    correction_years = {
        "106年": list(range(46, 51)),
        "107年": list(range(46, 51)),
        "108年": list(range(47, 51)),
        "109年": list(range(46, 51)),
        "110年": list(range(46, 51)),
        "114年": list(range(46, 51)),
    }
    for year, missing_nums in correction_years.items():
        files = _find_depts_missing_questions(
            year=year,
            subject_pattern="法學知識與英文",
            missing_nums=missing_nums,
            dept_filter="犯罪防治學系矯治組",
        )
        if files:
            task_id += 1
            nums_str = f"Q{missing_nums[0]}-{missing_nums[-1]}"
            tasks.append({
                "id": task_id,
                "type": "single_file",
                "label": f"犯罪防治矯治組 {year} 法學英文 {nums_str}",
                "description": f"閱讀測驗（{len(missing_nums)} 題）",
                "year": year,
                "missing_nums": missing_nums,
                "target_files": files,
                "total_questions": len(missing_nums),
            })

    # --- 最後：掃描是否有其他異常缺漏 ---
    # （已在先前修復中全部處理，但保留掃描以防新問題）

    return tasks


def _find_depts_missing_questions(
    year: str,
    subject_pattern: str,
    missing_nums: list[int],
    dept_filter: str | None = None,
) -> list[str]:
    """找出指定年份/科目中缺少特定題號的所有 JSON 檔案路徑。"""
    import glob as globmod

    pattern = str(EXAM_DIR / "*" / year / f"*{subject_pattern}*" / "試題.json")
    results = []
    for fpath in sorted(globmod.glob(pattern)):
        if dept_filter and dept_filter not in fpath:
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            existing_nums = {
                q["number"] for q in data["questions"]
                if isinstance(q["number"], int)
            }
            still_missing = [n for n in missing_nums if n not in existing_nums]
            if still_missing:
                results.append(fpath)
        except (json.JSONDecodeError, KeyError):
            continue
    return results


# === 進度追蹤 ===

def load_progress() -> dict:
    """載入進度檔案。"""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"completed": [], "last_updated": None}


def save_progress(progress: dict) -> None:
    """儲存進度檔案。"""
    progress["last_updated"] = datetime.now().isoformat()
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def is_task_completed(progress: dict, task_label: str) -> bool:
    """檢查任務是否已完成。"""
    return task_label in progress.get("completed", [])


def mark_task_completed(progress: dict, task_label: str) -> None:
    """標記任務完成。"""
    if task_label not in progress["completed"]:
        progress["completed"].append(task_label)
    save_progress(progress)


# === 備份 ===

def backup_file(filepath: str) -> str:
    """備份指定的 JSON 檔案，回傳備份路徑。"""
    today = datetime.now().strftime("%Y%m%d")
    backup_dir = BACKUP_BASE / f"manual_input_{today}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    rel = os.path.relpath(filepath, EXAM_DIR)
    backup_path = backup_dir / rel
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(filepath, backup_path)
    return str(backup_path)


# === JSON 操作 ===

def load_json(filepath: str) -> dict:
    """載入 JSON 檔案。"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filepath: str, data: dict) -> None:
    """儲存 JSON 檔案（保持格式一致）。"""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # 確保檔案末尾有換行
    with open(filepath, "a", encoding="utf-8") as f:
        f.write("\n")


def insert_question(data: dict, question: dict) -> None:
    """將題目插入到正確的位置（按題號排序）。"""
    qnum = question["number"]
    questions = data["questions"]

    # 找到插入位置：在所有 int 題號中，找到第一個大於 qnum 的位置
    insert_idx = len(questions)
    for i, q in enumerate(questions):
        if isinstance(q["number"], int) and q["number"] > qnum:
            insert_idx = i
            break

    questions.insert(insert_idx, question)


def get_existing_numbers(data: dict) -> list[int]:
    """取得所有選擇題的題號（已排序）。"""
    nums = sorted([
        q["number"] for q in data["questions"]
        if isinstance(q["number"], int)
    ])
    return nums


# === 互動式輸入 ===

def input_multiline(prompt: str) -> str:
    """讀取多行輸入，空行結束。"""
    print(prompt)
    lines = []
    while True:
        try:
            line = input("> ")
        except EOFError:
            break
        if line == "":
            if lines:
                break
            continue
        lines.append(line)
    return "\n".join(lines)


def input_single(prompt: str, default: str = "") -> str:
    """讀取單行輸入。"""
    if default:
        result = input(f"{prompt} [{default}]: ").strip()
        return result if result else default
    return input(f"{prompt}: ").strip()


def input_answer() -> str:
    """讀取答案（A/B/C/D）。"""
    while True:
        ans = input("正確答案 (A/B/C/D): ").strip().upper()
        if ans in ("A", "B", "C", "D"):
            return ans
        print("  請輸入 A、B、C 或 D")


def input_single_question(qnum: int, section: str = "乙、測驗題") -> dict:
    """互動式輸入一道選擇題。"""
    print(f"\n--- 輸入第 {qnum} 題 ---")

    stem = input_multiline("題幹（輸入完畢按 Enter 兩次）:")
    if not stem:
        return {}

    options = {}
    for key in ("A", "B", "C", "D"):
        options[key] = input_single(f"選項 {key}")

    answer = input_answer()

    question = {
        "number": qnum,
        "type": "choice",
        "stem": stem,
        "section": section,
        "answer": answer,
        "options": options,
    }
    return question


def input_reading_comprehension(missing_nums: list[int], section: str = "乙、測驗題") -> list[dict]:
    """輸入閱讀測驗題組（passage + 多題）。"""
    print("\n=== 閱讀測驗輸入 ===")

    # 決定要輸入幾組 passage
    print(f"需要輸入的題號：{missing_nums}")
    num_passages = int(input_single("有幾組閱讀段落（passage）", "1"))

    all_questions: list[dict] = []
    remaining = list(missing_nums)

    for p in range(num_passages):
        if not remaining:
            break

        print(f"\n--- 第 {p + 1} 組閱讀段落 ---")
        passage = input_multiline("閱讀段落（passage，輸入完畢按 Enter 兩次）:")

        # 決定這組 passage 對應哪些題號
        if num_passages == 1:
            group_nums = remaining[:]
        else:
            nums_str = input_single(
                f"此段落對應的題號（用逗號分隔，剩餘：{remaining}）"
            )
            group_nums = [int(n.strip()) for n in nums_str.split(",")]

        for qnum in group_nums:
            q = input_single_question(qnum, section)
            if q:
                q["passage"] = passage
                all_questions.append(q)
                if qnum in remaining:
                    remaining.remove(qnum)

    return all_questions


def preview_question(q: dict) -> None:
    """預覽題目 JSON。"""
    print("\n--- 預覽 ---")
    display = {k: v for k, v in q.items()}
    # 截斷 passage 顯示
    if "passage" in display and len(display["passage"]) > 120:
        display["passage"] = display["passage"][:120] + "..."
    print(json.dumps(display, ensure_ascii=False, indent=2))


def confirm(prompt: str = "確認寫入？") -> bool:
    """確認操作。"""
    ans = input(f"{prompt} (y/n): ").strip().lower()
    return ans in ("y", "yes")


# === 任務處理 ===

def process_shared_english_task(task: dict, progress: dict) -> None:
    """處理共用英文試題任務（輸入一次，寫入多類科）。"""
    label = task["label"]
    missing_nums = task["missing_nums"]
    target_files = task["target_files"]

    print(f"\n{'='*60}")
    print(f"任務：{label}")
    print(f"說明：{task['description']}")
    print(f"缺少題號：{missing_nums}")
    print(f"目標檔案數：{len(target_files)}")
    print(f"{'='*60}")

    # 顯示第一個目標檔案的現有題號
    if target_files:
        sample = load_json(target_files[0])
        existing = get_existing_numbers(sample)
        dept = Path(target_files[0]).parts[-4]
        print(f"\n參考（{dept}）現有選擇題號：", end="")
        _print_number_ranges(existing)

    # 輸入題目
    if len(missing_nums) >= 3:
        questions = input_reading_comprehension(missing_nums)
    else:
        questions = []
        for qnum in missing_nums:
            q = input_single_question(qnum)
            if q:
                questions.append(q)

    if not questions:
        print("未輸入任何題目，跳過。")
        return

    # 預覽全部
    print(f"\n共輸入 {len(questions)} 題：")
    for q in questions:
        preview_question(q)

    print(f"\n將寫入以下 {len(target_files)} 個檔案：")
    for fp in target_files:
        rel = os.path.relpath(fp, EXAM_DIR)
        print(f"  {rel}")

    if not confirm():
        print("已取消。")
        return

    # 備份並寫入
    written = 0
    for fp in target_files:
        backup_file(fp)
        data = load_json(fp)
        for q in questions:
            insert_question(data, dict(q))  # 複製一份避免共用引用
        save_json(fp, data)
        written += 1

    print(f"\n已寫入 {written} 個檔案，共 {written * len(questions)} 題。")
    mark_task_completed(progress, label)


def process_single_file_task(task: dict, progress: dict) -> None:
    """處理單一檔案任務。"""
    label = task["label"]
    missing_nums = task["missing_nums"]
    target_files = task["target_files"]

    if not target_files:
        print(f"找不到目標檔案，跳過任務：{label}")
        return

    filepath = target_files[0]

    print(f"\n{'='*60}")
    print(f"任務：{label}")
    print(f"說明：{task['description']}")
    print(f"目標檔案：{os.path.relpath(filepath, EXAM_DIR)}")
    print(f"缺少題號：{missing_nums}")
    print(f"{'='*60}")

    data = load_json(filepath)
    existing = get_existing_numbers(data)
    print(f"現有選擇題號：", end="")
    _print_number_ranges(existing)

    # 輸入題目
    if len(missing_nums) >= 3:
        questions = input_reading_comprehension(missing_nums)
    else:
        questions = []
        for qnum in missing_nums:
            q = input_single_question(qnum)
            if q:
                questions.append(q)

    if not questions:
        print("未輸入任何題目，跳過。")
        return

    for q in questions:
        preview_question(q)

    if not confirm():
        print("已取消。")
        return

    backup_file(filepath)
    for q in questions:
        insert_question(data, q)
    save_json(filepath, data)

    print(f"\n已寫入 {len(questions)} 題至 {os.path.relpath(filepath, EXAM_DIR)}")
    mark_task_completed(progress, label)


def _print_number_ranges(nums: list[int]) -> None:
    """將題號列表格式化為範圍表示（如 1-22, 24-50）。"""
    if not nums:
        print("（無）")
        return

    ranges = []
    start = nums[0]
    end = nums[0]
    for n in nums[1:]:
        if n == end + 1:
            end = n
        else:
            ranges.append(f"{start}-{end}" if start != end else str(start))
            start = n
            end = n
    ranges.append(f"{start}-{end}" if start != end else str(start))
    print(", ".join(ranges))


# === CSV 批次匯入 ===

def process_batch_csv(csv_path: str) -> None:
    """從 CSV 檔案批次匯入題目。

    CSV 格式：
    json_path,number,stem,option_a,option_b,option_c,option_d,answer[,passage][,section]
    """
    if not os.path.exists(csv_path):
        print(f"找不到檔案：{csv_path}")
        return

    progress = load_progress()
    modified_files: dict[str, dict] = {}  # filepath -> data

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            json_path = row["json_path"].strip()
            if not os.path.isabs(json_path):
                json_path = str(EXAM_DIR / json_path)

            if json_path not in modified_files:
                if not os.path.exists(json_path):
                    print(f"警告：找不到 {json_path}，跳過此列")
                    continue
                modified_files[json_path] = load_json(json_path)

            data = modified_files[json_path]
            qnum = int(row["number"])

            question: dict[str, Any] = {
                "number": qnum,
                "type": "choice",
                "stem": row["stem"].strip(),
                "section": row.get("section", "乙、測驗題").strip() or "乙、測驗題",
                "answer": row["answer"].strip().upper(),
                "options": {
                    "A": row["option_a"].strip(),
                    "B": row["option_b"].strip(),
                    "C": row["option_c"].strip(),
                    "D": row["option_d"].strip(),
                },
            }

            passage = row.get("passage", "").strip()
            if passage:
                question["passage"] = passage

            insert_question(data, question)
            count += 1

    if count == 0:
        print("CSV 中沒有有效的題目資料。")
        return

    print(f"\n解析完成：{count} 題，涉及 {len(modified_files)} 個檔案。")

    # 預覽
    for fp, data in modified_files.items():
        rel = os.path.relpath(fp, EXAM_DIR)
        print(f"  {rel}")

    if not confirm("確認寫入所有檔案？"):
        print("已取消。")
        return

    for fp, data in modified_files.items():
        backup_file(fp)
        save_json(fp, data)

    print(f"\n已寫入 {count} 題至 {len(modified_files)} 個檔案。")
    mark_task_completed(progress, f"batch_{os.path.basename(csv_path)}")


# === 主程式 ===

def show_task_list(tasks: list[dict], progress: dict) -> None:
    """顯示任務清單。"""
    completed_labels = set(progress.get("completed", []))
    pending = [t for t in tasks if t["label"] not in completed_labels]
    done = [t for t in tasks if t["label"] in completed_labels]

    total_pending_qs = sum(t["total_questions"] for t in pending)
    total_done_qs = sum(t["total_questions"] for t in done)

    print(f"\n{'='*60}")
    print(f"  考古題手動補入工具")
    print(f"  進度：{len(done)}/{len(tasks)} 任務完成")
    print(f"  題目：{total_done_qs}/{total_pending_qs + total_done_qs} 題")
    print(f"{'='*60}")

    if not pending:
        print("\n  所有任務已完成！")
        if done:
            print(f"\n[已完成] {len(done)} 項任務")
            for t in done:
                print(f"  {t['id']:>3}. {t['label']} ({t['total_questions']} 題)")
        return

    # 分類顯示
    shared = [t for t in pending if t["type"] == "shared_english"]
    single = [t for t in pending if t["type"] == "single_file"]

    if shared:
        print(f"\n[待處理] 英文閱讀測驗共用試題（{len(shared)} 項）")
        for t in shared:
            print(f"  {t['id']:>3}. {t['label']} — {t['description']}，共 {t['total_questions']} 題")

    if single:
        print(f"\n[待處理] 個別檔案（{len(single)} 項）")
        for t in single:
            print(f"  {t['id']:>3}. {t['label']} — {t['description']}，共 {t['total_questions']} 題")

    if done:
        print(f"\n[已完成] {len(done)} 項任務")
        for t in done:
            print(f"  {t['id']:>3}. {t['label']}")


def interactive_mode() -> None:
    """主互動模式。"""
    print("正在掃描缺失題目...")
    tasks = scan_missing_questions()
    progress = load_progress()

    if not tasks:
        print("\n掃描完成：沒有發現缺失的題目。所有題目都已完整！")
        return

    while True:
        show_task_list(tasks, progress)

        completed_labels = set(progress.get("completed", []))
        pending = [t for t in tasks if t["label"] not in completed_labels]

        if not pending:
            break

        print()
        choice = input_single("請選擇要處理的項目編號（或 q 退出、r 重新掃描）")

        if choice.lower() in ("q", "quit", "exit"):
            print("再見！")
            break
        elif choice.lower() in ("r", "rescan"):
            print("正在重新掃描...")
            tasks = scan_missing_questions()
            continue

        try:
            task_id = int(choice)
        except ValueError:
            print("請輸入有效的編號。")
            continue

        task = next((t for t in tasks if t["id"] == task_id), None)
        if task is None:
            print(f"找不到編號 {task_id} 的任務。")
            continue

        if task["label"] in completed_labels:
            print(f"任務 {task_id} 已完成。要重新處理嗎？")
            if not confirm("重新處理？"):
                continue
            # 移除完成標記
            progress["completed"].remove(task["label"])
            save_progress(progress)

        try:
            if task["type"] == "shared_english":
                process_shared_english_task(task, progress)
            elif task["type"] == "single_file":
                process_single_file_task(task, progress)
            else:
                print(f"未知的任務類型：{task['type']}")
        except KeyboardInterrupt:
            print("\n\n已中斷。進度已儲存。")
            continue


def scan_mode() -> None:
    """掃描模式：只顯示缺失清單不輸入。"""
    print("正在掃描缺失題目...\n")
    tasks = scan_missing_questions()
    progress = load_progress()

    if not tasks:
        print("沒有發現缺失的題目。所有題目都已完整！")
        return

    show_task_list(tasks, progress)

    total_unique = sum(len(t["missing_nums"]) for t in tasks)
    total_qs = sum(t["total_questions"] for t in tasks)
    print(f"\n總計：{len(tasks)} 項任務，{total_unique} 道獨立題目，展開後 {total_qs} 題")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="考古題手動補入工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
  python tools/manual_input.py              # 互動模式
  python tools/manual_input.py --scan       # 掃描缺失清單
  python tools/manual_input.py --batch input.csv  # CSV 批次匯入
        """,
    )
    parser.add_argument(
        "--batch",
        metavar="CSV_FILE",
        help="CSV 批次匯入模式",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="僅掃描並顯示缺失清單，不進入互動模式",
    )
    parser.add_argument(
        "--reset-progress",
        action="store_true",
        help="重置進度記錄",
    )

    args = parser.parse_args()

    if args.reset_progress:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
            print("進度已重置。")
        else:
            print("沒有進度記錄。")
        return

    if args.batch:
        process_batch_csv(args.batch)
    elif args.scan:
        scan_mode()
    else:
        interactive_mode()


if __name__ == "__main__":
    main()
