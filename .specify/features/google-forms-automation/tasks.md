# 實作任務: CSV → Google Forms 自動部署

> **基於**: spec.md v1.0, plan.md v1.0  
> **建立日期**: 2025-11-26  
> **最後更新**: 2025-11-26

## 任務摘要

- **總任務數**: 12  
- **預計時程**: 6 天 (可視人力並行)  
- **並行任務**: T1.3, T3.3, T5.2, T6.2

---

## Phase 1: 基礎與環境

### T1.1: 建立 Spec Kit 架構

- **描述**: 建立 `.specify/memory/constitution.md` 與 `features/google-forms-automation/` 內的 spec/plan/tasks。  
- **檔案**: `.specify/**`, `README.md` (加入連結)。  
- **驗收標準**:
  - [x] 憲章列出 4 項 MUST/SHOULD 原則。  
  - [x] Spec/Plan/Tasks 皆 reference README/指南。  
  - [ ] `README`「相關文件」指向 Spec Kit。
- **依賴**: 無。

### T1.2: 設定專案環境

- **描述**: 定義 `requirements.txt`（若需要）、`pyproject` baseline、`Makefile` 或 `invoke` 腳本。  
- **檔案**: `requirements.txt`, `pyproject.toml`, `Makefile` (可選)。  
- **驗收標準**:
  - [ ] `pip install -r requirements.txt` 成功。  
  - [ ] `python --version`、`node --version`, `clasp --version` 檢查腳本可執行。  
- **依賴**: T1.1。

### T1.3: CLI 參數框架 `[P]`

- **描述**: 使用 `argparse` 定義所有旗標，含多 CSV 支援、報告路徑。  
- **檔案**: `auto_generate_form.py`.  
- **驗收標準**:
  - [ ] `python auto_generate_form.py --help` 顯示完整說明。  
- **依賴**: T1.1。

---

## Phase 2: 資料層與報告

### T2.1: CSV 欄位偵測與正規化

- **描述**: 強化 `COLUMN_ALIASES`、`_detect_columns`，支援中文欄名與大小寫。  
- **檔案**: `auto_generate_form.py`, `tests/test_columns.py`.  
- **驗收標準**:
  - [ ] 任意別名能映射回標準欄位。  
  - [ ] 未知欄位時給出警告訊息。  
- **測試**:
  ```python
  def test_detect_columns_handles_chinese():
      ...
  ```
- **依賴**: T1.3。

### T2.2: 題幹與選項解析

- **描述**: 強化 `_split_question_and_options`，支援「」等符號及跨行選項。  
- **檔案**: `auto_generate_form.py`, `tests/test_parser.py`.  
- **驗收標準**:
  - [ ] 至少覆蓋 5 種題幹格式。  
  - [ ] 缺少任何選項時記錄 `report.warn` 並跳過。  
- **依賴**: T2.1。

### T2.3: 報告生成與輸出

- **描述**: 實作 `GenerationReport` class，含 `to_dict()` 與 `write_report`.  
- **檔案**: `auto_generate_form.py`, `tests/test_report.py`, `form_generation_summary.json` 範例。  
- **驗收標準**:
  - [ ] 報告含來源檔名、輸出檔、總題數、imported/skipped、warnings[]。  
  - [ ] CLI 退出碼會因 `warnings` 決策（configurable）。  
- **依賴**: T2.1, T2.2。

---

## Phase 3: Apps Script 產出

### T3.1: Template 與 Renderer

- **描述**: 將 `TEMPLATE` 拆至獨立模組或常數，支援 `questions_per_page`, `form_title/description`.  
- **檔案**: `auto_generate_form.py`, `src/Code.gs` (sample)。  
- **驗收標準**:
  - [ ] `render_gas()` 會插入時間戳與題數。  
  - [ ] 輸出保留 UTF-8，長題幹自動截斷。  
- **依賴**: T2.2。

### T3.2: 檔案寫入與路徑管理

- **描述**: `write_file` 確保目錄存在、覆寫前備份（可選）。  
- **檔案**: `auto_generate_form.py`.  
- **驗收標準**:
  - [ ] 指定任意相對/絕對路徑可成功生成檔案。  
  - [ ] CLI 輸出包含檔案大小與位置。  
- **依賴**: T3.1。

### T3.3: CLI 體驗優化 `[P]`

- **描述**: Emoji log、問答式提示（若缺少參數）、執行結束摘要。  
- **檔案**: `auto_generate_form.py`.  
- **驗收標準**:
  - [ ] 成功/失敗清楚顯示 `✅/❌/⚠️`。  
  - [ ] `--dry-run` 或 `--verbose` 旗標可開啟詳細輸出。  
- **依賴**: T3.1。

---

## Phase 4: 部署層

### T4.1: CLASP Push 自動化

- **描述**: 封裝 `run_command`，在 CLI 中加入 `--skip-push` 邏輯與錯誤處理。  
- **檔案**: `auto_generate_form.py`, `快速使用_clasp.*`.  
- **驗收標準**:
  - [ ] 成功 push 印出 `✅`, 失敗傳回 stderr。  
  - [ ] `--skip-push` 時不呼叫任何 CLASP 指令。  
- **依賴**: T3.2。

### T4.2: CLASP Run 與日誌

- **描述**: `--run` 旗標執行 `clasp run createFormFromCSV` 並擷取表單 URL / Execution ID。  
- **檔案**: `auto_generate_form.py`, `google_forms_setup_guide.md`.  
- **驗收標準**:
  - [ ] 結束時列出 `Form edit URL / Response URL`。  
  - [ ] 提示使用 `clasp logs` 取得 log。  
- **依賴**: T4.1。

---

## Phase 5: QA 與可觀測

### T5.1: QA 清單維護

- **描述**: 更新 `✅_檢查清單.txt`，加入題數、表單 URL、CLASP log ID。  
- **檔案**: `考選部考古題完整庫/情境實務考古題/✅_檢查清單.txt`.  
- **驗收標準**:
  - [ ] 每份表單需記錄「題數/選項檢查/正確答案備註」。  
  - [ ] 清單描述與 spec 一致。  
- **依賴**: T4.2。

### T5.2: 報告自動附加 `[P]`

- **描述**: CLI 執行完自動顯示報告路徑並建議在 PR/issue 張貼。  
- **檔案**: `auto_generate_form.py`, `README.md`.  
- **驗收標準**:
  - [ ] CLI 收尾輸出 `報告檔案: ...`。  
- **依賴**: T3.3, T4.2。

---

## Phase 6: 文件與發佈

### T6.1: README / Quick Start 更新

- **描述**: 在 README、QUICK_START、`google_forms_setup_guide` 中加入新流程、Spec Kit 連結、常見錯誤。  
- **檔案**: `README.md`, `QUICK_START.txt`, `google_forms_setup_guide.md`.  
- **驗收標準**:
  - [ ] README 提供 10 分鐘完成流程 + 指令。  
- **依賴**: T5.2。

### T6.2: 發布與驗證 `[P]`

- **描述**: 以 dev 帳號跑一次 full pipeline，附上 Form URL、報告、QA 清單於 PR。  
- **檔案**: PR template / release note。  
- **驗收標準**:
  - [ ] PR 描述含報告、log、Form URL。  
  - [ ] QA 清單勾選完成。  
- **依賴**: T4.2, T5.1。

---

## 任務依賴圖

```
T1.1 → T1.2 → T1.3
  └─────────────┐
                ▼
              T2.1 → T2.2 → T2.3 → T3.1 → T3.2 → T4.1 → T4.2
                                └────────────→ T3.3
T4.2 → T5.1
T3.3 + T4.2 → T5.2 → T6.1
T4.2 + T5.1 → T6.2
```

---

## 檢查清單

### 進行中
- [ ] 所有任務都有明確驗收標準與檔案。  
- [ ] 相依性清楚標示，並行任務已加 `[P]`。  
- [ ] 風險與技術負債記錄在對應 spec/plan/issue。

### 完成前
- [ ] 單元/整合測試通過。  
- [ ] 報告與 QA 清單更新。  
- [ ] README/指南同步。  
- [ ] PR 包含報告、Form URL、log。

---

**總計預估時間**: ~45 小時（含人工 QA）  
**關鍵路徑**: T1.1 → T1.3 → T2.1 → T2.2 → T2.3 → T3.1 → T3.2 → T4.1 → T4.2 → T5.1 → T6.2  
**並行窗口**: T1.3, T3.3, T5.2, T6.2 (依人力安排)
