# Google Form Deployment Toolkit

本專案專注於「將結構化 CSV 題庫快速部署到 Google Forms」，提供一鍵自動化部署系統。你只需要準備好題目 CSV 檔案，執行智能部署腳本即可自動建立可作答、可評分的 Google 表單。

---

## 🎯 功能特色

- **🚀 一鍵部署系統**：雙擊 `一鍵部署.bat` 即可啟動智能自動化流程
- **CSV → Google Form 自動部署**：解析題目與選項欄位，產生 Google Apps Script
- **自動驗證表單**：內建 `validateAllForms` 函數，自動檢查所有表單狀態
- **欄位驗證與匯入報告**：輸出 `form_generation_summary.json`，記錄成功/跳過列數及警告訊息
- **QA 報告自動生成**：產生完整的 QA 驗證報告，可直接附於 Pull Request

---

## 🚀 快速開始（推薦）

### 方法一：智能自動化系統

1. **雙擊執行** `一鍵部署.bat`

2. **選擇功能**：
   ```
   ╔══════════════════════════════════════════════════════════════╗
   ║         警察考古題表單 - 智能自動化部署系統                  ║
   ╠══════════════════════════════════════════════════════════════╣
   ║  [1] 完整部署 (CSV → 表單 → 驗證)                            ║
   ║  [2] 只驗證現有表單                                          ║
   ║  [3] 只推送程式碼                                            ║
   ║  [4] 查看表單清單                                            ║
   ║  [5] 擷取 CLASP 日誌                                         ║
   ║  [Q] 退出                                                    ║
   ╚══════════════════════════════════════════════════════════════╝
   ```

3. **輸入 `1` 進行完整部署**，系統會自動：
   - 掃描並選擇 CSV 檔案
   - 生成 Apps Script 程式碼
   - 推送到 Google
   - 開啟瀏覽器執行表單建立
   - 開啟驗證頁面
   - 產生 QA 報告

---

## 📦 專案結構

```
.
├── 一鍵部署.bat               # 雙擊啟動智能部署系統
├── smart_deploy.py            # 智能自動化部署腳本
├── auto_generate_form.py      # CSV 解析 + Apps Script 產生
├── src/
│   ├── Code.gs                # 主要 Apps Script (表單建立)
│   ├── FormValidator.gs       # 表單驗證模組
│   └── appsscript.json        # GAS 專案設定
├── .clasp.json                # CLASP 設定 (含 GCP projectId)
├── form_generation_summary_*.json  # 各年度匯入報告
├── QA_Report_*.txt            # QA 驗證報告
└── 考選部考古題完整庫/        # CSV 題庫檔案
```

### 部署管線選擇
- **主要管線（推薦）**：使用根目錄 `.clasp.json` + `src/Code.gs`、`FormValidator.gs`（scriptId `1-m81BHKdUIZfAdHkRGCRXfRFI_e79ieKgppZqvj4rVOIztAM-O3GKUJQ`）。`一鍵部署.bat`、`smart_deploy.py`、`clasp run validateAllForms` 都走這條。
- **備用/舊管線**：`考選部考古題完整庫/情境實務考古題/.clasp.json` 指向舊專案，僅在需要維護歷史表單時使用。避免在子資料夾執行 `clasp push/run` 以免推錯環境。

---

## 📋 需求與環境

| 元件 | 說明 |
|------|------|
| Python 3.9+ | 執行自動化腳本 |
| Node.js & npm | CLASP 依賴 |
| CLASP | `npm install -g @google/clasp` |
| Python 套件 | `pip install -r requirements.txt`（僅需標準函式庫＋pytest 測試） |
| Google 帳號 | 具備 Apps Script 權限 |

安裝指令（Windows/macOS/Linux）：
```bash
pip install -r requirements.txt
npm install -g @google/clasp
```
> Python 腳本的執行不依賴第三方套件，`requirements.txt` 只為測試而準備；若只跑部署流程可略過 pytest。

### 首次設定

1. **登入 CLASP**：
   ```bash
   clasp login
   ```

2. **確認 GCP 專案已連結**：
   - 開啟 [Apps Script 編輯器](https://script.google.com)
   - 專案設定 → Google Cloud Platform 專案 → 確認已連結

3. **啟用必要 API**（在 GCP Console）：
   - Google Drive API
   - Google Forms API

---

## 🧾 CSV 格式

最少需要以下欄位（支援中英文欄名）：

| 欄位 | 說明 |
|------|------|
| `年份` / `Year` | 題目年份或分類 |
| `試題編號` / `Number` | 題號 |
| `題目` / `Title` | 題幹 |
| `選項A~D` | 四個選擇題選項 |
| `標準答案` / `Answer` | A/B/C/D |

檔案必須使用 **UTF-8** 編碼。

---

## ⚙️ 手動執行方式

如果需要手動控制，可以使用以下命令：

### 生成 Apps Script
```bash
python auto_generate_form.py --csv "題庫.csv" --form-title "考試練習"
```

### 推送到 Google
```bash
clasp push --force
```

### 在 Apps Script 編輯器執行
1. 開啟 [Apps Script 編輯器](https://script.google.com)
2. 選擇函數 `createFormFromCSV`
3. 點擊 ▶️ 執行

### 驗證表單
1. 選擇函數 `validateAllForms`
2. 點擊 ▶️ 執行
3. 查看執行記錄

### 擷取日誌
```bash
clasp logs --json
```

---

## 📊 匯入報告

每次執行會產生 `form_generation_summary_*.json`：

```json
{
  "csv_source": "113年警察人員三等考試.csv",
  "output_script": "src/Code.gs",
  "total_questions": 20,
  "stats": {
    "total_rows": 20,
    "imported": 20,
    "skipped": 0
  },
  "warnings": [
    "第 8 行答案格式不正確（C,D），已預設為 A"
  ]
}
```

---

## ✅ QA 驗證清單

執行 `validateAllForms` 後會顯示：

```
========================================
       驗證結果
========================================
總數: 5
通過: 5
失敗: 0
1. [OK] 110年警察人員三等考試 (19題)
   https://docs.google.com/forms/d/xxx/edit
2. [OK] 111年警察人員三等考試 (20題)
   https://docs.google.com/forms/d/xxx/edit
...
```

---

## 🔧 常見問題

| 問題 | 解決方式 |
|------|----------|
| `clasp push` 失敗 | 執行 `clasp login` 重新登入 |
| `validateAllForms` 出錯 | 確認已在 GCP 啟用 Drive API 和 Forms API |
| 表單沒有選項 | 檢查 CSV 的選項欄位是否為空 |
| 403 access_denied | 在 GCP OAuth 同意畫面加入測試使用者 |

---

## 📚 相關文件

- `.specify/features/google-forms-automation/spec.md` - 功能規格
- `.specify/features/google-forms-automation/plan.md` - 實作計劃
- `QA_Checklist.txt` - QA 檢查清單範本

---

## 📝 版本歷程

| 日期 | 版本 | 重點 |
|------|------|------|
| 2025-11-27 | 3.0 | 新增智能自動化系統、表單驗證模組、Web App |
| 2025-11-26 | 2.1 | 新增 GitHub Spec Kit、QA 報告 |
| 2025-11-24 | 2.0 | 專案聚焦 CSV→Google Form |

---

## 🤝 貢獻

歡迎提交 Issue / PR！
