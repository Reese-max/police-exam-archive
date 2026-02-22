#!/usr/bin/env python3
"""
PDF vs JSON 逐題內容比對工具
從考古題庫中抽樣 20 份含選擇題的試卷，
用 pdfplumber 讀 PDF 提取文字，與 JSON 中的 choice 題目做逐題比對。

輸出：reports/pdf_compare_report.txt
"""

import json
import random
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import pdfplumber

BASE_DIR = Path(r"C:\Users\User\Desktop\考古題下載")
EXAM_DB = BASE_DIR / "考古題庫"
REPORT_DIR = BASE_DIR / "reports"

SAMPLE_SIZE = 20
SIMILARITY_THRESHOLD = 0.85


# ============================================================
# 正規化
# ============================================================

def normalize(text: str) -> str:
    """正規化文字：NFKC、去空白、統一全半形標點"""
    t = unicodedata.normalize("NFKC", text)
    # 去除所有空白（空格、換行、tab）
    t = re.sub(r'\s+', '', t)
    # 統一標點
    repls = {
        '，': ',', '。': '.', '；': ';', '：': ':', '？': '?', '！': '!',
        '（': '(', '）': ')', '「': '"', '」': '"', '『': "'", '』': "'",
        '—': '-', '─': '-', '～': '~', '﹣': '-',
    }
    for k, v in repls.items():
        t = t.replace(k, v)
    # 移除底線填空符號
    t = re.sub(r'_+', '', t)
    return t.lower()


def remove_header_footer(text: str) -> str:
    """移除 PDF 頁首頁碼、考卷標頭、代號等"""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        # 跳過考卷標頭
        if re.match(r'^\d{2,3}年(公務|特種)', s):
            continue
        if re.match(r'^代號[:：]', s):
            continue
        if re.match(r'^頁次[:：]', s):
            continue
        if re.match(r'^考試(別|時間|等|類)', s):
            continue
        if re.match(r'^科目[:：]', s):
            continue
        if re.match(r'^座號[:：]', s):
            continue
        if re.match(r'^等\s*別[:：]', s):
            continue
        if re.match(r'^類\s*(科|別)[:：]', s):
            continue
        if re.match(r'^(全一張|全一頁)', s):
            continue
        if re.match(r'^(甲|乙)、', s) and ('測驗' in s or '申論' in s):
            continue
        # 頁碼行
        if re.match(r'^-?\d{1,2}-?$', s):
            continue
        # 五位數代號獨立行
        if re.match(r'^\d{5}$', s):
            continue
        # 移除行末五位數代號
        s = re.sub(r'\s+\d{5}\s*$', '', s)
        s = re.sub(r'^\d{5}\s+', '', s)
        # 移除「請接背面」等
        s = re.sub(r'（請接背面）|（背面尚有試題）|請以背面空白頁書寫.*$', '', s)
        # 注意事項行
        if re.match(r'^※\s*注意', s):
            continue
        if re.match(r'^不必抄題', s):
            continue
        if re.match(r'^請以(藍|黑)', s):
            continue
        if re.match(r'^本試題為', s):
            continue
        if re.match(r'^(共\d+題|本科目)', s):
            continue
        if s.strip():
            cleaned.append(s.strip())
    return "\n".join(cleaned)


# ============================================================
# PDF 提取
# ============================================================

def extract_pdf_text(pdf_path: Path) -> str:
    """用 pdfplumber 提取 PDF 全文"""
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
    raw = "\n".join(parts)
    return remove_header_footer(raw)


# ============================================================
# 抽樣
# ============================================================

def collect_candidates() -> list[dict]:
    """掃描考古題庫，收集所有含選擇題且 PDF+JSON 同時存在的試卷"""
    candidates = []
    for cat_dir in sorted(EXAM_DB.iterdir()):
        if not cat_dir.is_dir():
            continue
        for year_dir in sorted(cat_dir.iterdir()):
            if not year_dir.is_dir():
                continue
            for subj_dir in sorted(year_dir.iterdir()):
                if not subj_dir.is_dir():
                    continue
                json_f = subj_dir / "試題.json"
                pdf_f = subj_dir / "試題.pdf"
                if not (json_f.exists() and pdf_f.exists()):
                    continue
                try:
                    data = json.loads(json_f.read_text(encoding="utf-8"))
                    choice_qs = [q for q in data.get("questions", [])
                                 if q.get("type") == "choice"]
                    if len(choice_qs) >= 1:
                        candidates.append({
                            "cat": cat_dir.name,
                            "year": year_dir.name,
                            "subj": subj_dir.name,
                            "json_path": json_f,
                            "pdf_path": pdf_f,
                            "choice_count": len(choice_qs),
                        })
                except Exception:
                    pass
    return candidates


def stratified_sample(candidates: list[dict], n: int) -> list[dict]:
    """分層抽樣：從不同類科均勻抽取"""
    by_cat = defaultdict(list)
    for c in candidates:
        by_cat[c["cat"]].append(c)

    cats = sorted(by_cat.keys())
    num_cats = len(cats)

    # 每類科至少抽 1 份，剩餘隨機分配
    per_cat = max(1, n // num_cats)
    remainder = n - per_cat * num_cats

    random.seed(42)  # 可重現
    selected = []

    for cat in cats:
        pool = by_cat[cat]
        take = min(per_cat, len(pool))
        selected.extend(random.sample(pool, take))

    # 填補剩餘
    already = {(s["cat"], s["year"], s["subj"]) for s in selected}
    remaining = [c for c in candidates
                 if (c["cat"], c["year"], c["subj"]) not in already]
    if remainder > 0 and remaining:
        selected.extend(random.sample(remaining, min(remainder, len(remaining))))

    # 確保恰好 n 份
    if len(selected) > n:
        selected = selected[:n]

    return selected


# ============================================================
# 逐題比對
# ============================================================

def find_question_in_pdf(pdf_text: str, q_num, next_q_num=None) -> str | None:
    """在 PDF 全文中定位某題的文字段落"""
    # 嘗試多種題號格式
    patterns = [
        rf'(?:^|\n)\s*{q_num}\s*[\.、）\)]\s*',
        rf'(?:^|\n)\s*{q_num}\s+',
        rf'(?:^|\n){q_num}[\.\s]',
    ]

    for pat in patterns:
        m = re.search(pat, pdf_text)
        if m:
            start = m.end()
            # 定位下一題結束
            if next_q_num is not None:
                end_pats = [
                    rf'(?:^|\n)\s*{next_q_num}\s*[\.、）\)]',
                    rf'(?:^|\n)\s*{next_q_num}\s+',
                ]
                for ep in end_pats:
                    em = re.search(ep, pdf_text[start:])
                    if em:
                        return pdf_text[start:start + em.start()].strip()
            # 沒找到下一題，取到文末（最多 3000 字）
            return pdf_text[start:start + 3000].strip()
    return None


def compare_question(pdf_segment: str, json_stem: str) -> dict:
    """比對一道題的 PDF 段落與 JSON stem"""
    n_pdf = normalize(pdf_segment)
    n_json = normalize(json_stem)

    if not n_json or len(n_json) < 3:
        return {"similarity": 1.0, "status": "skip", "detail": "JSON stem 太短"}

    # 計算整體相似度
    # 因為 PDF 段落可能比 JSON stem 長（包含選項），
    # 所以取 JSON 長度的 2 倍範圍做比對
    compare_len = min(len(n_pdf), len(n_json) * 2)
    pdf_window = n_pdf[:compare_len]

    sim = SequenceMatcher(None, pdf_window, n_json, autojunk=False).ratio()

    # 也嘗試在 PDF 中找到最佳匹配位置
    if sim < SIMILARITY_THRESHOLD and len(n_json) >= 10:
        anchor = n_json[:min(15, len(n_json))]
        idx = n_pdf.find(anchor)
        if idx >= 0:
            local_pdf = n_pdf[idx:idx + len(n_json) + 50]
            local_sim = SequenceMatcher(None, local_pdf, n_json, autojunk=False).ratio()
            if local_sim > sim:
                sim = local_sim

    status = "pass" if sim >= SIMILARITY_THRESHOLD else "fail"
    return {"similarity": sim, "status": status}


def compare_one_exam(sample: dict) -> dict:
    """比對一份試卷的所有選擇題"""
    result = {
        "cat": sample["cat"],
        "year": sample["year"],
        "subj": sample["subj"],
        "questions": [],
        "error": None,
    }

    # 讀 JSON
    try:
        data = json.loads(sample["json_path"].read_text(encoding="utf-8"))
    except Exception as e:
        result["error"] = f"JSON 讀取失敗: {e}"
        return result

    choice_qs = [q for q in data.get("questions", []) if q.get("type") == "choice"]
    if not choice_qs:
        result["error"] = "沒有選擇題"
        return result

    # 讀 PDF
    try:
        pdf_text = extract_pdf_text(sample["pdf_path"])
    except Exception as e:
        result["error"] = f"PDF 讀取失敗: {e}"
        return result

    if not pdf_text or len(pdf_text.strip()) < 10:
        result["error"] = "PDF 提取文字為空或太短"
        return result

    # 逐題比對
    for i, q in enumerate(choice_qs):
        q_num = q.get("number", i + 1)
        # 下一題題號
        next_num = None
        if i + 1 < len(choice_qs):
            next_num = choice_qs[i + 1].get("number", None)
        elif isinstance(q_num, int):
            next_num = q_num + 1

        pdf_segment = find_question_in_pdf(pdf_text, q_num, next_num)

        if pdf_segment is None:
            result["questions"].append({
                "number": q_num,
                "similarity": 0.0,
                "status": "not_found",
                "json_stem_preview": q["stem"][:60],
            })
            continue

        cmp = compare_question(pdf_segment, q["stem"])
        cmp["number"] = q_num
        if cmp["similarity"] < SIMILARITY_THRESHOLD:
            cmp["json_stem_preview"] = q["stem"][:80]
            cmp["pdf_segment_preview"] = pdf_segment[:80]
        result["questions"].append(cmp)

    return result


# ============================================================
# 報告
# ============================================================

def generate_report(results: list[dict], samples: list[dict]) -> str:
    """產生文字報告"""
    lines = []
    lines.append("=" * 72)
    lines.append("  PDF vs JSON 逐題內容比對報告")
    lines.append(f"  抽樣數: {len(samples)} 份試卷")
    lines.append(f"  相似度門檻: {SIMILARITY_THRESHOLD}")
    lines.append("=" * 72)
    lines.append("")

    total_questions = 0
    total_pass = 0
    total_fail = 0
    total_not_found = 0
    total_errors = 0
    fail_details = []

    for r in results:
        label = f"{r['cat']}/{r['year']}/{r['subj']}"

        if r["error"]:
            lines.append(f"[ERROR] {label}")
            lines.append(f"  {r['error']}")
            lines.append("")
            total_errors += 1
            continue

        qs = r["questions"]
        q_pass = sum(1 for q in qs if q.get("status") == "pass")
        q_fail = sum(1 for q in qs if q.get("status") == "fail")
        q_nf = sum(1 for q in qs if q.get("status") == "not_found")
        q_skip = sum(1 for q in qs if q.get("status") == "skip")
        avg_sim = 0.0
        sim_vals = [q["similarity"] for q in qs if q.get("status") in ("pass", "fail")]
        if sim_vals:
            avg_sim = sum(sim_vals) / len(sim_vals)

        total_questions += len(qs)
        total_pass += q_pass
        total_fail += q_fail
        total_not_found += q_nf

        status_icon = "PASS" if q_fail == 0 and q_nf == 0 else "WARN"
        lines.append(f"[{status_icon}] {label}")
        lines.append(f"  選擇題: {len(qs)}, 通過: {q_pass}, 失敗: {q_fail}, "
                      f"未定位: {q_nf}, 跳過: {q_skip}, 平均相似度: {avg_sim:.4f}")

        # 列出低相似度的題目
        for q in qs:
            if q.get("status") == "fail":
                lines.append(f"  [低相似度] Q{q['number']}: {q['similarity']:.4f}")
                if "json_stem_preview" in q:
                    lines.append(f"    JSON: {q['json_stem_preview']}")
                if "pdf_segment_preview" in q:
                    lines.append(f"    PDF:  {q['pdf_segment_preview']}")
                fail_details.append({
                    "exam": label,
                    "number": q["number"],
                    "similarity": q["similarity"],
                })
            elif q.get("status") == "not_found":
                lines.append(f"  [未定位] Q{q['number']}: 在 PDF 中找不到對應題目")
                if "json_stem_preview" in q:
                    lines.append(f"    JSON: {q['json_stem_preview']}")
                fail_details.append({
                    "exam": label,
                    "number": q["number"],
                    "similarity": 0.0,
                })

        lines.append("")

    # 摘要
    lines.append("=" * 72)
    lines.append("  摘要")
    lines.append("=" * 72)
    lines.append(f"  試卷數:     {len(results)}")
    lines.append(f"  讀取錯誤:   {total_errors}")
    lines.append(f"  檢查題目:   {total_questions}")
    lines.append(f"  通過:       {total_pass} ({total_pass/max(total_questions,1)*100:.1f}%)")
    lines.append(f"  低相似度:   {total_fail}")
    lines.append(f"  未定位:     {total_not_found}")
    lines.append("")

    if fail_details:
        lines.append("  低相似度題目列表:")
        for fd in fail_details:
            lines.append(f"    {fd['exam']} Q{fd['number']} sim={fd['similarity']:.4f}")
    else:
        lines.append("  所有題目相似度均 >= {:.2f}".format(SIMILARITY_THRESHOLD))

    lines.append("")
    lines.append("=" * 72)

    return "\n".join(lines)


# ============================================================
# 主程式
# ============================================================

def main():
    print("PDF vs JSON 逐題內容比對工具")
    print("=" * 50)

    # 收集候選試卷
    print("掃描考古題庫...")
    candidates = collect_candidates()
    print(f"找到 {len(candidates)} 份含選擇題的試卷")

    # 分層抽樣
    samples = stratified_sample(candidates, SAMPLE_SIZE)
    print(f"抽樣 {len(samples)} 份進行比對")
    print()

    # 顯示抽樣結果
    print("抽樣試卷:")
    for i, s in enumerate(samples, 1):
        print(f"  {i:2d}. {s['cat']}/{s['year']}/{s['subj']} ({s['choice_count']} 題)")
    print()

    # 逐一比對
    results = []
    for i, s in enumerate(samples, 1):
        label = f"{s['cat']}/{s['year']}/{s['subj']}"
        print(f"[{i:2d}/{len(samples)}] 比對: {label} ... ", end="", flush=True)
        r = compare_one_exam(s)
        if r["error"]:
            print(f"ERROR: {r['error']}")
        else:
            qs = r["questions"]
            fails = sum(1 for q in qs if q.get("status") in ("fail", "not_found"))
            if fails > 0:
                print(f"WARN ({fails} 題異常)")
            else:
                print("PASS")
        results.append(r)

    # 產生報告
    print()
    report = generate_report(results, samples)

    # 建立 reports 目錄
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "pdf_compare_report.txt"
    report_path.write_text(report, encoding="utf-8")
    print(f"報告已儲存: {report_path}")

    # 印出摘要
    print()
    print(report)


if __name__ == "__main__":
    main()
