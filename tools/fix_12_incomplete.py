#!/usr/bin/env python3
"""
手動修復 12 道剩餘 incomplete 考古題。
選項內容從 PDF 原始檔案目視提取。
"""
import json
import os
import glob

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ─── 修復定義 ───────────────────────────────────────
FIXES = [
    # ====== COMBO 題：在現有 stem 尾部追加選項 ======
    {
        "file": "考古題庫/刑事警察/107年/刑案現場處理與刑事鑑識/試題.json",
        "qnum": 7,
        "mode": "append",
        "options": " (A)345 (B)234 (C)235 (D)1234",
        "desc": "刑案Q7 毛髮跡證 COMBO 5項",
    },
    {
        "file": "考古題庫/刑事警察/107年/刑案現場處理與刑事鑑識/試題.json",
        "qnum": 21,
        "mode": "append",
        "options": " (A)23 (B)35 (C)235 (D)1234",
        "desc": "刑案Q21 纖維物證 COMBO 5項",
    },
    {
        "file": "考古題庫/刑事警察/107年/犯罪偵查學/試題.json",
        "qnum": 10,
        "mode": "append",
        "options": " (A)134 (B)124 (C)45 (D)14",
        "desc": "犯偵Q10 辯護人選任 COMBO 5項",
    },
    {
        "file": "考古題庫/行政警察/107年/偵查法學與犯罪偵查/試題.json",
        "qnum": 14,
        "mode": "append",
        "options": " (A)25 (B)13 (C)56 (D)34",
        "desc": "行政Q14 暫時性物證 COMBO 6項",
    },
    {
        "file": "考古題庫/行政警察/107年/偵查法學與犯罪偵查/試題.json",
        "qnum": 18,
        "mode": "append",
        "options": " (A)14 (B)25 (C)36 (D)24",
        "desc": "行政Q18 重大刑案 COMBO 6項",
    },
    # ====== INLINE / 截斷題：替換 stem 中選項部分 ======
    {
        "file": "考古題庫/消防警察/107年/消防與災害防救法規(包括消防法及施行細則、災害防救法及施行細則、爆竹煙火管理條例及施行細則、公共危險物品及可燃性高壓氣體設置標準暨安全管理辦法、緊急救護辦法、緊/試題.json",
        "qnum": 17,
        "mode": "replace",
        "stem": "依緊急救護辦法之規定,緊急傷病患非指下列何者情形: (A)醫療機構之緊急醫療 (B)因災害或意外事故急待救護者 (C)路倒傷病無法行動者 (D)孕婦待產者",
        "desc": "消防Q17 緊急傷病患 INLINE",
    },
    {
        "file": "考古題庫/行政警察/107年/偵查法學與犯罪偵查/試題.json",
        "qnum": 15,
        "mode": "replace",
        "stem": "刑案現場有各種蒐證方式,偵查人員發現現場有一大滴血,隨即尋找該受傷之人。此方法之運用屬於何種蒐證法? (A)線條式 (B)放射式 (C)聯鎖式 (D)螺旋式",
        "desc": "行政Q15 蒐證法 截斷→完整",
    },
    {
        "file": "考古題庫/行政警察/107年/偵查法學與犯罪偵查/試題.json",
        "qnum": 16,
        "mode": "replace",
        "stem": "有關「證物處理」之敘述,下列何者正確? (A)犯罪現場測繪的順序是先記錄主要跡證的相關位置,其次是現場全面景象,最後是測繪所在位置 (B)犯罪現場搜查的原則是由外而內、由明顯至潛伏、由高而低以及由近而遠 (C)偵查人員在犯罪現場進行勘察時,為了爭取時效應盡量直接進入現場中心進行採證 (D)採證人員以金屬鑷子夾取金屬性證物,屬不當的證物採集方法",
        "desc": "行政Q16 證物處理 截斷→完整",
    },
    {
        "file": "考古題庫/行政警察/107年/偵查法學與犯罪偵查/試題.json",
        "qnum": 17,
        "mode": "replace",
        "stem": "警察偵查犯罪手冊有關「犯罪案件管轄責任區分」之規定,下列敘述何者正確? (A)涉及外籍人士金融帳戶之詐欺案件,以被害人最後一次匯款地之警察機關主辦 (B)單一犯罪行為案件之行為地與結果地非同一處所,管轄責任機關有二以上者,由結果發生地之警察機關負責偵辦 (C)未涉及帳戶匯款之網路詐欺案件,以網路犯罪被害人現住所或戶籍所在地之警察機關為管轄機關 (D)案件涉及境外犯罪,管轄之警察機關依序為被害人之工作地、居住地、家屬居住地之警察機關",
        "desc": "行政Q17 犯罪案件管轄 截斷→完整",
    },
    {
        "file": "考古題庫/行政警察/107年/偵查法學與犯罪偵查/試題.json",
        "qnum": 19,
        "mode": "replace",
        "stem": "有關「犯罪剖繪」(criminal profiling)之敘述,下列何者正確? (A)犯罪剖繪對所有的刑事案件都能發揮極大的偵防功效 (B)一般傷害案件屬適合犯罪剖繪的犯罪型態之一 (C)作案手法是犯罪者的習慣、技巧及行為特性的總稱 (D)犯罪剖繪主要應用在偵查階段,因為此技術能提供犯罪者的確切身分",
        "desc": "行政Q19 犯罪剖繪 截斷→完整",
    },
    {
        "file": "考古題庫/行政警察/107年/偵查法學與犯罪偵查/試題.json",
        "qnum": 20,
        "mode": "replace",
        "stem": "指紋鑑識作業手冊的目的是確保刑案現場指紋勘察之採證品質,並作為犯罪偵查之證據。關於指紋採取與採驗之敘述,下列何者正確? (A)捺印指紋應有次序,先左手,後右手,由小指至拇指 (B)十指紋卡填寫各欄位資料,應於捺印指紋後為之 (C)在刑案現場發現手指接觸未乾油漆面所遺留之立體狀指紋,稱為「成型紋」 (D)在刑案現場發現腳印時,應先就單獨紋線拍照,再以相機對腳印及其周邊全景拍照",
        "desc": "行政Q20 指紋採取 截斷→完整",
    },
    {
        "file": "考古題庫/鑑識科學/106年/犯罪偵查/試題.json",
        "qnum": 19,
        "mode": "replace",
        "stem": "在犯罪偵查過程中所獲得的涉案情資,可以視為犯罪物件,每一個犯罪物件具有時間與地點兩種資訊。由兩毒品犯罪者的移動軌跡中,在進行毒品交易時,其犯罪物件的時間分別為t1與t2,犯罪物件的地點分別為x1與x2,下列何者正確? (A)t1=t2且x1=x2 (B)t1≠t2且x1=x2 (C)t1=t2且x1≠x2 (D)t1≠t2且x1≠x2",
        "desc": "鑑識Q19 犯罪物件時空 截斷→完整",
    },
]


def main():
    print("=" * 60)
    print("  手動修復 12 道 incomplete 考古題")
    print("=" * 60)

    fixed = 0
    errors = 0

    # Group fixes by file to minimize I/O
    by_file = {}
    for fix in FIXES:
        fp = os.path.join(BASE, fix["file"])
        by_file.setdefault(fp, []).append(fix)

    for fp, fixes in by_file.items():
        if not os.path.exists(fp):
            print(f"  [ERROR] 找不到: {fp}")
            errors += len(fixes)
            continue

        data = json.load(open(fp, encoding="utf-8"))
        modified = False

        for fix in fixes:
            qnum = fix["qnum"]
            # Find the question
            q = None
            for candidate in data["questions"]:
                if candidate.get("number") == qnum:
                    q = candidate
                    break

            if q is None:
                print(f"  [ERROR] 找不到 Q{qnum} in {os.path.basename(fp)}")
                errors += 1
                continue

            old_stem = q["stem"]

            if fix["mode"] == "append":
                new_stem = old_stem.rstrip() + fix["options"]
            elif fix["mode"] == "replace":
                new_stem = fix["stem"]
            else:
                print(f"  [ERROR] 未知 mode: {fix['mode']}")
                errors += 1
                continue

            # 驗證: 新 stem 必須包含 (A) (B) (C) (D)
            for label in ["(A)", "(B)", "(C)", "(D)"]:
                if label not in new_stem:
                    print(f"  [ERROR] Q{qnum} 新 stem 缺少 {label}")
                    errors += 1
                    continue

            q["stem"] = new_stem

            # 移除 incomplete 標記
            if "subtype" in q:
                del q["subtype"]

            modified = True
            fixed += 1
            print(f"  [OK] {fix['desc']}")

        if modified:
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    print()
    print(f"  修復: {fixed} / {len(FIXES)}")
    if errors:
        print(f"  錯誤: {errors}")

    # 驗證：掃描所有 incomplete
    print()
    print("  驗證剩餘 incomplete...")
    inc = 0
    for f in glob.glob(os.path.join(BASE, "考古題庫/**/試題.json"), recursive=True):
        d = json.load(open(f, encoding="utf-8"))
        for q in d["questions"]:
            if q.get("subtype") == "incomplete":
                inc += 1
                print(f"    - {os.path.relpath(f, BASE)} Q{q['number']}")
    print(f"  剩餘 incomplete: {inc}")
    print("=" * 60)


if __name__ == "__main__":
    main()
