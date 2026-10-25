# 警察特考考古題資料庫

台灣警察人員特種考試（三等、四等）考古題結構化 JSON 資料庫，涵蓋 106-115 年（2017-2026）各學系/類別的所有科目。

## 資料規模

<!-- corpus-stats:begin 由 scripts/check_corpus_claims.py 驗證，請勿手改 -->
| 項目 | 數量 |
|------|------|
| 學系/類別 | 49 個 |
| 年份 | 106-115 年（10 年） |
| 科目 | 101 個 |
| JSON 檔案 | 2,049 個（非重複） |
| 重複副本 | 41 份（共 1,217 題，不計入題數） |
| 選擇題 | 36,760 題 |
| 申論題 | 5,758 題 |
| 總題數 | 42,518 題 |
<!-- corpus-stats:end -->

## 目錄結構

```
├── 考古題庫/                    # 資料主體
│   ├── 行政警察/
│   │   ├── 106年/
│   │   │   ├── 中華民國憲法與警察專業英文/
│   │   │   │   └── 試題.json
│   │   │   └── .../
│   │   └── .../
│   └── .../
├── scripts/                     # 工具腳本
│   ├── download/                # 從考選部下載 PDF
│   │   ├── concurrent_download.py    # 併發排程
│   │   ├── http_client.py            # Retry/Resume/PDF 完整性
│   │   └── ...
│   ├── parse/                   # PDF → JSON 解析（v2）
│   │   ├── pdf_to_questions.py       # CLI 入口（併發 + 增量）
│   │   ├── patterns.py               # 正則集中地
│   │   ├── ocr_fallback.py           # PyMuPDF + rapidocr
│   │   ├── ocr_repair.py             # wordninja 修復英文斷字
│   │   └── manifest.py               # 增量處理 manifest
│   └── audit/                   # 資料品質驗證
├── tests/                       # pytest 單元測試
├── cache/                       # parse_manifest.json, ocr/, http_meta.json
├── archive/                     # 歷史腳本（已完成的一次性修復）
├── config.py, logger.py, ...    # 核心支援模組
└── README.md
```

每個 `試題.json` 對應一個學系/類別在特定年份的一個科目考卷。

## 網站：模擬考試中斷回復

`考古題網站/quiz.html` 的模擬考試進行中會把場次快照（題目、作答、標記、
目前題號與計時狀態）寫進瀏覽器的 `localStorage` `exam-quiz-active`，
讓重新整理或分頁／程序被中斷後可以接著作答，而不是整場重來。

- **完全本機**：沒有帳號、雲端同步或跨裝置分享，資料只留在該瀏覽器。
- **題型保持**：多個官方正解、送分、題組文章與選項圖片都會隨場次保存，回復後
  仍依原有答案契約計分。舊 v1 的單一整數正解快照可回復並升級；圖片僅接受網站內
  的相對資產路徑，遭竄改的外站、可執行連結或未轉義標記會拒絕載入。
- **回復**：重新載入後設定頁會出現「繼續作答／捨棄這次考試」橫幅，
  橫幅上的剩餘時間會持續更新；點擊時會重新讀取檢查點並依據 `savedAt`
  扣除離線期間的時間，倒數不會因為重新整理而暫停，恢復後設定表單也會
  對齊成這場考試的題數與時間。
- **逾時**：離線期間已逾時的場次不會出現在橫幅上，會直接清除並留在設定頁，
  不會開啟一個 `00:00` 的死場次。
- **清除時機**：交卷或按「捨棄這次考試」即清除；資料缺漏、毀損、過期
  （>24 小時）或欄位不一致時一律安全退回設定頁。
- **場次保護**：交卷／捨棄後，舊分頁不能寫回已清除的場次，也不能覆寫或清除
  後來開始的新場次。舊版沒有場次識別的有效快照仍可回復；限時計時資料必須
  符合「已用時間＋剩餘時間＝考試時長」。繼續作答會將寫入權交給回復的分頁，
  避免原分頁卸載時覆寫回復後的新答案；橫幅定期刷新時若檢測到場次已在另一分頁接手亦會自動收起，避免舊分頁改綁或清掉進行中的作答。
- **儲存失敗**：私密瀏覽或配額已滿時檢查點寫入會失敗，模擬考試本身照常進行
  （只是沒有回復能力），不會中斷作答。
- 驗證邏輯集中在 `考古題網站/js/quiz-checkpoint.js`；
  `tests/test_quiz_session_flow.py` 會實際執行 `quiz.html` 的流程
  （開始 → 作答／標記 → 檢查點 → 重整 → 回復 → 交卷），
  `tests/test_quiz_checkpoint.py` 驗證模組本身的契約，
  `tests/test_quiz_checkpoint_modern.py` 使用實際 AnswerUtils 與頁面腳本驗證現代題型、
  舊版回復及遭竄改的文章／圖片資料。

## 解析 Pipeline (v2)

```bash
# 全量解析（首次或 --force）
python scripts/parse/pdf_to_questions.py --input 考古題庫 --workers 8

# 增量重跑：未變更的 PDF 自動跳過（檢查 sha256+mtime+size）
python scripts/parse/pdf_to_questions.py --input 考古題庫

# 停用 OCR fallback（只用 pdfplumber）
python scripts/parse/pdf_to_questions.py --no-ocr

# 跑單一 PDF
python scripts/parse/pdf_to_questions.py --input path/to/試題.pdf
```

主要優化：

| 模組 | 變更 |
|---|---|
| `pdf_to_questions.py` | ProcessPoolExecutor 併發 + tqdm 進度條 |
| `manifest.py` | 增量處理：跳過未變更 PDF（sha256+mtime） |
| `ocr_fallback.py` | pdfplumber 抽不到文字 → PyMuPDF 渲染 + rapidocr-onnxruntime |
| `ocr_repair.py` | wordninja 取代硬編 OCR_FIXES 規則 list |
| `patterns.py` | 所有正則集中 + pytest 覆蓋 |
| `http_client.py` | Retry/Backoff + Range 續傳 + PDF 完整性 + 304 cache |

OCR fallback 需要選用依賴：

```bash
pip install PyMuPDF rapidocr-onnxruntime
```

## JSON 結構

### 檔案格式

```json
{
  "metadata": {
    "exam_name": "警察人員考試",
    "level": "三等",
    "subject": "中華民國憲法與警察專業英文",
    "exam_time": "2 小時",
    "code": "50120"
  },
  "notes": "代號：50120 ...",
  "questions": [...]
}
```

### 選擇題 (choice)

```json
{
  "number": 1,
  "type": "choice",
  "stem": "依憲法規定,考試院副院長人選之同意權屬於下列何者?",
  "options": {
    "A": "總統",
    "B": "立法院",
    "C": "考試院",
    "D": "監察院"
  },
  "answer": "B",
  "section": "乙、測驗題",
  "passage": "（閱讀測驗段落文字，僅克漏字/閱讀題有此欄位）"
}
```

### 申論題 (essay)

```json
{
  "number": "一",
  "type": "essay",
  "stem": "英譯中:請將下列英文翻譯成中文(10 分)\n...",
  "section": "甲、申論題"
}
```

### 欄位說明

| 欄位 | 類型 | 說明 |
|------|------|------|
| `number` | int/string | 題號。選擇題為阿拉伯數字，申論題為中文數字（一、二、三...） |
| `type` | string | `"choice"` 或 `"essay"` |
| `stem` | string | 題幹文字 |
| `options` | object | 選項 A-D（僅選擇題） |
| `answer` | string | 正確答案 A/B/C/D 或 `"送分"`（僅選擇題） |
| `section` | string | 所屬區段（甲、申論題 / 乙、測驗題） |
| `passage` | string | 閱讀測驗/克漏字的共用段落文字（選填） |
| `_note` | string | 備註（如已知出題瑕疵說明，選填） |

### 特殊值

- `answer: "送分"` — 該題所有考生均給分（178 題）
- `answer: "C或D"` 等「或」複選答案 — 官方公布所列選項皆給分（3 題）
- `options: {"A": "[圖片選項]", ...}` — 原卷圖形無法文字化（4 題）；`option_images` 保留 A–D 原圖、替代文字、公開路徑與 SHA-256，`source_locator` 保留官方 PDF URL、頁碼與 PDF SHA-256
- `_is_duplicate: true` — metadata 中標記為已知重複資料夾

## 學系/類別列表

### 三等（警察大學）
交通學系交通組、交通學系電訊組、公共安全學系情報組、公共安全學系社安組、刑事警察學系、國境警察學系境管組、國境警察學系移民組、外事警察學系、水上警察學系、法律學系、消防學系、犯罪防治學系矯治組、犯罪防治學系預防組、行政管理學系、行政警察學系、資訊管理學系、鑑識科學學系

### 四等（警察專科）
交通警察交通組、交通警察電訊組、公共安全、刑事警察、國境警察、外事警察、水上警察、消防警察、犯罪防治矯治組、犯罪防治預防組、行政管理、行政警察、警察法制、資訊管理、鑑識科學

## 資料品質

本資料庫經過多輪自動化品質檢查與修復：

- **結構完整性**: P0=0, P1=0, P2=0（deep_audit 全通過）
<!-- corpus-quality:begin 由 scripts/check_corpus_claims.py 驗證，請勿手改 -->
- **選項完整率**: 36,760/36,760 = 100%
- **答案合法率**: 36,760/36,760 = 100%
- **驗證範圍**: 2,049 份非重複試題 JSON、36,760 道選擇題（含 115 年 550 題；另有 41 份重複副本共 1,217 題另行列出，不混入唯一題數）
- **Canonical scope**: 只排除 `metadata._is_duplicate=true`；42,518 題（36,760 選擇 / 5,758 申論）、49 類科
- **Search scope**: 同時排除頂層與 `metadata._is_duplicate=true`；由 `loadIndex().stats.total` 動態顯示，離線生成值為 42,482 題（36,760 選擇 / 5,722 申論）
- **Homepage scope**: 內軌 17 類科投影；24,876 題
- **Analytics scope**: 與 canonical 相同；42,518 題、49 類科
- **圖片選項題**: 4 題保留 `[圖片選項]` 文字標記，另提供 `option_images` 與 `source_locator`；圖片資產由專屬測試驗證
- **統計基準**: `考古題庫/quality_summary.json`（含資料指紋與納入/排除規則）
<!-- corpus-quality:end -->
- **題號連續性**: 無缺漏、無重複
- **PUA 字元**: 已全數替換為正確文字
- **英文連字**: 已全數修復（wordninja 分詞）
- **選項標記**: 已清除前綴殘留
- **段落/選項混入**: 已修復英文閱讀測驗邊界問題

### 已知限制

1. 圖片題（4 題）保留原卷圖片；替代文字提供題號與選項脈絡，精確圖形內容仍須查看圖片或官方 PDF
2. 移民組 111 年入出國法規 Q7 選項 B 與 D 內容相同，為原卷出題瑕疵（已加 `_note` 說明）
3. 同年同等級共用考卷（國文、英文等）會在多個學系資料夾中重複出現

## 查詢工具

內建 SQLite 索引查詢 API，支援命令列和 Python 兩種方式。

Python 查詢結果的 `option_images` 與 `source_locator` 為 JSON 物件；舊版產生的索引會從完整來源重建後原子升級。若來源損壞、不完整或資料庫含自訂資料表，升級會失敗並保留原始資料庫。

```bash
# 建立索引（首次使用）
python examdb.py build

# 關鍵字搜尋
python examdb.py query --keyword "基本權" --year 112

# 按科目查詢
python examdb.py query --subject "憲法" --category "行政警察"

# 匯出圖片題及完整來源 JSON（query / random 均支援 --json）
python examdb.py query --year 109 --keyword "進港嘴" --json

# 隨機抽題練習
python examdb.py random --count 5 --subject "刑法"

# 統計摘要
python examdb.py stats
```

```python
# Python API
from examdb import ExamDB

with ExamDB() as db:
    results = db.search(year=112, keyword="基本權", limit=10)
    stats = db.stats()
    random_qs = db.random(n=5, subject="憲法")
```

全文搜尋題數由載入後的 `search-index.json` `stats.total` 動態顯示；搜尋同時排除頂層與 metadata 重複旗標。

## 驗證

```bash
# 執行自動化品質測試套件
python -m pytest tests/ -v

# 驗證公開題數/品質分母與 quality_summary.json 一致（CI 同項檢查）
python scripts/check_corpus_claims.py
```

### 語料統計單一來源

`考古題庫/quality_summary.json` 是所有公開題數與品質分母的 machine-readable
來源，包含資料指紋（sha256）、納入/排除規則、逐年度題數、選項完整率與
答案合法率的分子/分母，以及首頁（內軌 17 類科）投影。

```bash
# 語料更新後：重建摘要並重填 README / quiz / manifest 受管區塊
python scripts/check_corpus_claims.py --write

# 其餘衍生檔由各自產生器維護
python scripts/build_home_stats.py
python scripts/build_category_pages.py
python scripts/apply_layout_refinements.py
python scripts/build_search_index.py
python scripts/build_analytics.py
python scripts/sync_analytics_frontend.py --analytics 考古題網站/data/analytics.json
```

類科頁建置涵蓋首頁 17 類科與水上警察、消防警察 2 個圖片題舊網址；更新後請一併提交 HTML。
類科頁的互動控制會在共用腳本完成初始化前停用，並顯示載入提示；載入失敗時
保留提示，可重新整理重試，不會暗中重播點擊。文字與一般連結不會被移除。
腳本網址帶固定版本參數，避免新頁面使用仍在 PWA 快取中的舊版初始化程式。
`python scripts/build_category_pages.py --check` 會在暫存目錄重建並比對現有頁面，
統計、年度、題文或圖片標記過期時以非零結束碼失敗，且不改寫來源頁面。
比對忽略頁尾產生日期與另行掛載的 `layout-refinements.css` 連結，並保留搜尋、測驗及 PWA 入口。
既有 PDF 下載連結依科目卡片 ID 保留為展示資料；檢查不驗證這些連結的變更或 PDF 資產可用性，
也不會把舊題文帶入重建結果。指定 `--output` 時，只保留該目錄本身的 PDF 入口。

## 模擬考逐題複習

網站的「模擬考試」會在瀏覽器本機保存逐題 Attempt Ledger，而不只保存總分。每筆紀錄包含 stable question locator（類科／年份／科目／題號）、作答結果、選擇答案、作答時間（資料可靠時）、題目內容 hash、資料集版本、測驗模式與篩選條件；答案結果與「標記回顧」是分開保存的。

「今日複習」由 ledger deterministic 派生，排除未到期且無其他複習原因的正答題。最多一半名額依類科／科目最近作答時間輪替覆蓋，其餘優先安排答錯、未答、標記與到期題；每日僅一題時先輪替覆蓋。每題會顯示如「上次答錯」「連續 2 次答錯」「標記回顧」「21 天未複習」等原因。使用者可設定目標考試日、每日題量與分鐘預算；截止日模式會將 due date 限制在考試日前，依每日題量與使用者設定的規劃每題分鐘估算容量不足時顯示 backlog/overload。每日容量為 min(題量上限, floor(分鐘上限／規劃每題分鐘))；0 分鐘表示不限時且不設時間容量上限。這是規劃估算，不是測得的作答速度或學習成效。單場題量上限 200 題、分鐘上限 1440，與 durable checkpoint 的範圍一致。

學習資料可從模擬考頁匯出／匯入 JSON。匯入先驗證 schema、逐題事實與設定；無效檔案會拒絕匯入，設定寫入失敗時還原原 ledger。題目 hash 改變或缺失時標記為 `STALE/REVIEW_REQUIRED`，重新作答後可由相容紀錄恢復進度；只有整體資料集版本改變、題目內容未變時仍保留進度，build version 留作來源紀錄。交卷儲存失敗會保留原 durable checkpoint 供重試；清除 checkpoint 重試不會重複保存作答事實。舊版進行中場次若沒有官方來源識別，恢復後保留為不同的 UNMAPPED_REVIEW_REQUIRED 快照與作答，仍可匯出／匯入，但不會套用至官方題目的複習狀態。清除學習資料只移除 `exam-question-attempt-ledger`、`exam-review-settings` 與 `exam-quiz-history`，不會刪除題庫或書籤；資料不會離開瀏覽器。目前 localStorage 寫入尚未支援跨分頁交易，請避免同時在多個分頁交卷或匯入。

## 115 年資料更新

115 年警察人員三等考試已依考選部考畢試題查詢平臺匯入，包含 13 類科、90 科次的試題，以及官方標準答案與更正答案。匯入來源、SHA-256 與檢查結果詳見 `docs/115-import-report.md`。

## 資料來源

所有題目與答案來自[考選部全球資訊網](https://wwwq.moex.gov.tw/exam/)公開的考試題目及測驗式試題答案 PDF。

## 授權

本資料庫為教育研究用途整理，原始考題著作權歸考選部所有。
