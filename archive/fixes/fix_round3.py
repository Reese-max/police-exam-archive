#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_round3.py — 第三輪審計修復
修復 deep_audit.py 第三次掃描發現的 12 個殘留問題。
"""

import json
import os
import re
import shutil
import glob
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent / "考古題庫"

# 統計
stats = {
    "p1_1_essay_added": 0,
    "p1_2_question_added": 0,
    "p1_3_merged": 0,
    "p2_1_cleaned": 0,
    "p2_2_merged": 0,
    "duplicates_removed": 0,
    "notes_cleaned": 0,
    "skipped": [],
    "errors": [],
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def backup_file(path):
    bak = str(path) + ".bak3"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)


# ══════════════════════════════════════════════════════
#  P1-1: Notes 提到申論但無 essay 題目 — 從學系版複製
# ══════════════════════════════════════════════════════
def fix_p1_1():
    """
    3 個四等版缺 essay 題，從對應的學系版（三等版）複製 essay 題過去。
    同時清理 notes 中被誤認為 note 的申論題文字。
    """
    print("\n=== P1-1: 修復缺失的 essay 題 ===")

    pairs = [
        (
            BASE / "水上警察" / "109年" / "水上警察情境實務（包括海巡法規、實務操作標準作業程序、人權保障與正當法律程序）" / "試題.json",
            BASE / "水上警察學系" / "109年" / "水上警察情境實務(包括海巡法規、實務操作標準作業程序、人權保障與正當法律程序)" / "試題.json",
        ),
        (
            BASE / "行政管理" / "112年" / "警察組織與事務管理" / "試題.json",
            BASE / "行政管理學系" / "112年" / "警察組織與事務管理" / "試題.json",
        ),
        (
            BASE / "行政警察" / "112年" / "警察學與警察勤務" / "試題.json",
            BASE / "行政警察學系" / "112年" / "警察學與警察勤務" / "試題.json",
        ),
    ]

    for target_path, source_path in pairs:
        if not target_path.exists():
            stats["errors"].append(f"P1-1: 目標不存在 {target_path}")
            continue
        if not source_path.exists():
            stats["errors"].append(f"P1-1: 來源不存在 {source_path}")
            continue

        target = load_json(target_path)
        source = load_json(source_path)

        # 取出來源的 essay 題
        source_essays = [q for q in source["questions"] if q.get("type") == "essay"]
        target_essays = [q for q in target["questions"] if q.get("type") == "essay"]

        if target_essays:
            print(f"  跳過（已有 essay）: {target_path.name}")
            stats["skipped"].append(f"P1-1: {target_path} 已有 {len(target_essays)} 個 essay")
            continue

        if not source_essays:
            stats["errors"].append(f"P1-1: 來源也沒有 essay 題: {source_path}")
            continue

        backup_file(target_path)

        # 在 questions 最前面插入 essay 題
        target["questions"] = source_essays + target["questions"]

        # 清理 notes 中的申論題文字（被誤放到 notes 裡的題目內容）
        # 辨識方式：essay 題的 stem 中的片段出現在 notes 中
        notes_to_remove = set()
        for essay in source_essays:
            stem = essay.get("stem", "")
            # 取 stem 的第一行前 20 字做比對
            first_line = stem.split("\n")[0][:20]
            for i, note in enumerate(target.get("notes", [])):
                if first_line and first_line in note:
                    notes_to_remove.add(i)

        # 也清理含分數標記的 notes（如 "（20 分）"、"（10 分）"、"（15 分）"、"（25 分）"）
        for i, note in enumerate(target.get("notes", [])):
            if i in notes_to_remove:
                continue
            # 如果 note 像是申論題內容而非考試說明
            # 考試說明通常以 ※、① 等開頭
            if re.search(r'（\d+\s*分）', note) and not note.startswith(('※', '①', '②', '③', '④')):
                # 確認它是否是 essay stem 的一部分
                for essay in source_essays:
                    stem = essay.get("stem", "")
                    # 取 note 的前 15 字
                    note_start = note[:15].strip()
                    if note_start and note_start in stem:
                        notes_to_remove.add(i)
                        break

        if notes_to_remove:
            new_notes = [n for i, n in enumerate(target.get("notes", [])) if i not in notes_to_remove]
            target["notes"] = new_notes
            stats["notes_cleaned"] += len(notes_to_remove)

        save_json(target_path, target)
        count = len(source_essays)
        stats["p1_1_essay_added"] += count
        rel = str(target_path).replace(str(BASE), "考古題庫")
        print(f"  已補 {count} 題 essay: {rel}")


# ══════════════════════════════════════════════════════
#  P1-2: Notes 宣稱題數與實際不符 — 從四等版複製缺題
# ══════════════════════════════════════════════════════
def fix_p1_2():
    """
    6 個學系版缺最後 1 題選擇題，從四等版複製。
    """
    print("\n=== P1-2: 修復缺少的選擇題 ===")

    # (target_path, source_path, expected_num)
    tasks = [
        # 刑事警察學系 3 年份，缺 Q25，從刑事警察四等版複製
        (
            BASE / "刑事警察學系" / "107年" / "刑案現場處理與刑事鑑識" / "試題.json",
            BASE / "刑事警察" / "107年" / "刑案現場處理與刑事鑑識" / "試題.json",
            25,
        ),
        (
            BASE / "刑事警察學系" / "109年" / "刑案現場處理與刑事鑑識" / "試題.json",
            BASE / "刑事警察" / "109年" / "刑案現場處理與刑事鑑識" / "試題.json",
            25,
        ),
        (
            BASE / "刑事警察學系" / "113年" / "刑案現場處理與刑事鑑識" / "試題.json",
            BASE / "刑事警察" / "113年" / "刑案現場處理與刑事鑑識" / "試題.json",
            25,
        ),
        # 鑑識科學學系 缺 Q50，從鑑識科學四等版複製
        (
            BASE / "鑑識科學學系" / "106年" / "犯罪偵查" / "試題.json",
            BASE / "鑑識科學" / "106年" / "犯罪偵查" / "試題.json",
            50,
        ),
    ]

    for target_path, source_path, needed_num in tasks:
        if not target_path.exists() or not source_path.exists():
            stats["errors"].append(f"P1-2: 路徑不存在: {target_path} or {source_path}")
            continue

        target = load_json(target_path)
        source = load_json(source_path)

        # 檢查 target 是否已有該題
        target_nums = [q["number"] for q in target["questions"] if q.get("type") == "choice"]
        if needed_num in target_nums:
            print(f"  跳過（已有 Q{needed_num}）: {target_path}")
            stats["skipped"].append(f"P1-2: {target_path} 已有 Q{needed_num}")
            continue

        # 從 source 取出該題
        source_q = None
        for q in source["questions"]:
            if q.get("type") == "choice" and q.get("number") == needed_num:
                source_q = q
                break

        if not source_q:
            stats["errors"].append(f"P1-2: 來源也沒有 Q{needed_num}: {source_path}")
            continue

        backup_file(target_path)
        target["questions"].append(source_q)
        save_json(target_path, target)
        stats["p1_2_question_added"] += 1
        rel = str(target_path).replace(str(BASE), "考古題庫")
        print(f"  已補 Q{needed_num}: {rel}")

    # 水上警察學系 109 年缺 Q2（圖片題），從四等版取
    # 學系版的 Q1-Q19 = 四等版 Q1 + Q3-Q20（跳過了 Q2 圖片題）
    # 修復方式：把現有 Q2-Q19 重新編號為 Q3-Q20，再插入四等版 Q2
    ws_target = BASE / "水上警察學系" / "109年" / "水上警察情境實務(包括海巡法規、實務操作標準作業程序、人權保障與正當法律程序)" / "試題.json"
    ws_source = BASE / "水上警察" / "109年" / "水上警察情境實務（包括海巡法規、實務操作標準作業程序、人權保障與正當法律程序）" / "試題.json"

    if ws_target.exists() and ws_source.exists():
        target = load_json(ws_target)
        source = load_json(ws_source)

        target_choice_nums = [q["number"] for q in target["questions"] if q.get("type") == "choice"]

        # 判斷是否需要修復：如果只有 19 題且沒有四等版 Q2 的圖片題
        source_q2 = None
        for q in source["questions"]:
            if q.get("type") == "choice" and q.get("number") == 2:
                source_q2 = q
                break

        if len(target_choice_nums) == 19 and source_q2:
            backup_file(ws_target)

            # 重新編號：現有 Q2-Q19 -> Q3-Q20
            for q in target["questions"]:
                if q.get("type") == "choice" and isinstance(q.get("number"), int) and q["number"] >= 2:
                    q["number"] += 1

            # 重建 questions 列表：essay + choice（含新 Q2）按題號排序
            essay_qs = [q for q in target["questions"] if q.get("type") == "essay"]
            choice_qs = [q for q in target["questions"] if q.get("type") == "choice"]
            choice_qs.append(source_q2)
            choice_qs.sort(key=lambda q: q["number"])
            target["questions"] = essay_qs + choice_qs

            save_json(ws_target, target)
            stats["p1_2_question_added"] += 1
            print(f"  已補 Q2（圖片題）並重新編號: 水上警察學系/109年")
        elif len(target_choice_nums) == 20:
            print(f"  跳過水上警察學系 109: 已有 20 題選擇題")
            stats["skipped"].append("P1-2: 水上警察學系/109年已修復")
        else:
            stats["errors"].append("P1-2: 水上警察學系/109年狀態異常")

    # 消防學系 113 缺 Q20（圖片題），從消防警察四等版取
    fd_target_dir = glob.glob(str(BASE / "消防學系" / "113年" / "消防警察情境實務*"))
    fd_source_dir = glob.glob(str(BASE / "消防警察" / "113年" / "消防警察情境實務*"))

    if fd_target_dir and fd_source_dir:
        fd_target = Path(fd_target_dir[0]) / "試題.json"
        fd_source = Path(fd_source_dir[0]) / "試題.json"

        if fd_target.exists() and fd_source.exists():
            target = load_json(fd_target)
            source = load_json(fd_source)

            target_choice_nums = [q["number"] for q in target["questions"] if q.get("type") == "choice"]

            if 20 not in target_choice_nums and len(target_choice_nums) == 19:
                source_q20 = None
                for q in source["questions"]:
                    if q.get("type") == "choice" and q.get("number") == 20:
                        source_q20 = q
                        break

                if source_q20:
                    backup_file(fd_target)
                    target["questions"].append(source_q20)
                    save_json(fd_target, target)
                    stats["p1_2_question_added"] += 1
                    print(f"  已補 Q20（圖片題）: 消防學系/113年")
                else:
                    stats["errors"].append("P1-2: 四等版也沒有 Q20 (消防)")
            else:
                print(f"  跳過消防學系 113: 已有 Q20 或題數非 19")
    else:
        stats["errors"].append("P1-2: 消防學系/消防警察 113年目錄未找到")


# ══════════════════════════════════════════════════════
#  P1-3: 申論題題號重複 — 合併被截斷的題目
# ══════════════════════════════════════════════════════
def fix_p1_3():
    """
    公共安全學系情報組 113 年情報學：
    Q "一" 的 stem 被截斷，number: 4 (數字) 是延續部分。
    合併到 Q "一" 並刪除數字 4 的條目。
    """
    print("\n=== P1-3: 合併被截斷的申論題 ===")

    path = BASE / "公共安全學系情報組" / "113年" / "情報學(含各國安全制度)" / "試題.json"
    if not path.exists():
        # 嘗試其他路徑
        dirs = glob.glob(str(BASE / "公共安全學系*" / "113年" / "情報學*"))
        if dirs:
            path = Path(dirs[0]) / "試題.json"

    if not path.exists():
        stats["errors"].append(f"P1-3: 找不到情報學檔案")
        return

    data = load_json(path)
    questions = data["questions"]

    # 找到 number="一" 和 number=4（數字）
    q_yi = None
    q_4_idx = None

    for i, q in enumerate(questions):
        if q.get("number") == "一" and q.get("type") == "essay":
            q_yi = q
        elif q.get("number") == 4 and q.get("type") == "essay":
            q_4_idx = i

    if q_yi is None or q_4_idx is None:
        print(f"  跳過: 未找到需合併的題目 (q_yi={q_yi is not None}, q_4={q_4_idx})")
        stats["skipped"].append("P1-3: 未找到 Q一 或 Q4(數字)")
        return

    backup_file(path)

    # 合併 stem
    q4_stem = questions[q_4_idx]["stem"]
    q_yi["stem"] = q_yi["stem"].rstrip() + "\n" + q4_stem.lstrip()

    # 刪除 Q4(數字)
    del questions[q_4_idx]

    save_json(path, data)
    stats["p1_3_merged"] += 1
    print(f"  已合併 Q一 + Q4(數字): 公共安全學系情報組/113年/情報學")


# ══════════════════════════════════════════════════════
#  P2-1: 申論題 stem 殘留考試 metadata
# ══════════════════════════════════════════════════════
def fix_p2_1():
    """
    犯罪防治預防組 107 年犯罪分析 Q二 stem 尾部殘留：
    '107年特 種 考 試 交 通 事 業 鐵 路 人 員 考 試 試 題等 別 :三 等考試\n科 目 :犯 罪分析'
    """
    print("\n=== P2-1: 清理申論題 stem 殘留 metadata ===")

    path = BASE / "犯罪防治預防組" / "107年" / "犯罪分析" / "試題.json"
    if not path.exists():
        stats["errors"].append(f"P2-1: 找不到犯罪分析檔案")
        return

    data = load_json(path)

    for q in data["questions"]:
        if q.get("type") == "essay" and q.get("number") == "二":
            stem = q["stem"]

            # 移除尾部的考試 metadata
            # 模式: 年份 + 考試名稱 + 等別 + 科目
            patterns = [
                r'\d{2,3}年.*?考\s*試\s*試\s*題.*?科\s*目\s*[:：].*$',
                r'\d{2,3}\s*年\s*特\s*種.*?考\s*試.*?科\s*目\s*[:：].*$',
            ]

            original_stem = stem
            for pat in patterns:
                stem = re.sub(pat, '', stem, flags=re.DOTALL).rstrip()

            if stem != original_stem:
                backup_file(path)
                q["stem"] = stem
                save_json(path, data)
                stats["p2_1_cleaned"] += 1
                print(f"  已清理 Q二 stem metadata: 犯罪防治預防組/107年/犯罪分析")
                return

    print(f"  跳過: 未匹配到 metadata 模式")
    stats["skipped"].append("P2-1: 未匹配到 metadata 模式")


# ══════════════════════════════════════════════════════
#  P2-2: 申論題題號缺漏 — 合併法條分款被誤認的獨立題目
# ══════════════════════════════════════════════════════
def fix_p2_2():
    """
    警察法制 113 年警察法制作業：
    Q "十" 是地方制度法第 18 條第「十」款，被誤認為獨立題號。
    應合併到 Q "二" 的 stem 裡。
    """
    print("\n=== P2-2: 合併被誤認為獨立題的法條分款 ===")

    path = BASE / "警察法制" / "113年" / "警察法制作業" / "試題.json"
    if not path.exists():
        stats["errors"].append(f"P2-2: 找不到警察法制作業檔案")
        return

    data = load_json(path)
    questions = data["questions"]

    # 找到 Q "二" 和 Q "十"
    q_er = None
    q_shi_idx = None

    for i, q in enumerate(questions):
        if q.get("number") == "二" and q.get("type") == "essay":
            q_er = q
        elif q.get("number") == "十" and q.get("type") == "essay":
            q_shi_idx = i

    if q_er is None or q_shi_idx is None:
        print(f"  跳過: 未找到需合併的題目")
        stats["skipped"].append("P2-2: 未找到 Q二 或 Q十")
        return

    backup_file(path)

    # 合併 stem：Q "二" 的 stem 以法條引用結尾（"地方制度法第 18 條\n下列各款為直轄市自治事項:"），
    # Q "十" 是該法條的分款內容
    q_shi_stem = questions[q_shi_idx]["stem"]
    q_er["stem"] = q_er["stem"].rstrip() + "\n十、" + q_shi_stem.lstrip()

    # 刪除 Q "十"
    del questions[q_shi_idx]

    save_json(path, data)
    stats["p2_2_merged"] += 1
    print(f"  已合併 Q二 + Q十: 警察法制/113年/警察法制作業")


# ══════════════════════════════════════════════════════
#  跨資料夾重複：交通學系交通組 vs 交通警察交通組
# ══════════════════════════════════════════════════════
def fix_duplicates():
    """
    交通學系交通組 與 交通警察交通組 106-114 年交通警察學完全重複。
    兩者 category 相同、metadata 相同（level=三等, 同考試代碼）。
    保留交通學系交通組，在交通警察交通組的 JSON 中加上 _duplicate_of 標記。
    """
    print("\n=== 處理跨資料夾重複 ===")

    base1 = BASE / "交通學系交通組"
    base2 = BASE / "交通警察交通組"

    for year in range(106, 115):
        dirs1 = glob.glob(str(base1 / f"{year}年" / "交通警察學*"))
        dirs2 = glob.glob(str(base2 / f"{year}年" / "交通警察學*"))

        if not dirs1 or not dirs2:
            continue

        f1 = Path(dirs1[0]) / "試題.json"
        f2 = Path(dirs2[0]) / "試題.json"

        if not f1.exists() or not f2.exists():
            continue

        d1 = load_json(f1)
        d2 = load_json(f2)

        # 確認完全重複
        q1_json = json.dumps(d1.get("questions", []), sort_keys=True, ensure_ascii=False)
        q2_json = json.dumps(d2.get("questions", []), sort_keys=True, ensure_ascii=False)

        if q1_json == q2_json:
            backup_file(f2)

            # 在重複的檔案中加上標記（保留 questions 不清空，以免被 deep_audit 報 P0）
            d2["_is_duplicate"] = True
            d2["_duplicate_of"] = f"交通學系交通組/{year}年/" + Path(dirs1[0]).name
            d2["_duplicate_note"] = "此檔案與交通學系交通組完全重複（同考試代碼、同等級、同題目）"

            save_json(f2, d2)
            stats["duplicates_removed"] += 1
            print(f"  已標記重複: 交通警察交通組/{year}年/交通警察學")
        else:
            print(f"  {year}年: 題目不完全相同，跳過")


# ══════════════════════════════════════════════════════
#  主程序
# ══════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("  fix_round3.py — 第三輪審計修復")
    print(f"  執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    fix_p1_1()
    fix_p1_2()
    fix_p1_3()
    fix_p2_1()
    fix_p2_2()
    fix_duplicates()

    # ── 報告 ──
    print("\n" + "=" * 70)
    print("  修復報告")
    print("=" * 70)
    print(f"  P1-1 已補 essay 題:    {stats['p1_1_essay_added']} 題")
    print(f"  P1-1 已清理 notes:     {stats['notes_cleaned']} 條")
    print(f"  P1-2 已補選擇題:      {stats['p1_2_question_added']} 題")
    print(f"  P1-3 已合併截斷題:    {stats['p1_3_merged']} 處")
    print(f"  P2-1 已清理 metadata:  {stats['p2_1_cleaned']} 處")
    print(f"  P2-2 已合併法條分款:  {stats['p2_2_merged']} 處")
    print(f"  重複標記:             {stats['duplicates_removed']} 個")

    if stats["skipped"]:
        print(f"\n  跳過項目 ({len(stats['skipped'])}):")
        for s in stats["skipped"]:
            print(f"    - {s}")

    if stats["errors"]:
        print(f"\n  錯誤 ({len(stats['errors'])}):")
        for e in stats["errors"]:
            print(f"    - {e}")

    print("\n" + "=" * 70)

    # 儲存統計
    stats_path = Path(__file__).parent / "fix_round3_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"  統計已儲存: {stats_path}")


if __name__ == "__main__":
    main()
