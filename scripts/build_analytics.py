#!/usr/bin/env python3
"""從考古題庫 JSON 生成出題趨勢統計。

產出 analytics.json 供前端 Dashboard 使用。

用法:
    python scripts/build_analytics.py
    python scripts/build_analytics.py --output 考古題網站/data/analytics.json
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = ROOT / "考古題庫"
DEFAULT_OUTPUT = ROOT / "考古題網站" / "data" / "analytics.json"


def load_all_questions(data_dir: Path) -> list[dict]:
    """載入所有題目（扁平化）。"""
    files = sorted(glob.glob(str(data_dir / "**" / "試題.json"), recursive=True))
    questions = []

    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                d = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        if d.get("metadata", {}).get("_is_duplicate"):
            continue

        category = d.get("category", "")
        year = d.get("year")
        subject = d.get("subject", "")

        if not category or not year or not subject:
            rel = os.path.relpath(fp, str(data_dir))
            parts = rel.replace(os.sep, "/").split("/")
            if not category:
                category = parts[0] if len(parts) > 0 else ""
            if not year:
                year_str = parts[1].replace("年", "") if len(parts) > 1 else ""
                year = int(year_str) if year_str.isdigit() else None
            if not subject:
                subject = parts[2] if len(parts) > 2 else ""

        for q in d.get("questions", []):
            questions.append({
                "cat": category,
                "yr": year,
                "sub": subject,
                "type": q.get("type", ""),
                "stem": q.get("stem", ""),
                "ans": q.get("answer", "") if q.get("type") == "choice" else "",
            })

    return questions


def build_analytics(questions: list[dict]) -> dict:
    """計算統計資料。"""
    years = sorted({q["yr"] for q in questions if q["yr"]})
    categories = sorted({q["cat"] for q in questions if q["cat"]})
    subjects = sorted({q["sub"] for q in questions if q["sub"]})

    # 1. 各類科各年份出題數
    cat_year = defaultdict(lambda: defaultdict(int))
    sub_year = defaultdict(lambda: defaultdict(int))
    for q in questions:
        if q["yr"] and q["cat"]:
            cat_year[q["cat"]][str(q["yr"])] += 1
        if q["yr"] and q["sub"]:
            sub_year[q["sub"]][str(q["yr"])] += 1

    # 2. 答案分佈（僅選擇題）
    answer_dist = Counter()
    answer_by_year = defaultdict(Counter)
    for q in questions:
        if q["type"] != "choice" or not q["ans"]:
            continue

        answer = q["ans"]
        if isinstance(answer, list):
            # Preserve all accepted options as one stable analytics bucket,
            # consistent with the repository's existing ``A或C`` convention.
            values = [
                str(value).strip()
                for value in answer
                if str(value).strip()
            ]
            answer = "或".join(dict.fromkeys(values))
        elif not isinstance(answer, str):
            answer = str(answer).strip()

        if not answer:
            continue
        answer_dist[answer] += 1
        if q["yr"]:
            answer_by_year[str(q["yr"])][answer] += 1

    # 3. 各類科題目數
    cat_total = Counter(q["cat"] for q in questions if q["cat"])

    # 4. 各科目題目數
    sub_total = Counter(q["sub"] for q in questions if q["sub"])

    # 5. 年份總題數
    year_total = Counter(str(q["yr"]) for q in questions if q["yr"])

    # 6. 關鍵字頻率（領域詞提取）
    # 領域詞庫：法律、警察、犯罪、行政相關專業詞彙
    domain_patterns = [
        # 法律制度
        r'憲法[第增修]*[條項號]*\d*[號解]*',
        r'刑法[第第]*\d*[條項]',
        r'行政[法罰程序訴訟]*[法第第]*\d*[條項]',
        r'民法[第第]*\d*[條項]',
        r'[刑事民事行政]*訴訟法',
        r'社會秩序維護法',
        r'槍砲彈藥刀械管制條例',
        r'毒品危害防制條例',
        r'組織犯罪防制條例',
        r'洗錢防制法',
        r'個人資料保護法',
        r'國家賠償法',
        r'行政執行法',
        r'集會遊行法',
        r'警械使用條例',
        r'警察職權行使法',
        r'公務人員行政中立法',
        r'道路交通管理處罰條例',
        r'入出國及移民法',
        r'災害防救法',
        r'消防法',
        r'兒童及少年福利與權益保障法',
        r'家庭暴力防治法',
        r'性騷擾防治法',
        r'選舉罷免法',
        r'政府資訊公開法',
        r'行政程序法',
        r'訴願法',
        r'地方制度法',
        r'公務員懲戒法',
        r'刑事妥速審判法',
        r'通訊保障及監察法',
        r'證人保護法',
        r'羈押法',
        r'監獄行刑法',
        r'少年事件處理法',
        r'保安處分執行法',
        # 警察專業
        r'警察[法勤務組織教育訓練考核獎懲倫理文化制度]',
        r'警勤區',
        r'派出所',
        r'分局',
        r'警政署',
        r'刑事警察局',
        r'保安警察',
        r'鐵路警察',
        r'航空警察',
        r'港務警察',
        r'國境警察',
        r'移民署',
        r'外事警察',
        r'水上警察',
        r'交通警察',
        r'鑑識科學',
        r'犯罪防治',
        r'資訊管理',
        r'行政管理',
        # 犯罪偵查
        r'偵查[作為程序方法技巧]',
        r'搜索[扣押票令]',
        r'拘提[票令]',
        r'逮捕[權現行犯緊急]',
        r'訊問[筆錄程序]',
        r'詢問[筆錄程序]',
        r'監聽[票令通訊監察]',
        r'跟蹤[監視]',
        r'埋伏[守候]',
        r'臨檢[盤查身分]',
        r'刑案現場[勘查採證]',
        r'刑事鑑識',
        r'法醫學',
        r'DNA[鑑定比對]',
        r'指紋[鑑定比對採集]',
        r'槍枝[鑑定彈道]',
        r'毒品[鑑定查緝]',
        r'詐欺[集團犯罪手法]',
        r'組織犯罪',
        r'幫派[犯罪組織]',
        r'電信詐騙',
        r'網路犯罪',
        r'洗錢[防制犯罪]',
        # 行政法學
        r'行政裁量',
        r'比例原則',
        r'平等原則',
        r'信賴保護',
        r'法律保留',
        r'依法行政',
        r'正當法律程序',
        r'行政處分',
        r'行政契約',
        r'行政罰[法則處罰]',
        r'行政執行',
        r'行政訴訟',
        r'行政救濟',
        r'國家賠償',
        r'公務員[責任保障懲戒]',
        # 刑法學
        r'犯罪[構成要件論體系]',
        r'故意[直接未必]',
        r'過失[有認識無認識]',
        r'未遂[犯障礙中止]',
        r'共犯[正犯教唆幫助]',
        r'競合[想像法條]',
        r'刑罰[種類量處]',
        r'緩刑[宣告條件]',
        r'假釋[條件撤銷]',
        r'追訴權[時效]',
        r'沒收[犯罪所得]',
        r'正當防衛',
        r'緊急避難',
        r'依法令[之行為]',
        # 憲法學
        r'基本權利',
        r'人身自由',
        r'居住遷徙自由',
        r'言論自由',
        r'宗教自由',
        r'集會結社自由',
        r'生存權',
        r'工作權',
        r'財產權',
        r'訴訟權',
        r'參政權',
        r'應考試權',
        r'國民主權',
        r'權力分立',
        r'地方自治',
        r'司法院大法官',
        r'憲法法庭',
        r'憲法解釋',
        r'違憲審查',
        # 犯罪學
        r'犯罪預防',
        r'犯罪轉移',
        r'犯罪學[理論]',
        r'情境犯罪預防',
        r'社區犯罪預防',
        r'環境設計',
        r'破窗理論',
        r'理性選擇理論',
        r'日常活動理論',
        r'社會解組理論',
        r'差別接觸理論',
        r'標籤理論',
        # 警察勤務
        r'巡邏[勤務]',
        r'臨檢[勤務]',
        r'守望[勤務]',
        r'值班[勤務]',
        r'備勤[勤務]',
        r'勤區查察',
        r'家戶訪查',
        r'為民服務',
        r'治安調查',
        r'交通指揮',
        r'取締違規',
        r'事故處理',
        r'救護[災害搶救]',
        # 移民/國境
        r'入出國[管理]',
        r'移民[業務署]',
        r'國境[安全檢查]',
        r'外國人[管理居留]',
        r'難民[認定庇護]',
        r'人口販運',
        r'跨國[犯罪境]',
    ]
    # 合併成一個大正則
    domain_re = re.compile('|'.join(domain_patterns))

    word_counter = Counter()
    for q in questions:
        stem = q.get("stem", "")
        matches = domain_re.findall(stem)
        for m in matches:
            if len(m) >= 2:
                word_counter[m] += 1

    # 也提取常見 2-3 字法律/警察詞
    common_legal = re.compile(
        r'(?:犯罪|刑法|刑罰|徒刑|拘役|罰金|沒收|緩刑|假釋|未遂|共犯|正犯|教唆|幫助|'
        r'故意|過失|正當防衛|緊急避難|競合|連續犯|牽連犯|想像競合|數罪併罰|'
        r'警察|勤務|偵查|搜索|扣押|拘提|逮捕|訊問|詢問|監聽|跟蹤|盤查|臨檢|'
        r'行政處分|行政訴願|行政訴訟|行政罰|行政執行|國家賠償|'
        r'基本權利|人身自由|言論自由|居住自由|財產權|訴訟權|參政權|'
        r'詐欺|竊盜|強盜|搶奪|恐嚇|擄人勒贖|殺人|傷害|妨害自由|'
        r'毒品|槍枝|洗錢|組織犯罪|幫派|電信詐騙|人口販運|'
        r'交通安全|酒駕|超速|違規停車|交通事故|'
        r'消防|災害|救護|避難|疏散|'
        r'鑑識|指紋|DNA|彈道|法醫|'
        r'移民|入出國|國境|外事|難民)'
    )
    for q in questions:
        stem = q.get("stem", "")
        matches = common_legal.findall(stem)
        for m in matches:
            if len(m) >= 2:
                word_counter[m] += 1

    # 過濾：移除出現次數太低的
    filtered = [(w, c) for w, c in word_counter.items() if c >= 20]
    filtered.sort(key=lambda x: -x[1])
    top_words = [{"word": w, "count": c} for w, c in filtered[:100]]

    return {
        "version": 1,
        "stats": {
            "total": len(questions),
            "choice": sum(1 for q in questions if q["type"] == "choice"),
            "essay": sum(1 for q in questions if q["type"] == "essay"),
            "categories": len(categories),
            "subjects": len(subjects),
            "years": years,
        },
        "by_category": {cat: dict(sorted(ys.items())) for cat, ys in sorted(cat_year.items())},
        "by_subject": {sub: dict(sorted(ys.items())) for sub, ys in sorted(sub_year.items())},
        "answer_distribution": dict(answer_dist),
        "answer_by_year": {yr: dict(sorted(ans.items())) for yr, ans in sorted(answer_by_year.items())},
        "category_totals": {cat: cnt for cat, cnt in cat_total.most_common()},
        "subject_totals": {sub: cnt for sub, cnt in sub_total.most_common()},
        "year_totals": {yr: year_total[yr] for yr in sorted(year_total.keys())},
        "top_keywords": top_words,
    }


def main():
    parser = argparse.ArgumentParser(description="生成出題趨勢統計")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--output", "-o", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"資料目錄不存在: {data_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"正在掃描 {data_dir} ...")
    questions = load_all_questions(data_dir)
    print(f"  載入 {len(questions)} 題")

    analytics = build_analytics(questions)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(analytics, f, ensure_ascii=False, indent=2)

    size_kb = output.stat().st_size / 1024
    print(f"\n已產出: {output} ({size_kb:.0f} KB)")
    print(f"  類科: {analytics['stats']['categories']}")
    print(f"  科目: {analytics['stats']['subjects']}")
    print(f"  年份: {analytics['stats']['years'][0]} ~ {analytics['stats']['years'][-1]}")
    print(f"  Top 關鍵字: {', '.join(w['word'] for w in analytics['top_keywords'][:10])}")


if __name__ == "__main__":
    main()
