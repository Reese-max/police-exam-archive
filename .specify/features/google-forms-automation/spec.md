# 功能規格: CSV → Google Forms 自動部署

> **狀態**: Draft  
> **建立日期**: 2025-11-26  
> **最後更新**: 2025-11-26  
> **負責人**: 情境實務自動化專案組

## 概述

### 背景

警察人員三等考試「情境實務」題庫需要快速轉成 Google Forms 供演練。既有流程仰賴手動貼題或 Apps Script 編輯，耗時且難以重複。`auto_generate_form.py` 目前已能將 CSV 轉為 Apps Script 並透過 CLASP 推送，但缺乏正式規格、任務拆解與標準化文件來支撐 Vibe Coding 式協作。

### 目標

- 5 份 CSV 能在 10 分鐘內產出 5 份可作答、可評分的 Google 表單。
- 每次部署都留下資料品質報告、CLASP log 與 QA 勾稽紀錄。
- 以 GitHub Spec Kit 建立一套可重複引用的標準文件結構，降低新成員上手時間至 < 15 分鐘。

### 範圍

**包含**:
- CSV 欄位檢查、欄位別名解析、題目/選項自動切割。
- Apps Script 生成（`Code.gs` / `google_forms_script.js`）與 `appsscript.json` 管理。
- CLASP push/run、自動登入提示，及部署後 QA 指南。
- 報告輸出（`form_generation_summary.json`）與 `✅_檢查清單.txt`。

**不包含**:
- PDF、影像或半結構化資料解析。
- Google Sheets 為中繼儲存層的維運。
- 外部測驗服務整合、題庫內容編輯器 UI。

## 功能需求

### FR-1: CSV 驗證與正規化

- **描述**: 解析 5 份 CSV，檢查欄位（題幹、選項A-D、年份、答案），並將混合標記的題目拆成題幹+選項。  
- **優先級**: High  
- **驗收標準**:
  - [ ] 缺欄或答案格式錯誤會被記錄並設定預設值，錯誤列不寫入輸出。
  - [ ] 每份 CSV 產生題目數、匯入/跳過列數統計。
  - [ ] 允許 `選項A~D` 缺漏時從題幹解析，仍須在報告中警告。

### FR-2: Apps Script 產生與覆寫

- **描述**: 依 CLI 參數輸出 Apps Script（含 `QUESTIONS` payload、`createFormFromCSV`），並保證與 CSV 同步。  
- **優先級**: High  
- **驗收標準**:
  - [ ] `QUESTIONS` 陣列為 JSON，保留 UTF-8 並限制單題 < 500 字（多餘截斷）。  
  - [ ] 生成檔案含自動化告警標頭、題數、時間戳。  
  - [ ] 若 `--output` 指向 `src/Code.gs` 以外路徑，仍自動建立目錄。

### FR-3: 生成報告與 QA 指標

- **描述**: CLI 執行後產出 `form_generation_summary.json`，並同步提示 QA 檢核重點。  
- **優先級**: Medium  
- **驗收標準**:
  - [ ] 報告包含 `csv_source`, `output_script`, `total_questions`, `stats`, `warnings`。  
  - [ ] 若 `warnings` 非空，CLI 以非 0 結束或提示人工處理。  
  - [ ] QA 清單列出五份表單名稱與驗收欄位（題數、正確答案備註）。

### FR-4: CLASP 串接與自動重跑

- **描述**: 腳本提供 `--skip-push`, `--run` 旗標；可呼叫 CLASP push/run 並回報結果。  
- **優先級**: High  
- **驗收標準**:
  - [ ] CLASP 命令失敗需回傳非 0 並印出錯誤。  
  - [ ] 成功執行時顯示 Apps Script Execution ID 及表單 URL。  
  - [ ] `快速使用_clasp.(bat|sh)` 透過相同流程呼叫腳本。

### FR-5: 可觀測與回溯流程

- **描述**: 建立 log/報表/Drive 連結的最小集合，利於稽核與再部署。  
- **優先級**: Medium  
- **驗收標準**:
  - [ ] `google_forms_setup_guide.md` 更新包含 log 擷取方法。  
  - [ ] QA 可藉由 `form_generation_summary.json` + CLASP log + Drive 搜尋結果完成驗證。  
  - [ ] PR 模板要求附上報告與表單連結。

## 非功能需求

- **效能**: 以 5 份各 100 題 CSV 為基準，CLI 需在 < 2 分鐘完成解析與輸出；CLASP push/run < 5 分鐘。  
- **可靠度**: 若任一 CSV 無有效題目需中止並顯示錯誤；生成結果應可重跑並產生相同 Form。  
- **可維護性**: Python 模組化（parser、renderer、cli），關鍵函式具 docstring 與 type hints；CI 執行 `pytest`。  
- **安全性**: 不將 OAuth token、Script ID 寫入 repo；`.clasp.json` 透過 `.gitignore` 控制。  
- **可觀測性**: CLI 需輸出 emoji 標示成功/失敗，並預留 hooks 寫入 log。

## 使用者故事

1. **作為** 題庫維運工程師，**我想要** 一次輸入多份 CSV，**以便** 在 10 分鐘內生成對應表單並通知講師測試。  
2. **作為** QA，**我想要** 查看 `form_generation_summary.json` 與 CLASP logs，**以便** 快速確認題數與警告。  
3. **作為** DevOps，**我想要** 透過 Spec Kit 文檔了解流程與風險，**以便** 納入 CI/CD 與版本控管。

## 邊界情況與錯誤處理

- 空 CSV 或僅有標題列：拋出 `ValueError` 並提示檔名。  
- 題幹中無 A-D 前綴：視為警告並跳過該題。  
- CLASP 尚未登入：腳本偵測 `clasp login` 失敗時提示執行批次腳本。  
- 重複表單名稱： Apps Script 預設會建立新表單，可考慮在未來加入時間戳或刪除舊表單的旗標。

## 主要流程

```
CSV (5 files)
   │ 1. python prepare/auto_generate_form
   ▼
Validated questions + warnings
   │ 2. render_gas()
   ▼
src/Code.gs + appsscript.json
   │ 3. clasp push --force
   ▼
Apps Script project
   │ 4. clasp run createFormFromCSV
   ▼
Google Forms + QA logs/report
```

## 資料模型

- **Question payload**: `{ year, number, title, optionA-D, answer }`。  
- **Summary report**: 包含 `csv_source`, `output_script`, `total_questions`, `stats: {total_rows, imported, skipped}`, `warnings[]`。  
- **Apps Script template**: `QUESTIONS` 陣列 + `createFormFromCSV` 函式。

## 整合需求

| 系統 | 用途 | 方法 | 認證 |
|------|------|------|------|
| Google Apps Script | 建表核心 | CLASP push/run / REST API | OAuth via `clasp login` |
| Google Drive | 驗證產出 | Apps Script `FormApp.create()` | 同上 |
| GitHub | 版本控管、Spec Kit | git push/PR | GitHub Flow |

## 假設與限制

- CSV 皆為 UTF-8，欄位順序可變但欄名須符合別名列表。  
- 操作人具備 Google Workspace 帳號與 Apps Script 權限。  
- 單份 CSV 題數 < 400（超過 400 需分批，避免 Form 限制）。  
- 預設建立 1 分題、四選一；不支援多選或非選擇題。

## 風險與緩解

| 風險 | 影響 | 機率 | 緩解 |
|------|------|------|------|
| CSV 格式突變 | High | Medium | 將 schema 與 mapping 拉到設定檔，並在報告中顯示未知欄位。 |
| CLASP quota 或登入失敗 | Medium | Medium | `快速使用_clasp` 腳本加入重試、清除 token 教學。 |
| 表單命名衝突 | Medium | Low | 允許 `--form-title-suffix` 或 QA 建立前刪舊表單。 |

## 測試策略

- **單元**: `_split_question_and_options`, `_detect_columns`, `render_gas`, `write_file`。  
- **整合**: 模擬 CLI，輸入樣本 CSV → 驗證輸出檔案與報告。  
- **端對端**: 在測試 Google 帳號執行 `clasp push/run`，確認表單 URL 與題數。  
- **效能**: 針對 500 題 CSV 量測執行時間與記憶體。

## 發布計畫

1. **v2.1 (現況)**: Spec Kit、CLI 文件、Apps Script 模板整合。  
2. **v2.2**: 自動檢測欄位別名表、QA 報表匯總。  
3. **v2.3**: 多環境（dev/prod scriptId）與 CI 驗證。

## 成功指標

- 5 份 CSV → 5 表單全自動成功率 ≥ 95%。  
- 新成員依 Spec Kit 文件上手時間 < 15 分鐘。  
- `form_generation_summary.json` 警告修復平均時間 < 30 分鐘。  
- 所有 PR 附有報告與 Form URL（審查清單通過率 100%）。

## 參考與附錄

- `README.md`, `QUICK_START.txt`, `google_forms_setup_guide.md`。  
- `auto_generate_form.py`, `prepare_for_google_forms.py`, CLASP 批次腳本。  
- `✅_檢查清單.txt`, `📊_完成報告.txt`。

---

**憲章符合性檢查**:
- [x] 符合所有 MUST 原則  
- [x] 已考慮所有 SHOULD 原則  
- [ ] 無需例外
