# eval_holdout.jsonl — 保留評估集說明

**此集不得用於調參；只在發版前跑一次。**
`rag/eval_semantic.jsonl` 已被用來調檢索參數，分數偏樂觀；本集為另行出題的保留集（holdout），
任何參數（keyword_weight、reranker、擴充縮寫等）不得以本集結果挑選或微調，僅在發版前跑一次作為未偏估計。

## 抽樣方法

- 母體：`rag/corpus.jsonl` 中 `type == "choice"` 的題目，共 8,164 題。
- 排除：`rag/eval_semantic.jsonl` 的 `relevant_question_ids` 出現過的 147 個 question_id，剩 8,079 題。
- 方法：`random.Random(20251110)`（**seed = 20251110**）將各年度候選洗牌後，
  依年度 round-robin 抽 10 題；每年內挑選目前「(科目, 學系) 已用次數最少」的題目，
  使科目與學系分散。共抽 100 題；主對話驗收時刪除 4 筆無法辨識目標的籠統查詢（如「英文克漏字26到30題怎麼填」），現存 96 筆。
- 英文題占比 26/100，與母體自然占比 23.6%（1,907/8,079）接近。

## 分布（以每題 appears_in 第一筆計）

- **年度**：106–115 每年各 10 題。
- **科目**：36 個科目。最多者為國文(作文與測驗) 5 題，其餘每科 1–4 題
  （綜合法政、消防情境、行政法、移民法規、水上情境、國境執法、國土安全、外國文各語別等）。
- **學系**：18 個學系/組別。國境警察學系移民組 26、公共安全學系情報組 16、消防學系 11、
  水上警察 9、交通學系交通組 8、行政警察 6，其餘 1–4
  （移民組與情報組偏多係因其為母體最大且題目多為該系獨考，與母體組成一致）。

## 標註規則

- 每題 1 個自然語言查詢，以「考生會怎麼問」的口吻撰寫：換句話說、口語或問概念，
  不複製題幹／選項連續 4 字以上（與 `check_eval_set.py` 的 `shared_four` 規則相同，
  NFKC 正規化、去空白標點後比對）。
- 17/100（17%）查詢使用 `rag/abbreviations.json` 中的簡稱寫法
  （如 刑訴、行執法、行程法、警職法、社維法、集遊法、貪污條例、災防法），
  部分另用口語／簡略寫法（如 老外、幹嘛）。
- `relevant_question_ids` 第一個為抽中的題目；若語料中另有
  **題幹＋全部選項正規化後完全相同**的同題（跨年度/學系重複出現的同一題），
  亦列入 gold（多標籤，共 17 列），rationale 中註明「同題跨卷重複，併列gold」。
  僅共用「請依下文回答」類說明題幹但選項不同者不併列。
- `rationale` 簡述考點或入選依據，欄位與 `eval_semantic.jsonl` 相容，
  另加 `"split": "holdout"`、`"author": "SWE-2 Max"`。

## 檢查

```bash
python scripts/rag/check_eval_set.py --eval-set rag/eval_holdout.jsonl \
    --min-queries 96 --require-types choice
```

（本集 96 題且全為選擇題，`--min-queries` 與 `--require-types` 為本集新增的參數；
預設行為不變，eval_semantic 仍以 150 題、choice+essay 檢查。）
