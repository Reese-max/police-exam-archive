# 警察特考考古題資料庫

台灣警察人員特種考試（三等、四等）考古題結構化 JSON 資料庫，涵蓋 106-115 年（2017-2026）各學系/類別的所有科目。

## 資料規模

| 項目 | 數量 |
|------|------|
| 學系/類別資料夾 | 32 個（其中 9 組為同一學系的新舊名稱，見 `rag/corpus_issues.json`） |
| 年份 | 106-115 年（10 年） |
| 科目資料夾 | 104 個 |
| JSON 檔案 | 2,090 個 |
| 選擇題 | 37,905 題 |
| 申論題 | 5,830 題 |
| 總題數 | 43,735 題 |
| 不重複題（跨學系去重） | 10,594 題 |

數字由 `python scripts/rag/build_corpus.py` 產生，見 `rag/corpus_stats.json`。

## RAG 語料

| 指令 | 產出 |
|---|---|
| `python scripts/rag/fetch_moex_catalog.py` | 讀取考選部公開「試題及答案」目錄 → `rag/moex_catalog.json`（原始 HTML 快取於 `rag/moex_cache/`，不進版控） |
| `python scripts/rag/build_source_map.py` | 每份考卷對應考選部試題／答案 PDF 網址 → `rag/source_map.json`（未對應者列於 `rag/source_map_unresolved.json`） |
| `python scripts/rag/build_corpus.py` | 去重、正規化語料 → `rag/corpus.jsonl`（不進版控）、`rag/corpus_stats.json`、`rag/corpus_issues.json` |
| `python scripts/rag/repair_english.py [--apply]` | 修正英文黏字，預設只產報告 |

`corpus.jsonl` 每行一題：`question_id`、題幹、選項、答案與 `answer_status`、題組文章、所有出處 `appears_in`，以及考選部原始 PDF 連結 `sources`，可直接用於檢索與溯源。

## 檢索與查詢

先建立語料與 keyword 索引，不需模型套件或 API 金鑰：

```bash
python scripts/rag/build_corpus.py
python scripts/rag/build_index.py --no-embed
python scripts/rag/query.py "警察職權行使法 查證身分" --mode keyword
python scripts/rag/query.py "警職法" --mode keyword --expand-abbreviations
```

向量套件 `sentence-transformers` 為選用依賴；程式不會自動安裝。請在已提供套件的環境
以本機 GPU 建索引、CPU 測查詢；兩個模型使用不同的 `--db`：

```bash
python scripts/rag/build_index.py --model intfloat/multilingual-e5-small --db rag/index-e5.sqlite --device cuda --batch-size 64
python scripts/rag/build_index.py --model BAAI/bge-m3 --db rag/index-bge-m3.sqlite --device cuda --batch-size 8
python scripts/rag/query.py "警察何時能攔人問身分" --db rag/index-e5.sqlite --device cpu
```

模型與 tokenizer 快取固定在 worktree 的 `.hf_cache/`，不執行遠端模型程式碼，不使用
API 金鑰。首次取得公開權重需要連網；快取完整後可設 `HF_HUB_OFFLINE=1`。
建置、查詢與評估支援 `--device auto|cpu|cuda`；auto 偵測 CUDA，指定不可用的 cuda
會報錯。CPU 查詢仍需要相同模型的本機權重；不會在查詢時重建文件向量。

向量 schema v2：每題先組合「完整題幹、選項、已知正確選項內容、資料夾科目名稱」，
題組文章另建向量。長文字按模型 tokenizer 的實際 token 預算切段，保留所有題幹內容，
不再讓文章佔滿 e5 的 512 token。相同文章片段只編碼與儲存一次，以 `question_vectors`
關聯多題；每題對所有關聯片段、所有查詢版本取最大 cosine 分數，結果每題只出現一次。
E5 使用 `passage: `／`query: `；bge-m3 dense 不加 E5 前綴。
`vectors` 保存輸入文字與 little-endian float32 正規化向量。meta 記錄 schema、模型、
維度、corpus SHA-256 及實際編碼裝置；舊 schema 或模型變更會全量重建向量。

重跑相同 corpus 不載入模型、不重算向量。題文更新 FTS，題幹／選項／正確答案內容／科目／
文章變動才使相應向量失效；僅出處網址異動只更新 JSON。刪題會清理關聯與無人引用的向量。
`--no-embed` 會使有變動題目的向量關聯失效，之後 `--embed` 補齊。
每批向量與維度一併提交；尚未編碼的列保留 NULL，續跑只補缺漏。
首批失敗會回復此次更新，後續中斷保留已提交批次；殘留 journal 由 SQLite 復原，勿手動刪除。
向量不完整時 vector/hybrid 會報錯，keyword 仍可使用。年度更新沿用原 corpus 建置流程。

keyword 使用 SQLite FTS5 trigram BM25；完整片語優先，無命中才按空白拆詞 AND／OR，
不足三字使用跳脫萬用字元的 LIKE。hybrid 預設候選各 50 筆，以加權 RRF 合併：
`keyword_weight/(k+rank) + vector_weight/(k+rank)`。完整查詢片語命中先排前面，
且保留 keyword 在這些命中之間的次序；可選 reranker 也不會破壞此規則。
同分按題目 ID 固定排序；下列參數可調：

```bash
python scripts/rag/query.py "查證身分" --db rag/index-e5.sqlite --device cpu --keyword-weight 2 --vector-weight 1 --rrf-k 60 --candidates 50 --phrase-priority
# 復現舊等權融合（使用目前 schema v2 向量，並非舊文件向量的完整歷史復現）
python scripts/rag/query.py "查證身分" --db rag/index-e5.sqlite --keyword-weight 1 --vector-weight 1 --no-phrase-priority --no-expand-abbreviations
```

**2:1、k=60 是待測的暫用值，尚未宣稱為實測最佳預設。** 最終值由下述 benchmark 選出，
再以 `--profile rag/bench_report.json` 套用；明確給的 CLI 參數優先於 profile。
當比較未完成、非 CPU 或沒有組合通過門檻時，`selected_default=null`，profile 會拒絕使用。

`rag/abbreviations.json` 收錄 31 組明確法規簡稱；`--expand-abbreviations` 啟用最長詞優先、
單次非遞迴替換，同時查原查詢及全名版本；keyword 合併兩版排名，向量批次編碼兩版並取最大分。
不自動更新法規名稱、不做模糊猜測；這是檢索用對照，不保證歷史題目適用現行法。

每題的文字出處按已知試題 PDF 網址分組，同網址學系合併一行，最多顯示三組；未知網址保持
未解析，依原路徑保留。`--json` 保留完整題文、所有原出處與答案歧異，不會刪掉原始引用。

語意集 `rag/eval_semantic.jsonl` 共 150 筆、15 科目，包含選擇及申論；34 筆（22.7%）使用
法規簡稱。逐題讀原題後編寫自然語言與相關性理由；人臉辨識的兩個近重複原題都標為相關。
標註是有限正例，未標題目不代表已確認不相關。原題未修改，也未加入臆測答案。
檢查器拒絕未知 ID、空理由、重複查詢、涵蓋不足及與任何相關題幹／選項共享連續四字的查詢；
採 NFKC、忽略大小寫、去掉空白及標點後檢查，比只比原字串更嚴格：

```bash
python scripts/rag/check_eval_set.py
python scripts/rag/bench.py --device cpu
# 明確指定索引；標準輸出含 Markdown 表，JSON 預設寫入 rag/bench_report.json
python scripts/rag/bench.py --device cpu --index intfloat/multilingual-e5-small=rag/index-e5.sqlite --index BAAI/bge-m3=rag/index-bge-m3.sqlite --weights 1 2 4 --rrf-constants 20 60 --repeats 3
# 選用：僅對前 20 筆執行 BAAI/bge-reranker-v2-m3
python scripts/rag/bench.py --device cpu --reranker
```

bench 不會建立或改寫索引。每個模型比較 keyword、vector、舊等權 RRF、新片語優先融合
（keyword 權重 1/2/4、RRF k=20/60），並比較簡稱展開；可加入重排。
先暖機（預設三次）再逐筆量測，時間包含查詢編碼、融合、可選重排與結果組裝，排除建索引及
初始載入。列 Recall@1/@5/@10、MRR@10、p50/p95；Recall 是每筆已標正例的找回比例再取平均，
p95 使用 nearest-rank。只在兩個指定模型的所有組合都完成後，選 CPU p95 ≤500 ms 且
Recall@5 高於 keyword 的最高 Recall@5 組合；同分依 MRR、p95、模型及組合名稱決定。
這是同一評估集的探索選型，未宣稱獨立測試集上的泛化效果。套用與字面驗收：

```bash
python scripts/rag/query.py "臨檢有哪些限制" --profile rag/bench_report.json --device cpu
python scripts/rag/eval_retrieval.py --profile rag/bench_report.json --n 500 --seed 0 --device cpu
```

字面評估沿用 seed=0、原題幹中間連續 15 字及原抽樣母體。NFC、合併空白與
ASCII／全形 `,;:?!()` 等同後，在完整 text 中只有一題含片段為 unique，多題則 ambiguous。
unique 使用嚴格 ID top-1/top-5，ambiguous 另列前 k 題至少一題包含片語的 relevant@k。
空群及未執行 gate 為 null，零包含仍計入全體分母。新 hybrid 門檻為 unique top-1 ≥0.95、
top-5 ≥0.98、ambiguous relevant@1 ≥0.95；結果寫入 `rag/eval_report.json`。
現存 `eval_report.json` 是先前 schema v1 的 500 題實測紀錄，**不是本輪多向量驗收**。
本沙箱沒有 sentence-transformers，真實雙模型建索引、CPU 延遲與最終預設選型待沙箱外執行；
`bench_report.json` 如含 null，表示未測，不能視為通過。

## 每年增量更新索引

啟用後，考古題匯入並合併至 `master` 時，`.github/workflows/rag-index.yml` 會下載上一版 Dataset
索引及考選部目錄、更新來源對應與語料，只為新增或變更的內容計算向量，再把兩個檔案一起上傳。
目錄缺少年份或新考卷時，會重新擷取該年度的考選部公開目錄。題庫匯入本身不由此工作流程執行。

首次啟用前，需先以本機 GPU 建好完整的 `rag/index-bge-m3.sqlite`，並在**既有公開**
Hugging Face Dataset 放入 `index-bge-m3.sqlite` 與 `moex_catalog.json`。建立 Dataset、
上傳、設定儲存庫變數 `HF_DATASET_REPO` 與具有該 Dataset 寫入權限的 GitHub Secret
`HF_DATASET_TOKEN`，都須由擁有者事先授權。完成設定及費用確認後，再將變數
`HF_RAG_UPDATES_ENABLED` 設為 `true`；在此之前工作不會啟動 runner。工作流程只讀 GitHub 內容，Dataset 下載不使用帳號；
上傳以下載時的 revision 為條件，避免覆寫並行更新。

可在本機用現有索引測試（請先將兩個檔案複製到 `.rag-dataset/`）：

```bash
python scripts/rag/update_index.py --device cuda --db .rag-dataset/index-bge-m3.sqlite --catalog .rag-dataset/moex_catalog.json --catalog-out .rag-dataset/moex_catalog.json --report .rag-update.json
```

缺少舊索引、模型或 schema 不符、舊索引不完整、語料為空或與舊索引完全無重疊時，
更新會停止，不會在 CPU 上自動全量重建。索引在副本建置成功後才替換；沒有變更時不載入模型，
也不會上傳。可設定 `RAG_MODEL_CACHE` 指向既有模型快取；模型下載仍不使用 HF token。
索引、向量與暫存語料不進 Git。

## Gradio 檢索介面

本機使用既有索引和模型快取（PowerShell 範例）：

```powershell
$env:RAG_INDEX_PATH = "rag/index-bge-m3.sqlite"
$env:RAG_MODEL_CACHE = ".hf_cache"
$env:HF_HUB_OFFLINE = "1"
python space/app.py
```

介面預設只監聽本機，使用 benchmark 選定的 BGE-M3 混合檢索參數；顯示前五題及其出處，
不呼叫 LLM。未解析的考選部 PDF 會標示為「未解析」。`RAG_MODEL_CACHE` 可指向其他既有快取。

準備 Hugging Face Space 目錄（不會上傳或使用帳號）：

```bash
python scripts/rag/package_space.py --out /path/to/new-space-directory
```

日後經授權建立 Space 後，上傳該目錄，並設定 `HF_DATASET_REPO` 指向已有索引的公開
Dataset；Space 啟動時匿名下載索引。[Hugging Face 官方文件](https://huggingface.co/docs/hub/spaces-overview)
目前指出 CPU Basic 無時租，但建立 Gradio Space 需要付費方案；建立前應先確認帳號方案與費用。

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

- `answer: "送分"` — 該題所有考生均給分（176 題）
- `answer: "C或D"` — 官方公布 C 或 D 皆給分（1 題）
- `options: {"A": "[圖片選項]", ...}` — 原卷為圖片題，無法文字化（4 題）
- `_is_duplicate: true` — metadata 中標記為已知重複資料夾

## 學系/類別列表

### 三等（警察大學）
交通學系交通組、交通學系電訊組、公共安全學系情報組、公共安全學系社安組、刑事警察學系、國境警察學系境管組、國境警察學系移民組、外事警察學系、水上警察學系、法律學系、消防學系、犯罪防治學系矯治組、犯罪防治學系預防組、行政管理學系、行政警察學系、資訊管理學系、鑑識科學學系

### 四等（警察專科）
交通警察交通組、交通警察電訊組、公共安全、刑事警察、國境警察、外事警察、水上警察、消防警察、犯罪防治矯治組、犯罪防治預防組、行政管理、行政警察、警察法制、資訊管理、鑑識科學

## 資料品質

本資料庫經過多輪自動化品質檢查與修復：

- **結構完整性**: P0=0, P1=0, P2=0（deep_audit 全通過）
- **選項完整率**: 36,210/36,210 = 100%
- **答案合法率**: 36,210/36,210 = 100%
- **題號連續性**: 無缺漏、無重複
- **PUA 字元**: 已全數替換為正確文字
- **英文連字**: 已全數修復（wordninja 分詞）
- **選項標記**: 已清除前綴殘留
- **段落/選項混入**: 已修復英文閱讀測驗邊界問題

### 已知限制

1. 圖片題（4 題）以 `[圖片選項]` 佔位，無法呈現原始圖片內容
2. 移民組 111 年入出國法規 Q7 選項 B 與 D 內容相同，為原卷出題瑕疵（已加 `_note` 說明）
3. 同年同等級共用考卷（國文、英文等）會在多個學系資料夾中重複出現

## 查詢工具

內建 SQLite 索引查詢 API，支援命令列和 Python 兩種方式。

```bash
# 建立索引（首次使用）
python examdb.py build

# 關鍵字搜尋
python examdb.py query --keyword "基本權" --year 112

# 按科目查詢
python examdb.py query --subject "憲法" --category "行政警察"

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

查詢速度依執行環境而異（目前 42,518 題全文搜尋）。

## 驗證

```bash
# 執行 18 項自動化品質測試
python -m pytest tests/ -v
```

## 115 年資料更新

115 年警察人員三等考試已依考選部考畢試題查詢平臺匯入，包含 13 類科、90 科次的試題，以及官方標準答案與更正答案。匯入來源、SHA-256 與檢查結果詳見 `docs/115-import-report.md`。

## 資料來源

所有題目與答案來自[考選部全球資訊網](https://wwwq.moex.gov.tw/exam/)公開的考試題目及測驗式試題答案 PDF。

## 授權

本資料庫為教育研究用途整理，原始考題著作權歸考選部所有。
