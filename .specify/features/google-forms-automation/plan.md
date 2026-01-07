# 實作計劃: CSV → Google Forms 自動部署

> **基於規格**: `.specify/features/google-forms-automation/spec.md` v1.0  
> **建立日期**: 2025-11-26  
> **最後更新**: 2025-11-27  
> **狀態**: ✅ Completed

## 執行摘要

- **目標**: 以 Python CLI + CLASP 建立一鍵部署管線，並提供完整報告/QA/文件，使 Vibe Coding 流程具備可觀測性與重現性。  
- **里程碑**:
  1. ✅ **M1 - 資料層完成** (D+2)：CSV 驗證、parser、報告結構就緒。  
  2. ✅ **M2 - 生成/部署** (D+4)：Apps Script renderer、CLASP push/run 自動化。  
  3. ✅ **M3 - 可觀測/交付** (D+6)：報告、QA 清單、文檔與 Spec Kit 校對。  
  4. ✅ **M4 - 智能自動化** (D+7)：一鍵部署系統、表單驗證模組、Web App。

## 完成項目 (2025-11-27)

### 新增功能
- ✅ `smart_deploy.py` - 智能自動化部署系統
- ✅ `一鍵部署.bat` - 雙擊啟動的 Windows 批次檔
- ✅ `FormValidator.gs` - 表單自動驗證模組
- ✅ Web App 部署 - 可透過 URL 觸發驗證
- ✅ GCP 整合 - 連結 Google Cloud Project，啟用 clasp logs

### 驗證函數
- `validateAllForms()` - 驗證所有警察考古題表單
- `listAllForms()` - 列出所有表單及其 URL
- `quickTest()` - 快速測試 Drive API 連線

### 設定完成
- ✅ `.clasp.json` 加入 `projectId: gen-lang-client-0582954071`
- ✅ GCP OAuth 同意畫面設定完成
- ✅ Google Drive API 已啟用
- ✅ Google Forms API 已啟用
- ✅ 測試使用者已加入

## 技術架構

```
┌───────────┐    parse/validate    ┌──────────────┐    render/write    ┌────────────┐
│ CSV files │ ───────────────────▶ │ Python layer │ ─────────────────▶ │ Code.gs    │
└───────────┘    report warnings   │ (auto_generate_form.py)           │ appsscript │
                                   └──────────────┘                    └────────────┘
                                         │                                   │
                                         ▼                                   ▼
                                  form_generation_summary.json       CLASP push/run
                                         │                                   │
                                         ▼                                   ▼
                                   QA checklist / Logs               Google Form(s)
                                         │                                   │
                                         ▼                                   ▼
                                  ┌──────────────┐                  ┌─────────────────┐
                                  │smart_deploy.py│ ◄──────────────▶│FormValidator.gs │
                                  │ 一鍵部署系統  │                  │ 自動驗證模組    │
                                  └──────────────┘                  └─────────────────┘
```

### 架構決策

1. **單一 Python CLI** vs 多腳本：集中在 `auto_generate_form.py`，利於維護，透過子函式拆模組。  
2. **Apps Script 直接內嵌題庫** vs Google Sheets：採內嵌 JSON，省略 Sheets 欄位同步並降低權限需求。  
3. **CLASP** vs Google Apps Script API：CLASP 可直接推送/執行與取得 logs，符合自動化原則。
4. **智能半自動化** vs 全自動化：因 Google OAuth 限制，採用半自動化方式，自動完成可自動化的部分，需點擊的部分開啟瀏覽器引導。

## 技術棧

- **Python**: 3.10+，模組分為 parser、renderer、reporter、cli。  
- **Node & CLASP**: Node 18 LTS + `@google/clasp` 全域安裝。  
- **Apps Script**: 使用 `FormApp` API 建表，`DriveApp` API 驗證。
- **GCP**: Google Cloud Project `gen-lang-client-0582954071`
- **測試/工具**: `pytest`, `ruff` (可選)。  
- **文件**: Spec Kit、README、Quick Start。

## 檔案清單

| 檔案 | 用途 |
|------|------|
| `一鍵部署.bat` | 雙擊啟動智能部署系統 |
| `smart_deploy.py` | 智能自動化部署腳本 |
| `auto_generate_form.py` | CSV 解析 + Apps Script 產生 |
| `src/Code.gs` | 主要 Apps Script (表單建立) |
| `src/FormValidator.gs` | 表單驗證模組 |
| `src/appsscript.json` | GAS 專案設定 (含 OAuth scopes) |
| `.clasp.json` | CLASP 設定 (含 GCP projectId) |
| `form_generation_summary_*.json` | 各年度匯入報告 |
| `QA_Report_*.txt` | QA 驗證報告 |
| `QA_Checklist.txt` | QA 檢查清單範本 |

## 使用流程

### 一鍵部署
```
雙擊「一鍵部署.bat」→ 選擇 [1] 完整部署 → 依提示操作
```

### 手動部署
```bash
python auto_generate_form.py --csv "題庫.csv"
clasp push --force
# 在瀏覽器執行 createFormFromCSV
# 在瀏覽器執行 validateAllForms
```

## 里程碑與交付

| 里程碑 | 內容 | 狀態 | 完成日期 |
|--------|------|------|----------|
| M1 - Parser & Report | CSV 驗證、報告 schema | ✅ 完成 | 11/26 |
| M2 - Renderer & Deploy | Apps Script 模板、CLASP push/run | ✅ 完成 | 11/26 |
| M3 - QA toolchain | QA 清單、文檔更新 | ✅ 完成 | 11/27 |
| M4 - 智能自動化 | 一鍵部署、表單驗證、Web App | ✅ 完成 | 11/27 |

## 測試與品質

- ✅ **手動測試**: 完整流程已驗證
- ✅ **表單驗證**: `validateAllForms` 可自動檢查所有表單
- ✅ **日誌擷取**: `clasp logs --json` 正常運作
- ✅ **QA 報告**: 自動產生 `QA_Report_*.txt`

## 文件與交付

- ✅ `README.md` - 更新為 v3.0，包含智能自動化說明
- ✅ `QUICK_START.txt` - 快速開始指南
- ✅ `QA_Checklist.txt` - QA 檢查清單範本
- ✅ `.specify/` - Spec Kit 文件

---

**憲章符合性**  
- [x] 自動化優先  
- [x] CSV 為單一真實來源  
- [x] 可觀測與可回溯  
- [x] 安全/權限最佳化
