#!/usr/bin/env python3
"""
考古題靜態網站 — 資料完整性驗證腳本
驗證項目：
  1. 題目數量一致性（JSON vs HTML）
  2. 答案格一致性（answer-cell vs 有答案的選擇題）
  3. ID 唯一性
  4. Index 連結有效性
  5. CSS/JS 引用正確性
  6. SUBJECT_KEYS 有效性
"""
import os
import re
import json
import sys
from collections import Counter
from pathlib import Path


def normalize_parens(text):
    """統一全形括號為半形括號（與 generate_html.py 一致）"""
    return str(text).replace('（', '(').replace('）', ')')


# ── 路徑設定 ──
BASE = Path(r"C:\Users\User\Desktop\考古題下載")
JSON_BASE = BASE / "考古題庫"
HTML_BASE = BASE / "考古題網站"

# 15 個類科
CATEGORIES = [
    "交通警察交通組", "交通警察電訊組", "公共安全", "刑事警察",
    "國境警察", "外事警察", "水上警察", "消防警察",
    "犯罪防治矯治組", "犯罪防治預防組", "行政管理", "行政警察",
    "警察法制", "資訊管理", "鑑識科學",
]

# ── 輔助函式 ──
def load_json_questions(category: str) -> tuple:
    """
    載入某類科所有 JSON 試題檔
    回傳: (選擇題數, 申論題數, 有答案選擇題數, 科目集合)
    """
    cat_dir = JSON_BASE / category
    mc_total = 0
    essay_total = 0
    mc_with_answer = 0
    subjects = set()

    for root, _dirs, files in os.walk(cat_dir):
        for fname in files:
            if fname == "試題.json":
                subject_name = normalize_parens(os.path.basename(root))
                subjects.add(subject_name)
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8-sig") as f:
                        data = json.load(f)
                except Exception:
                    continue
                questions = data.get("questions", [])
                for q in questions:
                    qtype = q.get("type", "")
                    if qtype in ("choice", "multiple_choice"):
                        mc_total += 1
                        if q.get("answer"):
                            mc_with_answer += 1
                    elif qtype == "essay":
                        essay_total += 1

    return mc_total, essay_total, mc_with_answer, subjects


def load_html(category: str) -> dict | None:
    """
    解析某類科 HTML 檔，回傳各種計數與結構資料
    """
    html_path = HTML_BASE / category / f"{category}考古題總覽.html"
    if not html_path.exists():
        return None

    with open(html_path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    mc_count = len(re.findall(r'class="mc-question[\s"]', content))
    passage_count = len(re.findall(r'data-subtype="passage_fragment"', content))
    essay_count = len(re.findall(r'class="essay-question"', content))
    answer_cell_count = len(re.findall(r'class="answer-cell[\s"]', content))

    # ID 唯一性
    all_ids = re.findall(r' id="([^"]+)"', content)
    id_counter = Counter(all_ids)
    dup_ids = {k: v for k, v in id_counter.items() if v > 1}

    # CSS/JS 引用
    has_css = '../css/style.css' in content
    has_js = '../js/app.js' in content

    # SUBJECT_KEYS
    sk_match = re.search(r'(?:var|const|let)\s+SUBJECT_KEYS\s*=\s*(\[.*?\])\s*;', content, re.DOTALL)
    subject_keys = None
    subject_keys_valid = False
    if sk_match:
        try:
            subject_keys = json.loads(sk_match.group(1))
            subject_keys_valid = isinstance(subject_keys, list) and len(subject_keys) > 0
        except json.JSONDecodeError:
            subject_keys_valid = False

    return {
        "mc": mc_count,
        "passage": passage_count,
        "essay": essay_count,
        "answer_cells": answer_cell_count,
        "all_ids": all_ids,
        "dup_ids": dup_ids,
        "has_css": has_css,
        "has_js": has_js,
        "subject_keys": subject_keys,
        "subject_keys_valid": subject_keys_valid,
        "raw": content,
    }


# ══════════════════════════════════════════════════════════
#  主要驗證
# ══════════════════════════════════════════════════════════
def main():
    print("=" * 72)
    print("  考古題靜態網站 — 資料完整性驗證報告")
    print("=" * 72)

    total_pass = 0
    total_fail = 0

    # 預先載入所有資料
    json_cache = {}
    html_cache = {}
    for cat in CATEGORIES:
        json_cache[cat] = load_json_questions(cat)
        html_cache[cat] = load_html(cat)

    # ────────────────────────────────────────────────────────
    # 驗證 1: 題目數量一致性
    # ────────────────────────────────────────────────────────
    print("\n" + "-" * 72)
    print("【驗證 1】題目數量一致性（JSON vs HTML）")
    print("-" * 72)

    v1_pass = True
    grand_json = 0
    grand_html = 0

    for cat in CATEGORIES:
        mc_j, essay_j, _, _ = json_cache[cat]
        json_total = mc_j + essay_j
        grand_json += json_total

        hd = html_cache[cat]
        if hd is None:
            print(f"  [FAIL] {cat}: HTML 檔案不存在")
            v1_pass = False
            continue

        html_total = hd["mc"] + hd["essay"]
        grand_html += html_total

        ok = (json_total == html_total)
        if not ok:
            v1_pass = False
        tag = "PASS" if ok else "FAIL"

        mc_note = "OK" if mc_j == hd["mc"] else f"MISMATCH(JSON={mc_j},HTML={hd['mc']})"
        es_note = "OK" if essay_j == hd["essay"] else f"MISMATCH(JSON={essay_j},HTML={hd['essay']})"
        print(f"  [{tag}] {cat}: JSON={json_total} HTML={html_total}  "
              f"(選擇={mc_note}, 申論={es_note})")

    print(f"\n  合計: JSON={grand_json} / HTML={grand_html}")
    if v1_pass:
        print("  >>> 驗證 1: PASS")
        total_pass += 1
    else:
        print("  >>> 驗證 1: FAIL")
        total_fail += 1

    # ────────────────────────────────────────────────────────
    # 驗證 2: 答案格一致性
    # ────────────────────────────────────────────────────────
    print("\n" + "-" * 72)
    print("【驗證 2】答案格一致性（answer-cell = 選擇題 - 段落題）")
    print("-" * 72)

    v2_pass = True
    for cat in CATEGORIES:
        mc_j, _, mc_ans_j, _ = json_cache[cat]
        hd = html_cache[cat]
        if hd is None:
            print(f"  [FAIL] {cat}: HTML 不存在")
            v2_pass = False
            continue

        ac = hd["answer_cells"]
        mc_html = hd["mc"]
        pf = hd["passage"]
        expected = mc_html - pf
        ok = (ac == expected)
        if not ok:
            v2_pass = False
        tag = "PASS" if ok else "FAIL"
        print(f"  [{tag}] {cat}: answer-cell={ac}  選擇題={mc_html}  "
              f"段落題={pf}  預期={expected}")

    if v2_pass:
        print("  >>> 驗證 2: PASS")
        total_pass += 1
    else:
        print("  >>> 驗證 2: FAIL")
        total_fail += 1

    # ────────────────────────────────────────────────────────
    # 驗證 3: ID 唯一性
    # ────────────────────────────────────────────────────────
    print("\n" + "-" * 72)
    print("【驗證 3】ID 唯一性（所有 16 個 HTML）")
    print("-" * 72)

    v3_pass = True
    total_ids = 0
    total_dups = 0

    for cat in CATEGORIES:
        hd = html_cache[cat]
        if hd is None:
            print(f"  [FAIL] {cat}: HTML 不存在")
            v3_pass = False
            continue

        n_ids = len(hd["all_ids"])
        n_dups = len(hd["dup_ids"])
        total_ids += n_ids
        total_dups += n_dups

        tag = "PASS" if n_dups == 0 else "FAIL"
        if n_dups > 0:
            v3_pass = False
            samples = list(hd["dup_ids"].items())[:3]
            s = ", ".join(f'"{k}"x{v}' for k, v in samples)
            print(f"  [{tag}] {cat}: {n_ids} IDs, {n_dups} 重複 ({s})")
        else:
            print(f"  [{tag}] {cat}: {n_ids} IDs, 0 重複")

    # index.html
    idx_path = HTML_BASE / "index.html"
    if idx_path.exists():
        with open(idx_path, "r", encoding="utf-8-sig") as f:
            idx_content = f.read()
        idx_ids = re.findall(r' id="([^"]+)"', idx_content)
        idx_dups = {k: v for k, v in Counter(idx_ids).items() if v > 1}
        n_d = len(idx_dups)
        tag = "PASS" if n_d == 0 else "FAIL"
        if n_d > 0:
            v3_pass = False
        print(f"  [{tag}] index.html: {len(idx_ids)} IDs, {n_d} 重複")
        total_ids += len(idx_ids)
        total_dups += n_d

    print(f"\n  合計: 掃描 {total_ids} 個 ID, {total_dups} 個重複")
    if v3_pass:
        print("  >>> 驗證 3: PASS")
        total_pass += 1
    else:
        print("  >>> 驗證 3: FAIL")
        total_fail += 1

    # ────────────────────────────────────────────────────────
    # 驗證 4: Index 連結有效性
    # ────────────────────────────────────────────────────────
    print("\n" + "-" * 72)
    print("【驗證 4】Index 連結有效性（15 個連結 -> 存在的檔案）")
    print("-" * 72)

    v4_pass = True
    if not idx_path.exists():
        print("  [FAIL] index.html 不存在")
        v4_pass = False
    else:
        links = re.findall(r'href="([^"]*考古題總覽\.html)"', idx_content)
        print(f"  找到 {len(links)} 個類科連結（預期 15）")
        if len(links) != 15:
            v4_pass = False
            print(f"  [FAIL] 連結數量 {len(links)} != 15")

        for lk in links:
            target = HTML_BASE / lk
            ok = target.exists()
            tag = "PASS" if ok else "FAIL"
            if not ok:
                v4_pass = False
            print(f"  [{tag}] {lk}")

    if v4_pass:
        print("  >>> 驗證 4: PASS")
        total_pass += 1
    else:
        print("  >>> 驗證 4: FAIL")
        total_fail += 1

    # ────────────────────────────────────────────────────────
    # 驗證 5: CSS/JS 引用正確性
    # ────────────────────────────────────────────────────────
    print("\n" + "-" * 72)
    print("【驗證 5】CSS/JS 引用正確性")
    print("-" * 72)

    v5_pass = True
    css_exists = (HTML_BASE / "css" / "style.css").exists()
    js_exists = (HTML_BASE / "js" / "app.js").exists()
    print(f"  實體檔案: css/style.css={'存在' if css_exists else '不存在'}  "
          f"js/app.js={'存在' if js_exists else '不存在'}")
    if not css_exists or not js_exists:
        v5_pass = False

    for cat in CATEGORIES:
        hd = html_cache[cat]
        if hd is None:
            print(f"  [FAIL] {cat}: HTML 不存在")
            v5_pass = False
            continue

        ok = hd["has_css"] and hd["has_js"]
        tag = "PASS" if ok else "FAIL"
        if not ok:
            v5_pass = False
            issues = []
            if not hd["has_css"]:
                issues.append("缺少 ../css/style.css")
            if not hd["has_js"]:
                issues.append("缺少 ../js/app.js")
            print(f"  [{tag}] {cat}  ({', '.join(issues)})")
        else:
            print(f"  [{tag}] {cat}")

    if v5_pass:
        print("  >>> 驗證 5: PASS")
        total_pass += 1
    else:
        print("  >>> 驗證 5: FAIL")
        total_fail += 1

    # ────────────────────────────────────────────────────────
    # 驗證 6: SUBJECT_KEYS 有效性
    # ────────────────────────────────────────────────────────
    print("\n" + "-" * 72)
    print("【驗證 6】SUBJECT_KEYS 有效性（有效 JSON + 涵蓋所有科目）")
    print("-" * 72)

    v6_pass = True
    for cat in CATEGORIES:
        _, _, _, json_subjects = json_cache[cat]
        hd = html_cache[cat]
        if hd is None:
            print(f"  [FAIL] {cat}: HTML 不存在")
            v6_pass = False
            continue

        if not hd["subject_keys_valid"]:
            print(f"  [FAIL] {cat}: SUBJECT_KEYS 無效或不存在")
            v6_pass = False
            continue

        sk_set = set(hd["subject_keys"])
        missing = json_subjects - sk_set
        extra = sk_set - json_subjects

        if missing:
            print(f"  [FAIL] {cat}: SUBJECT_KEYS 缺少 {len(missing)} 個科目")
            for m in sorted(missing):
                print(f"         - {m}")
            v6_pass = False
        else:
            note = ""
            if extra:
                note = f"  (另有 {len(extra)} 個額外項，可能為全半形括號變體)"
            print(f"  [PASS] {cat}: JSON={len(json_subjects)} 科目, "
                  f"SUBJECT_KEYS={len(sk_set)} 項{note}")

    if v6_pass:
        print("  >>> 驗證 6: PASS")
        total_pass += 1
    else:
        print("  >>> 驗證 6: FAIL")
        total_fail += 1

    # ── 總結 ──
    print("\n" + "=" * 72)
    all_ok = total_fail == 0
    status = "ALL PASS" if all_ok else f"{total_fail} FAIL"
    print(f"  驗證總結: {total_pass} PASS / {total_fail} FAIL  (共 6 項)  [{status}]")
    print("=" * 72)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
