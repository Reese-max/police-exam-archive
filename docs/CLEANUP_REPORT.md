# 專案清理與整理報告

## 🔍 掃描結果

### 可安全刪除的檔案/目錄

#### 1. 臨時檔案
- `_tmp_template_check.py` - 臨時測試檔案

#### 2. Python 快取檔案
- `__pycache__/` (根目錄)
- `tests/__pycache__/`
- `考選部考古題完整庫/__pycache__/`

#### 3. pytest 快取
- `.pytest_cache/` - pytest 測試快取

#### 4. 備份檔案
- `backup/Code_69_backup.gs` (45 KB)
- `backup/Code_98.gs` (70 KB)

#### 5. HTML 涵蓋率報告
- `htmlcov/` (22 個檔案，約 1 MB)
  - 可隨時重新生成

#### 6. 日誌檔案
- `logs/download_20260108.log` (測試日誌)

---

## 🗑️ 刪除計劃

### 立即刪除（不影響功能）
- ✅ `_tmp_template_check.py`
- ✅ `__pycache__/` (所有)
- ✅ `.pytest_cache/`
- ✅ `logs/` (測試日誌)

### 可選刪除（保留或刪除）
- ⚠️ `backup/` - 舊版備份檔案
- ⚠️ `htmlcov/` - 涵蓋率報告（可重新生成）

### 保留（不刪除）
- ✅ `.specify/` - 專案規格文件
- ✅ `src/` - Apps Script 原始碼
- ✅ `.github/workflows/` - CI/CD 配置
- ✅ 所有 .md 文件
- ✅ 所有 .py 主程式

---

## 📁 建議的資料夾結構

```
考古題下載/
├── 📝 文件
│   ├── README.md (主說明)
│   ├── docs/ (所有文件)
│   │   ├── BUG_FIX_REPORT.md
│   │   ├── IMPROVEMENT_REPORT.md
│   │   ├── BEST_PRACTICES.md
│   │   ├── IMPLEMENTATION_REPORT.md
│   │   ├── NEW_FEATURES_GUIDE.md
│   │   ├── COVERAGE_REPORT.md
│   │   ├── CI_CD_GUIDE.md
│   │   └── TEST_REPORT.md
│
├── 🐍 主程式
│   ├── 考古題下載.py
│   ├── auto_generate_form.py
│   ├── smart_deploy.py
│   └── 一鍵部署.bat
│
├── 🛠️ 模組
│   ├── logger.py
│   ├── errors.py
│   ├── concurrent_download.py
│   ├── cache.py
│   └── config.py
│
├── 🧪 測試
│   └── tests/
│       ├── test_cli.py
│       ├── test_download_*.py
│       ├── test_new_features.py
│       └── ...
│
├── ⚙️ 配置
│   ├── .env.example
│   ├── pyproject.toml
│   ├── requirements.txt
│   └── .gitignore
│
├── 🚀 CI/CD
│   └── .github/workflows/ci.yml
│
├── 📦 Apps Script
│   └── src/
│       ├── Code.gs
│       ├── FormValidator.gs
│       └── appsscript.json
│
└── 🗄️ 資料 (gitignore)
    ├── logs/ (執行日誌)
    ├── 考選部考古題完整庫/ (下載檔案)
    └── .download_cache.json (快取)
```

---

## 🎯 執行清理

