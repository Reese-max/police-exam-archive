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

## RAG 語料

| 指令 | 產出 |
|---|---|
| `python scripts/rag/fetch_moex_catalog.py` | 讀取考選部公開「試題及答案」目錄 → `rag/moex_catalog.json`（原始 HTML 快取於 `rag/moex_cache/`，不進版控） |
| `python scripts/rag/build_source_map.py` | 每份考卷對應考選部試題／答案 PDF 網址 → `rag/source_map.json`（未對應者列於 `rag/source_map_unresolved.json`） |
| `python scripts/rag/build_corpus.py` | 去重、正規化語料 → `rag/corpus.jsonl`（不進版控）、`rag/corpus_stats.json`、`rag/corpus_issues.json` |
| `python scripts/rag/repair_english.py [--apply]` | 修正英文黏字，預設只產報告 |

`corpus.jsonl` 每行一題：`question_id`、題幹、選項、答案與 `answer_status`、題組文章、所有出處 `appears_in`，以及考選部原始 PDF 連結 `sources`，可直接用於檢索與溯源。

### RAG 來源覆蓋率

`rag/corpus_stats.json` 的 `questions_with_sources` 表示題目有本地來源對應資料（來源路徑及其 URL 欄位），
不代表一定有 PDF 連結。`questions_with_question_pdf_url` 與 `questions_with_answer_pdf_url` 分別計算至少一筆
來源具有非空考選部試題／答案 PDF URL 的去重題目；`choice_questions_with_question_pdf_url` 與
`choice_questions_with_answer_pdf_url` 是相同口徑下的選擇題數。各 URL 欄位分開統計，一題可同時計入兩者。
目前語料有 10,594 題具本地來源對應，但其中 8,514 題有試題 PDF URL、6,814 題有答案 PDF URL；
選擇題的對應數為 6,419 題（試題）及 6,419 題（答案）。執行建置指令可更新這些數字。

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

現行法條取自全國法規資料庫開放資料，法規清單由 `rag/law_list.json` 限定；
使用 `python scripts/rag/fetch_laws.py --source <ChLaw.json或law.zip>` 更新 `rag/laws.jsonl`，
再以 `python scripts/rag/build_index.py --laws rag/laws.jsonl` 寫入題目索引 SQLite。
目前法條資料日期為 2026/10/30（來源 `UpdateDate`），查詢預設附上最多 3 條相關法條，
可用 `--law-k 0` 關閉。

可選擇以 `python scripts/rag/query.py "問題" --answer` 產生 AI 整理回答；HF Space 提供
對話式介面，設定 `RAG_LLM_API_KEY` secret 後可使用 AI 回答，未設定時只回檢索結果。可設定
`RAG_LLM_BASE_URL`（預設 `https://api.minimax.io/v1`）、`RAG_LLM_MODEL`（預設
`MiniMax-M3.1-Flash`）、`RAG_LLM_TIMEOUT`（預設 180 秒）、`RAG_LLM_REASONING_EFFORT`（預設 high，不設輸出 token 上限；實測 2～36 秒）及 Space 每小時上限
`RAG_LLM_MAX_PER_HOUR`（不設定＝不限次數；設數字才限制，每一則實際送出模型的訊息都計入）。主要模型限流或失敗時，設有 `RAG_LLM_FALLBACK_API_KEY` 就改送備用模型（`RAG_LLM_FALLBACK_BASE_URL` 預設 `https://api.openai.com/v1`、`RAG_LLM_FALLBACK_MODEL` 預設 `gpt-6-luna`、`RAG_LLM_FALLBACK_REASONING_EFFORT` 預設 low，設為空字串則不送此欄位；按量計費），兩者都失敗才只回檢索結果。有檢索依據的回答
會驗證引用編號；資料未涵蓋處可由模型自身知識補充，並由程式強制標示「未經查證」。
追問時若本次檢索沒有條文，且考題為低信心或沒有考題，會以前一則使用者問題加上本次問題重查；追問訊息含 [題n]／[條n] 時沿用上一輪的檢索，讓編號與畫面一致；引用編號每一輪重新編排，沒有引用的段落與清單項目一律歸入「未經查證」；
兩段回答及可展開的檢索來源會分開呈現。模型與費用來源為 MiniMax Token Plan，並與其他用途共用額度。

模型與 tokenizer 預設使用 worktree 的 `.hf_cache/`，亦可透過 `RAG_MODEL_CACHE` 指向既有快取；
預設允許首次載入時下載公開權重，不執行遠端模型程式碼，也不使用 API 金鑰。需離線執行時，
可在快取完整後設定 `HF_HUB_OFFLINE=1`。
建置、查詢與評估支援 `--device auto|cpu|cuda`；auto 偵測 CUDA，指定不可用的 cuda
會報錯。CPU 查詢仍需要相同模型的本機權重；不會在查詢時重建文件向量。

向量 schema v2：每題先組合「完整題幹、選項、無歧異時的答案選項內容、資料夾科目名稱」；
若有答案歧異，保留所有選項但不將其中一個標記為正確。
題組文章另建向量。長文字按模型 tokenizer 的實際 token 預算切段，保留所有題幹內容，
不再讓文章佔滿 e5 的 512 token。相同文章片段只編碼與儲存一次，以 `question_vectors`
關聯多題；每題對所有關聯片段、所有查詢版本取最大 cosine 分數，結果每題只出現一次。
E5 使用 `passage: `／`query: `；bge-m3 dense 不加 E5 前綴。
`vectors` 保存輸入文字與 little-endian float32 正規化向量。meta 記錄 schema、模型、
維度、corpus SHA-256、實際編碼裝置與版本化 `model_identity`。第 3 版模型身分根據載入後的
完整權重與所有 buffer（含非持久 buffer）、模組類型與設定、tokenizer 實際內容與輸入欄位、
模型輸入過濾參數、模型／pooling、切段與編碼設定，以及相關套件版本計算；revision、
模型名稱或維度本身都不是權重證明。增量編碼、續跑及每次向量查詢都核對身分；不符即停止。
明確指定不同模型名稱時，可信索引沿用原有的全量重建行為。

Hub 模型在載入各模組前，先將 `main` 解析為完整 commit，並在新索引記錄 `model_revision`；
後續增量建置、續跑及查詢使用該 commit，而不是重新追蹤可能已移動的 `main`。無法解析或
取得該版本時會停止，離線使用需先備妥對應版本的完整快取。commit 和快取路徑只用來定位，
可寫入的本機檔案仍可能被修改，因此每次向量運算仍須比對實際內容指紋。
本機模型目錄不推定為 Hub 模型，也不記錄 Hub revision。既有索引若已有內容身分但沒有
revision，使用時會解析當前 Hub 版本並比對內容，但不會回填或宣稱原始來源版本。

重跑相同 corpus 不載入模型、不重算向量。題文更新 FTS，題幹／選項／正確答案內容／科目／
文章變動才使相應向量失效；僅出處網址異動只更新 JSON。刪題會清理關聯與無人引用的向量。
`--no-embed` 會使有變動題目的向量關聯失效，之後 `--embed` 補齊。
每批向量與維度一併提交；尚未編碼的列保留 NULL，續跑只補缺漏。
首批失敗會回復此次更新，後續中斷保留已提交批次；殘留 journal 由 SQLite 復原，勿手動刪除。
向量不完整時 vector/hybrid 會報錯，keyword 仍可使用。年度更新沿用原 corpus 建置流程。

向量輸入規則另以 `embedding_text_version` 記錄。**舊索引有向量但沒有可信的模型身分時，
無法由抽樣或目前快取補證來源**：保留舊檔，keyword 與真正不需編碼的 no-op 仍可使用；
若要更動該索引、補建或進行向量查詢，請指定新的 `--db` 完整重建。例如：

```bash
python scripts/rag/build_index.py --model BAAI/bge-m3 --db rag/index-bge-m3-verified.sqlite --device cuda --batch-size 8
```

第 1、2 版模型身分未涵蓋所有會影響輸出的狀態，因此不能視為第 3 版；既有第 1、2 版向量索引
仍可 keyword 與 no-op，但向量運算須在新檔完整重建。

目前自動驗證僅支援標準 SentenceTransformer BERT／XLM-R transformer + pooling，及可選的 normalize，
搭配可序列化的 XLM-R backend tokenizer；adapter、量化、自訂模組、實例方法覆寫及 PyTorch 全域 forward hook 會明確拒絕。程式注入的
編碼器須提供 `rag_identity`（小寫 64 位 SHA-256 字串），由呼叫端負責涵蓋權重、tokenizer
與所有影響輸出的行為；這是呼叫端的契約，並非程式對注入編碼器內容的獨立驗證。
直接注入的編碼器由呼叫端管理來源，不會自動記錄 Hub revision；對已記錄 revision 的索引，
注入 factory 須接受 `revision` 關鍵字參數，並依該定位載入模型。
完整雜湊有實際成本：每次向量查詢編碼前、後各完整核對一次模型權重與設定，每批建置也會在編碼前及提交前核對。第 3 版
以最多四個執行緒平行雜湊各個 tensor，仍不省略內容。本機 BGE-M3 CPU 單題隔離索引的三次
暖機查詢為 7.862、7.711、10.984 秒；這是小樣本，不能代表完整資料集或 p95，實際時間依
硬體及負載而異。尚未重測 150 題 p95，不能宣稱達到 500 ms 目標。no-op 不載入模型。
同一 PyTorch 上游版本的 `+cpu`／`+cuNNN` wheel 後綴視為相容，不同上游版本仍分別核對。
Space 與更新 workflow 固定相同上游模型套件版本。
新版索引使用觸發器阻擋舊建置器
寫入，並保留使用者觸發器；SQLite `trusted_schema=OFF` 下建置會失敗並回滾，不會自動
降低安全設定。合作的建置與更新程序使用固定的 `.索引檔名.rag-write.lock` 旁檔跨批次互斥；
旁檔會保留，作業系統會在程序結束時釋放鎖。具有多個硬連結的索引會拒絕寫入；若替換時才出現
舊索引硬連結，更新會保留該連結並回報狀態不確定。年度更新替換
候選檔時，若來源處於 WAL 模式或仍有 SQLite journal／WAL sidecar，會保留原檔並停止；
初次檢查及備份時分別完整雜湊來源快照；若需替換，會在獨占鎖下再次核對，並讀取候選與目的地
驗證結果，防止覆寫其他提交或錯報替換成功。這些完整讀檔有額外成本，no-op 也會完整讀取來源兩次。
若 SQLite 讀者或寫入者使資料庫鎖定，已提交的安全批次保留，釋放鎖後可重試。Windows 的原子
替換需要檔案系統支援 POSIX 語意；不支援時會停止並保留原檔。

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
查詢結果的 `answer_confidence` 為 `disputed`（有答案歧異）或 `unknown`；`unknown` 不代表
答案已經核實。衝突題顯示的來源資料夾題號仍須對照官方試卷。
查詢文字與 Space 介面會列出每題的民國年度；科目名稱含「法」等法律標記時，另提醒法規可能已修正。
hybrid 可用 `--min-vector-score` 啟用低信心提示：只有 top-1 cosine 低於門檻且沒有關鍵字片語命中時，
結果才標記為低信心；未設定（預設 `null`）維持原行為。`bench_report.json` 暫不設定此值，應先由呼叫端以
實際模型與索引校準，再將建議值加入 `selected_default.configuration`：

```bash
python scripts/rag/calibrate_threshold.py --profile rag/bench_report.json --device cpu
```

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
`bench_report.json` 記錄的是先前語料的評估結果；題庫更新後須重新評估檢索品質與延遲。

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

## Gradio 對話介面

本機需另行安裝 `gradio==5.50.0`；Space 平台會提供 Gradio。使用既有索引和模型快取（PowerShell 範例）：

```powershell
$env:RAG_INDEX_PATH = "rag/index-bge-m3.sqlite"
$env:RAG_MODEL_CACHE = ".hf_cache"
$env:HF_HUB_OFFLINE = "1"
python space/app.py
```

介面預設只監聽本機，使用 benchmark 選定的 BGE-M3 混合檢索參數；顯示前五題及其出處，
以對話方式回答並支援追問。未解析的考選部 PDF 會標示為「未解析」。
設定 `RAG_LLM_API_KEY` 才會使用 AI；沒有金鑰時仍可檢索。`RAG_MODEL_CACHE` 可指向其他既有快取。

準備 Hugging Face Space 目錄（不會上傳或使用帳號）：

```bash
python scripts/rag/package_space.py --out /path/to/new-space-directory
```

可加上 `--essay-mcp <已建置的申論 MCP 專案目錄>`，將 Space 啟動所需的 MCP 檔案一併封裝。
部署後設定 Space 變數 `RAG_ESSAY_MCP_DIR=essay-mcp` 才會啟用；每次啟動會隨機產生 token，
申論答案與匯出檔放在暫存目錄，Space 重啟即清空。目前使用一般申論模板；165 原稿紙模板需要另備字型。

日後經授權建立 Space 後，上傳該目錄，並設定 `HF_DATASET_REPO` 指向已有索引的公開
Dataset；Space 啟動時匿名下載索引。[Hugging Face 官方文件](https://huggingface.co/docs/hub/spaces-overview)
目前指出 CPU Basic 無時租，但建立 Gradio Space 需要付費方案；建立前應先確認帳號方案與費用。
符合資格的免費個人帳號亦可使用 ZeroGPU（`zero-a10g`）；本介面仍只在 CPU 執行檢索。

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
