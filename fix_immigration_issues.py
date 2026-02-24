#!/usr/bin/env python3
"""
國境警察學系移民組題庫綜合修復腳本
========================
修復「考古題庫/國境警察學系移民組/」下所有 試題.json 的已知問題。

用法：
    python fix_immigration_issues.py                    # dry-run 模式（僅列出修改，不寫入）
    python fix_immigration_issues.py --apply            # 實際寫入修改
    python fix_immigration_issues.py --fix-pua          # 僅修復 PUA/控制字元
    python fix_immigration_issues.py --fix-sc2tc        # 僅修復簡繁轉換
    python fix_immigration_issues.py --fix-legal        # 僅修復法律用語
    python fix_immigration_issues.py --fix-empty-opts   # 僅修復空白選項
    python fix_immigration_issues.py --fix-metadata     # 僅補全 metadata
    python fix_immigration_issues.py --fix-brackets     # 僅統一括號（含目錄重命名）
    python fix_immigration_issues.py --fix-square       # 僅標記 □ 符號
    python fix_immigration_issues.py --fix-short-stem   # 僅標記過短題幹

作者：Claude Code 自動生成
日期：2026-02-24
"""

import argparse
import json
import glob
import os
import re
import shutil
import sys
from collections import defaultdict
from typing import Any


# ============================================================
# 常數定義
# ============================================================

BASE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "考古題庫", "國境警察學系移民組"
)

EXAM_NAME = "移民行政人員特種考試"

# 簡體→繁體對照表：僅收錄「明確簡體字」（在繁體中絕不會使用的字形）
# 排除所有一對多或在繁體中也合法的字形（如 卷/捲、了/瞭、才/纔、台/臺 等）
# 這些字在繁體中僅有一個對應，不會有歧義
SIMPLE_SC2TC_MAP = {
    # === 明確簡體字（繁體中不存在此字形的用法）===
    "没": "沒",
    "内": "內",
    "与": "與",
    "为": "為",
    "对": "對",
    "关": "關",
    "会": "會",
    "从": "從",
    "来": "來",
    "时": "時",
    "进": "進",
    "过": "過",
    "还": "還",
    "这": "這",
    "种": "種",
    "应": "應",
    "该": "該",
    "将": "將",
    "并": "並",
    "开": "開",
    "现": "現",
    "经": "經",
    "问": "問",
    "题": "題",
    "动": "動",
    "机": "機",
    "区": "區",
    "华": "華",
    "国": "國",
    "际": "際",
    "实": "實",
    "业": "業",
    "学": "學",
    "认": "認",
    "证": "證",
    "办": "辦",
    "议": "議",
    "设": "設",
    "让": "讓",
    "说": "說",
    "请": "請",
    "调": "調",
    "费": "費",
    "资": "資",
    "运": "運",
    "达": "達",
    "选": "選",
    "处": "處",
    "组": "組",
    "织": "織",
    "条": "條",
    "规": "規",
    "则": "則",
    "约": "約",
    "纪": "紀",
    "级": "級",
    "报": "報",
    "护": "護",
    "权": "權",
    "义": "義",
    "门": "門",
    "长": "長",
    "乡": "鄉",
    "县": "縣",
    "审": "審",
    "专": "專",
    "属": "屬",
    "决": "決",
    "担": "擔",
    "据": "據",
    "杂": "雜",
    "类": "類",
    "体": "體",
    "确": "確",
    "称": "稱",
    "独": "獨",
    "产": "產",
    "广": "廣",
    "边": "邊",
    "适": "適",
    "违": "違",
    "远": "遠",
    "签": "簽",
    "历": "歷",
    "离": "離",
    "难": "難",
    "岁": "歲",
    "亿": "億",
    "仅": "僅",
    "价": "價",
    "众": "眾",
    "优": "優",
    "传": "傳",
    "伤": "傷",
    "补": "補",
    "够": "夠",
    "检": "檢",
    "构": "構",
    "极": "極",
    "标": "標",
    "档": "檔",
    "欢": "歡",
    "环": "環",
    "电": "電",
    "节": "節",
    "获": "獲",
    "虑": "慮",
    "观": "觀",
    "记": "記",
    "许": "許",
    "评": "評",
    "质": "質",
    "购": "購",
    "输": "輸",
    "连": "連",
    "陆": "陸",
    "须": "須",
    "飞": "飛",
    "驻": "駐",
    "龄": "齡",
    "届": "屆",
    "辞": "辭",
    "数": "數",
    "万": "萬",
    "当": "當",
    "蜡": "蠟",
    "湾": "灣",
    "礼": "禮",
    "伙": "夥",
    "咨": "諮",
    "扎": "紮",
    "挂": "掛",
    "洒": "灑",
}

# 注意：以下字在繁體中也常用，不做轉換，以避免過度修正：
# 卷（試卷）、了（助詞）、才（才能）、台（台灣）、后（皇后）、
# 干（干預）、于（於/于 皆可）、余（我/餘）、里（鄰里/裏）、
# 只（只有/隻）、系（系統/係）、面、云（人名）、谷、松、折、范（姓）、
# 制（制度）、复（復/複）、发（發/髮）、征（征/徵）、斗（北斗/鬥）、
# 几（茶几/幾）、尽（盡/儘）、冲（沖/衝）、占（占卜/佔）、
# 布（布料/佈告）、核（核心/覈）、准（准許/準）、秘（秘密/祕）、
# 群（群眾/羣）、背（背景/揹）、吃（吃飯/喫）、注（注意/註）、
# 游（游泳/遊）、采（采風/採）、借（借用/藉）、床（床鋪/牀）、
# 峰（山峰/峯）、欲（欲望/慾）、局（局面/侷）、凶（凶手/兇）、
# 症（症狀/癥）、表（表示/錶）、回（回來/迴）、搜（搜尋/蒐）、
# 郁（郁悶/鬱）、巨（巨大/鉅）、厘（厘米/釐）、尸（尸位/屍）、
# 辟（開辟/闢）、舍（舍棄/捨）、蒙（蒙古/矇）、致（致敬/緻）、
# 咸（鹹/咸 皆有）、夫（丈夫/伕）、戚（親戚/慼）、粽（粽子/糉）、
# 梁（樑/梁 皆有）、克（克服/剋）、岩（岩石/巖）、怀、雇（雇用/僱用 台灣皆可）、
# 台（臺/台 台灣正式皆可）


# ============================================================
# 工具函式
# ============================================================

def load_json(filepath: str) -> dict:
    """讀取 JSON 檔案"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filepath: str, data: dict) -> None:
    """寫入 JSON 檔案"""
    with open(filepath, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def backup_file(filepath: str) -> str:
    """備份檔案（.bak），回傳備份路徑"""
    bak_path = filepath + ".bak"
    if not os.path.exists(bak_path):
        shutil.copy2(filepath, bak_path)
    return bak_path


def extract_year(filepath: str) -> str:
    """從路徑中擷取年份（如 '107年'）"""
    normalized = filepath.replace("\\", "/")
    parts = normalized.split("/")
    for p in parts:
        if re.match(r"^\d{3}年$", p):
            return p
    return ""


def extract_level_from_dirname(dirname: str) -> str:
    """從目錄名稱擷取等級（如 '[三等]'→'三等'）"""
    m = re.search(r"\[([二三四]等)\]", dirname)
    return m.group(1) if m else ""


def extract_subject_from_dirname(dirname: str) -> str:
    """從目錄名稱擷取科目名稱（去除等級前綴）"""
    # 移除 "[三等] " 前綴
    cleaned = re.sub(r"^\[[二三四]等\]\s*", "", dirname)
    return cleaned


def deep_text_scan(obj: Any) -> str:
    """遞迴掃描 JSON 物件中所有文字"""
    if isinstance(obj, str):
        return obj
    elif isinstance(obj, list):
        return " ".join(deep_text_scan(item) for item in obj)
    elif isinstance(obj, dict):
        return " ".join(deep_text_scan(v) for v in obj.values())
    return ""


def deep_apply(obj: Any, func) -> Any:
    """遞迴對 JSON 物件中所有字串套用 func"""
    if isinstance(obj, str):
        return func(obj)
    elif isinstance(obj, list):
        return [deep_apply(item, func) for item in obj]
    elif isinstance(obj, dict):
        return {k: deep_apply(v, func) for k, v in obj.items()}
    return obj


# ============================================================
# 修復函式
# ============================================================

class FixReport:
    """統計修復報告"""

    def __init__(self):
        self.stats = defaultdict(int)
        self.details = defaultdict(list)

    def add(self, category: str, detail: str):
        self.stats[category] += 1
        self.details[category].append(detail)

    def print_summary(self):
        print("\n" + "=" * 70)
        print("修復統計報告")
        print("=" * 70)
        total = 0
        for cat in sorted(self.stats.keys()):
            count = self.stats[cat]
            total += count
            print(f"  [{cat}] : {count} 處")
        print(f"\n  總計修復/標記 : {total} 處")
        print("=" * 70)

    def print_details(self):
        for cat in sorted(self.details.keys()):
            items = self.details[cat]
            print(f"\n--- [{cat}] 共 {len(items)} 處 ---")
            for item in items:
                print(f"  {item}")


# ------ 1. PUA/NULL/控制字元清理 ------

def clean_control_chars(text: str) -> str:
    """移除 NULL、PUA、零寬字元等控制字元"""
    # NULL
    text = text.replace("\x00", "")
    # PUA 字元 (U+E000 - U+F8FF)
    text = re.sub(r"[\uE000-\uF8FF]", "", text)
    # 零寬字元
    text = re.sub(r"[\u200B-\u200F\u202A-\u202E\uFEFF\u2060-\u2064]", "", text)
    # 其他 C0/C1 控制字元（保留 \n \r \t）
    text = re.sub(r"[\x01-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]", "", text)
    return text


def fix_pua(data: dict, filepath: str, report: FixReport) -> dict:
    """修復 PUA/NULL/控制字元"""
    original_text = deep_text_scan(data)
    cleaned_data = deep_apply(data, clean_control_chars)
    cleaned_text = deep_text_scan(cleaned_data)

    if original_text != cleaned_text:
        # 統計差異字元
        diff_chars = set()
        for o, c in zip(original_text, cleaned_text):
            if o != c:
                diff_chars.add(repr(o))
        if len(original_text) != len(cleaned_text):
            # 有被移除的字元
            removed_count = len(original_text) - len(cleaned_text)
            report.add("PUA/控制字元", f"{filepath} - 移除 {removed_count} 個字元")
        else:
            report.add("PUA/控制字元", f"{filepath} - 替換字元: {diff_chars}")

    return cleaned_data


# ------ 2. 簡體中文 → 繁體中文 ------

def fix_sc2tc(data: dict, filepath: str, report: FixReport) -> dict:
    """修復簡繁混用（使用保守的手動映射，避免過度轉換）"""
    # 不使用 OpenCC s2t，因為它太激進：
    # 會把「試卷→試捲」「了→瞭」「才→纔」「台灣→臺灣」等都轉換
    # 這些在台灣繁體中都是合法且常用的寫法

    def convert_text(text: str) -> str:
        for sc, tc in SIMPLE_SC2TC_MAP.items():
            text = text.replace(sc, tc)
        return text

    original_text = deep_text_scan(data)
    converted_data = deep_apply(data, convert_text)
    converted_text = deep_text_scan(converted_data)

    if original_text != converted_text:
        # 找出被轉換的字
        changed_chars = {}
        i_orig = 0
        i_conv = 0
        orig_str = original_text
        conv_str = converted_text
        # 簡單逐字比對（長度可能不同，但 s2t 通常一對一）
        min_len = min(len(orig_str), len(conv_str))
        for i in range(min_len):
            if orig_str[i] != conv_str[i]:
                key = f"{orig_str[i]}→{conv_str[i]}"
                changed_chars[key] = changed_chars.get(key, 0) + 1

        changes_str = ", ".join(f"'{k}'x{v}" for k, v in list(changed_chars.items())[:10])
        report.add("簡繁轉換", f"{filepath} - {changes_str}")

    return converted_data


# ------ 3. 法律用語修正 ------

def fix_legal_terms(data: dict, filepath: str, report: FixReport) -> dict:
    """修正法律用語 OCR 錯誤"""
    # 114年三等法學知識第15題 選項D: 「出入國移民法」→「入出國及移民法」
    # 這是 OCR 錯誤：正式名稱是「入出國及移民法」
    # 注意：某些語境中「出入國」可能是原始試題用語，需要根據上下文判斷

    year = extract_year(filepath)
    questions = data.get("questions", [])
    modified = False

    for q in questions:
        stem = q.get("stem", "")
        options = q.get("options", {})

        # 搜尋「出入國移民法」（缺少「及」且前後顛倒）
        # 這明確是 OCR 錯誤，正式名稱中「入出國」在前、有「及」字
        for key in list(options.keys()):
            val = options[key]
            if "出入國移民法" in val:
                # 這是 OCR 錯誤：正確應為「入出國及移民法」
                new_val = val.replace("出入國移民法", "入出國及移民法")
                options[key] = new_val
                report.add("法律用語", f"{filepath} Q{q.get('number')} 選項{key}: "
                           f"「出入國移民法」→「入出國及移民法」")
                modified = True

        if "出入國移民法" in stem:
            new_stem = stem.replace("出入國移民法", "入出國及移民法")
            q["stem"] = new_stem
            report.add("法律用語", f"{filepath} Q{q.get('number')} 題幹: "
                       f"「出入國移民法」→「入出國及移民法」")
            modified = True

    return data


# ------ 4. 空白選項修復 ------

def fix_empty_options(data: dict, filepath: str, report: FixReport) -> dict:
    """修復空白選項"""
    year = extract_year(filepath)
    questions = data.get("questions", [])

    for q in questions:
        options = q.get("options", {})
        if not options:
            continue

        for key, val in options.items():
            if val is not None and val.strip() == "":
                # 113年三等入出國法規第19題
                q_num = q.get("number")
                if year == "113年" and q_num == 19 and key == "A":
                    # 其他選項: B="僅1345", C="僅345", D="僅3"
                    # 答案是 B="僅1345"
                    # 題幹列出 12345 五個項目，A 應該是全選
                    # 合理推斷 A = "12345"（即全部皆是）
                    options[key] = "12345"
                    report.add("空白選項", f"{filepath} Q{q_num} 選項{key}: "
                               f"空白 → 「12345」（從上下文推斷：B=僅1345, C=僅345, D=僅3）")
                else:
                    # 其他空白選項，加註記但不亂填
                    notes = q.get("notes", "")
                    if isinstance(notes, list):
                        notes_list = notes
                    else:
                        notes_list = [notes] if notes else []
                    note_msg = f"選項{key}為空白，可能為 OCR 遺漏"
                    if note_msg not in notes_list:
                        notes_list.append(note_msg)
                        q["notes"] = notes_list
                    report.add("空白選項", f"{filepath} Q{q.get('number')} "
                               f"選項{key}: 空白（已加註記，未填入值）")

    return data


# ------ 5. Metadata 補全 ------

def fix_metadata(data: dict, filepath: str, report: FixReport) -> dict:
    """補全 metadata"""
    meta = data.setdefault("metadata", {})
    dirname = os.path.basename(os.path.dirname(filepath))
    year = extract_year(filepath)

    changes = []

    # 補 subject
    if not meta.get("subject"):
        subject = extract_subject_from_dirname(dirname)
        if subject:
            meta["subject"] = subject
            changes.append(f"subject=「{subject}」")

    # 補 exam_name
    # 注意：已有 exam_name 為「一般警察人員考試」的是共用科目（國文、法學知識），
    # 但它們放在國境警察學系移民組目錄下，所以統一設為國境警察學系移民組
    if not meta.get("exam_name") or meta.get("exam_name") == "一般警察人員考試":
        old_name = meta.get("exam_name", "")
        meta["exam_name"] = EXAM_NAME
        if old_name and old_name != EXAM_NAME:
            changes.append(f"exam_name=「{old_name}」→「{EXAM_NAME}」")
        elif not old_name:
            changes.append(f"exam_name=「{EXAM_NAME}」")

    # 補 level
    if not meta.get("level"):
        level = extract_level_from_dirname(dirname)
        if level:
            meta["level"] = level
            changes.append(f"level=「{level}」")

    # 補 year（從目錄名推導）
    if not meta.get("year") and year:
        # 轉成民國年數字
        year_num = year.replace("年", "")
        meta["year"] = int(year_num) if year_num.isdigit() else year_num
        changes.append(f"year={meta['year']}")

    if changes:
        report.add("Metadata補全", f"{filepath} - {', '.join(changes)}")

    return data


# ------ 6. 括號統一化（目錄重命名 + JSON subject 更新） ------

def find_dirs_with_half_brackets(base_dir: str) -> list:
    """找出所有含半形括號的科目目錄"""
    result = []
    for year_dir in sorted(os.listdir(base_dir)):
        year_path = os.path.join(base_dir, year_dir)
        if not os.path.isdir(year_path) or not re.match(r"^\d{3}年$", year_dir):
            continue
        for subj_dir in sorted(os.listdir(year_path)):
            subj_path = os.path.join(year_path, subj_dir)
            if not os.path.isdir(subj_path):
                continue
            if "(" in subj_dir or ")" in subj_dir:
                new_name = subj_dir.replace("(", "（").replace(")", "）")
                if new_name != subj_dir:
                    result.append((subj_path, os.path.join(year_path, new_name), subj_dir, new_name))
    return result


def fix_brackets(base_dir: str, apply: bool, report: FixReport) -> dict:
    """
    統一半形括號為全形括號。
    回傳 {舊路徑: 新路徑} 映射，供其他修復使用。
    """
    dirs_to_rename = find_dirs_with_half_brackets(base_dir)
    rename_map = {}

    if not dirs_to_rename:
        return rename_map

    print(f"\n--- 括號統一化：共 {len(dirs_to_rename)} 個目錄需要改名 ---")
    for old_path, new_path, old_name, new_name in dirs_to_rename:
        print(f"  {old_name}")
        print(f"    → {new_name}")
        report.add("括號統一化", f"{old_path} → {new_name}")

        if apply:
            # 檢查目標是否已存在
            if os.path.exists(new_path):
                print(f"  [警告] 目標目錄已存在，跳過: {new_path}")
                continue
            os.rename(old_path, new_path)
            rename_map[old_path] = new_path

            # 更新該目錄下 JSON 的 subject 欄位
            json_path = os.path.join(new_path, "試題.json")
            if os.path.exists(json_path):
                data = load_json(json_path)
                meta = data.get("metadata", {})
                if meta.get("subject"):
                    old_subj = meta["subject"]
                    new_subj = old_subj.replace("(", "（").replace(")", "）")
                    if old_subj != new_subj:
                        meta["subject"] = new_subj
                        save_json(json_path, data)
        else:
            rename_map[old_path] = new_path

    return rename_map


# ------ 7. □ 方塊符號標記 ------

def fix_square_marks(data: dict, filepath: str, report: FixReport) -> dict:
    """找出含 □ 的題目，在 notes 加註"""
    questions = data.get("questions", [])

    for q in questions:
        all_text = deep_text_scan(q)
        if "□" in all_text:
            # 確保 notes 是 list
            notes = q.get("notes", "")
            if isinstance(notes, str):
                notes_list = [notes] if notes else []
            elif isinstance(notes, list):
                notes_list = notes
            else:
                notes_list = []

            note_msg = "含無法辨識字元"
            if note_msg not in notes_list:
                notes_list.append(note_msg)
                q["notes"] = notes_list
                report.add("□符號標記", f"{filepath} Q{q.get('number')}: 含 □ 字元")

    return data


# ------ 8. 過短題目標記 ------

def fix_short_stems(data: dict, filepath: str, report: FixReport) -> dict:
    """找出 stem < 10 字元的申論題，加註"""
    questions = data.get("questions", [])

    for q in questions:
        if q.get("type") != "essay":
            continue
        stem = q.get("stem", "")
        # 計算有效長度（去除空白和換行）
        effective = stem.strip().replace("\n", "").replace(" ", "")
        if len(effective) < 10:
            notes = q.get("notes", "")
            if isinstance(notes, str):
                notes_list = [notes] if notes else []
            elif isinstance(notes, list):
                notes_list = notes
            else:
                notes_list = []

            note_msg = "題幹可能不完整"
            if note_msg not in notes_list:
                notes_list.append(note_msg)
                q["notes"] = notes_list
                report.add("過短題幹", f"{filepath} Q{q.get('number')}: "
                           f"stem={repr(stem[:30])}（{len(effective)}字）")

    return data


# ============================================================
# 主流程
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="國境警察學系移民組題庫綜合修復腳本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
  python fix_immigration_issues.py                 # dry-run 模式
  python fix_immigration_issues.py --apply         # 實際執行所有修復
  python fix_immigration_issues.py --fix-pua       # 僅修復 PUA 字元
  python fix_immigration_issues.py --fix-sc2tc --fix-metadata --apply  # 組合修復
        """
    )
    parser.add_argument("--apply", action="store_true",
                        help="實際寫入修改（預設為 dry-run 模式）")
    parser.add_argument("--fix-pua", action="store_true",
                        help="修復 PUA/NULL/控制字元")
    parser.add_argument("--fix-sc2tc", action="store_true",
                        help="修復簡繁轉換")
    parser.add_argument("--fix-legal", action="store_true",
                        help="修復法律用語")
    parser.add_argument("--fix-empty-opts", action="store_true",
                        help="修復空白選項")
    parser.add_argument("--fix-metadata", action="store_true",
                        help="補全 metadata")
    parser.add_argument("--fix-brackets", action="store_true",
                        help="統一括號（含目錄重命名）")
    parser.add_argument("--fix-square", action="store_true",
                        help="標記 □ 符號")
    parser.add_argument("--fix-short-stem", action="store_true",
                        help="標記過短題幹")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="顯示詳細修復內容")

    args = parser.parse_args()

    # 如果沒有指定任何 --fix-xxx，則預設全部啟用
    fix_flags = [args.fix_pua, args.fix_sc2tc, args.fix_legal,
                 args.fix_empty_opts, args.fix_metadata, args.fix_brackets,
                 args.fix_square, args.fix_short_stem]
    if not any(fix_flags):
        args.fix_pua = True
        args.fix_sc2tc = True
        args.fix_legal = True
        args.fix_empty_opts = True
        args.fix_metadata = True
        args.fix_brackets = True
        args.fix_square = True
        args.fix_short_stem = True

    return args


def main():
    args = parse_args()
    report = FixReport()

    mode_label = "套用模式" if args.apply else "DRY-RUN 模式（不會寫入任何變更）"
    print(f"\n{'=' * 70}")
    print(f"國境警察學系移民組題庫綜合修復腳本")
    print(f"模式: {mode_label}")
    print(f"基礎目錄: {BASE_DIR}")
    print(f"{'=' * 70}")

    if not os.path.isdir(BASE_DIR):
        print(f"[錯誤] 找不到目錄: {BASE_DIR}")
        sys.exit(1)

    # 啟用的修復項目
    enabled = []
    if args.fix_pua:
        enabled.append("PUA/控制字元")
    if args.fix_sc2tc:
        enabled.append("簡繁轉換")
    if args.fix_legal:
        enabled.append("法律用語")
    if args.fix_empty_opts:
        enabled.append("空白選項")
    if args.fix_metadata:
        enabled.append("Metadata補全")
    if args.fix_brackets:
        enabled.append("括號統一化")
    if args.fix_square:
        enabled.append("□符號標記")
    if args.fix_short_stem:
        enabled.append("過短題幹")
    print(f"啟用修復: {', '.join(enabled)}\n")

    # Step 0: 括號統一化（需要在讀取檔案前執行，因為會改目錄名稱）
    rename_map = {}
    if args.fix_brackets:
        print("--- 步驟 0: 括號統一化（目錄重命名）---")
        rename_map = fix_brackets(BASE_DIR, apply=args.apply, report=report)
        if not rename_map:
            print("  沒有需要改名的目錄。")
        print()

    # 重新掃描所有 JSON 檔案（括號改名後路徑可能已變）
    json_files = sorted(
        glob.glob(os.path.join(BASE_DIR, "**", "試題.json"), recursive=True)
    )
    print(f"找到 {len(json_files)} 個試題.json 檔案\n")

    files_modified = 0
    files_backed_up = 0

    for filepath in json_files:
        try:
            data = load_json(filepath)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"[警告] 無法讀取 {filepath}: {e}")
            continue

        original_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
        short_path = filepath.replace(BASE_DIR, "...").replace("\\", "/")

        # 依序套用修復
        if args.fix_pua:
            data = fix_pua(data, short_path, report)

        if args.fix_sc2tc:
            data = fix_sc2tc(data, short_path, report)

        if args.fix_legal:
            data = fix_legal_terms(data, short_path, report)

        if args.fix_empty_opts:
            data = fix_empty_options(data, short_path, report)

        if args.fix_metadata:
            data = fix_metadata(data, short_path, report)

        if args.fix_square:
            data = fix_square_marks(data, short_path, report)

        if args.fix_short_stem:
            data = fix_short_stems(data, short_path, report)

        # 檢查是否有變更
        modified_json = json.dumps(data, ensure_ascii=False, sort_keys=True)
        if original_json != modified_json:
            files_modified += 1
            if args.apply:
                backup_file(filepath)
                files_backed_up += 1
                save_json(filepath, data)
                print(f"  [已修改] {short_path}")
            else:
                print(f"  [待修改] {short_path}")

    # 輸出報告
    print(f"\n--- 檔案統計 ---")
    print(f"  掃描檔案: {len(json_files)}")
    print(f"  需修改檔案: {files_modified}")
    if args.apply:
        print(f"  已備份檔案: {files_backed_up}")
        print(f"  已寫入修改: {files_modified}")
    else:
        print(f"  （DRY-RUN 模式，未實際寫入）")

    report.print_summary()

    if args.verbose:
        report.print_details()

    if not args.apply and files_modified > 0:
        print(f"\n提示：加上 --apply 參數以實際執行修復。")
        print(f"      加上 -v 參數可查看每項修復的詳細內容。")


if __name__ == "__main__":
    main()
