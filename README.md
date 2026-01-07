# 考古題下載專案 - 完整功能說明

## 🎯 專案核心功能

這是一個**雙功能整合系統**，專為警察特考考生設計：

### 功能 1: 考古題自動下載器 📥
從考選部網站批次下載歷年考古題 PDF 檔案

### 功能 2: Google Forms 自動部署工具 📝
將考古題 CSV 轉換為線上練習表單

---

## 📥 功能 1: 考古題自動下載

### 主程式
**檔案**: `考古題下載.py`

### 核心功能
1. **自動掃描考選部網站**
   - 連接 https://wwwq.moex.gov.tw/exam/
   - 掃描民國 81 年至今的所有考試

2. **智能篩選**
   - 關鍵字篩選（預設: "警察"）
   - 自動識別警察特考相關考試
   - 支援自訂篩選條件

3. **自動分類下載**
   ```
   考選部考古題完整庫/
   ├── 民國113年/
   │   ├── 民國113年_警察特考/
   │   │   ├── 三等_刑事警察人員/
   │   │   │   ├── 刑法與刑事訴訟法.pdf
   │   │   │   ├── 犯罪偵查學.pdf
   │   │   │   └── ...
   │   │   └── 四等_行政警察人員/
   │   │       └── ...
   │   └── ...
   └── ...
   ```

4. **進階功能**
   - 重試機制（網路異常自動重試）
   - 路徑長度檢查（避免 Windows 路徑限制）
   - 檔案驗證（檢查 PDF 完整性）
   - 進度追蹤與統計

### 使用方式
```bash
python 考古題下載.py
```

### 互動流程
```
1. 選擇儲存資料夾
2. 選擇年份範圍（單一年份或連續範圍）
3. 設定篩選關鍵字（預設: 警察）
4. 確認設定
5. 自動下載並分類
```

### 實際範例
```
🚀 開始下載
======================================================================
🔍 正在掃描民國 113 年的考試...
   ✓ 找到 3 場考試

📋 民國 113 年 - 警察人員考試、一般警察人員考試
======================================================================
   📊 類科: 2 個 | 科目: 15 個 | 檔案: 30 個
   
   [三等_刑事警察人員]
      ✓ 刑法與刑事訴訟法.pdf (2.5 MB)
      ✓ 犯罪偵查學.pdf (1.8 MB)
      ...
   
   ✅ 完成: 30/30 個檔案
```

---

## 📝 功能 2: Google Forms 自動部署

### 主程式
**檔案**: `auto_generate_form.py` + `smart_deploy.py`

### 工作流程

#### 步驟 1: 準備 CSV 題庫
```csv
year,number,title,option_a,option_b,option_c,option_d,answer
113,1,"某警員處理家暴案件時...","報案人同意","當事人同意","現行犯逮捕","取得搜索票",C
113,2,"關於警械使用規定...","口頭警告","鳴槍示警","瞄準射擊","直接射擊",B
```

#### 步驟 2: 生成 Google Apps Script
```bash
python auto_generate_form.py questions.csv
```

**輸出**: `src/Code.gs`
```javascript
const QUESTIONS = [
  {
    year: 113,
    number: 1,
    title: "某警員處理家暴案件時...",
    options: ["報案人同意", "當事人同意", "現行犯逮捕", "取得搜索票"],
    answer: "C"
  },
  // ...
];
```

#### 步驟 3: 智能部署
**方式 1**: 一鍵部署
```bash
一鍵部署.bat
```

**方式 2**: 手動部署
```bash
python smart_deploy.py
```

### 部署選單
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

#### 步驟 4: 自動生成 Google Form
部署後，系統會：
1. 推送 Code.gs 至 Google Apps Script
2. 自動開啟瀏覽器
3. 點擊「部署」按鈕
4. 執行 `createFormFromCSV()` 函數
5. 自動建立 Google Form

### 最終成果
**Google Form 特色**:
- ✅ 自動評分
- ✅ 單選題（A/B/C/D）
- ✅ 答案驗證
- ✅ 成績統計
- ✅ 即時練習

---

## 🛠️ 新功能模組 (v2.0)

### 1. 日誌系統 (`logger.py`)
```python
from logger import logger

logger.info("開始下載考古題")
logger.warning("網路連線不穩定")
logger.error("下載失敗", exc_info=True)
```

**功能**:
- 自動日誌輪替（10MB/檔案）
- 雙輸出（檔案 + 控制台）
- 可配置層級

### 2. 錯誤處理 (`errors.py`)
```python
from errors import retry, NetworkError

@retry(max_attempts=3, delay=1, backoff=2)
def download_with_retry(url):
    # 自動重試 3 次
    return requests.get(url)
```

**功能**:
- 6 種自訂例外
- 重試裝飾器（指數退避）
- 統一錯誤處理

### 3. 併發下載 (`concurrent_download.py`)
```python
from concurrent_download import ConcurrentDownloader

downloader = ConcurrentDownloader(max_workers=5)
results = downloader.download_all(tasks, download_func, session)
```

**功能**:
- 多執行緒下載（3-5x 速度）
- 即時進度顯示
- 統計報告

### 4. 快取系統 (`cache.py`)
```python
from cache import cache

if not cache.is_downloaded(url, path):
    download_file(url, path)
    cache.mark_downloaded(url, path, size)
```

**功能**:
- 避免重複下載
- 自動快取管理
- 檔案驗證

---

## 📊 使用場景

### 場景 1: 準備警察特考
```bash
# 下載近 5 年考古題
python 考古題下載.py
# 選擇: 109-113 年
# 篩選: 警察
# 結果: ~500 個 PDF 檔案
```

### 場景 2: 建立線上練習
```bash
# 1. 準備題庫
# 建立 113年警察特考.csv

# 2. 生成表單
python auto_generate_form.py 113年警察特考.csv

# 3. 部署
一鍵部署.bat

# 4. 練習
# 開啟 Google Form 連結開始作答
```

### 場景 3: 大量批次下載
```python
from concurrent_download import ConcurrentDownloader
from cache import cache

# 使用併發下載 + 快取
downloader = ConcurrentDownloader(max_workers=10)
# 下載速度提升 5 倍
```

---

## 🎯 目標使用者

### 主要使用者
- **警察特考考生** - 下載歷年考古題
- **補習班老師** - 建立線上測驗系統
- **自修學生** - 整理題庫練習

### 次要使用者
- **考試研究者** - 分析考題趨勢
- **教材編輯者** - 整理考古題資料

---

## 💡 實際使用案例

### 案例 1: 準備 114 年警察特考
```
目標: 下載 109-113 年（近 5 年）考古題
步驟:
  1. 執行 python 考古題下載.py
  2. 選擇年份範圍: 109-113
  3. 篩選關鍵字: 警察
  4. 等待約 10-20 分鐘
結果:
  - 下載 ~500 個 PDF 檔案
  - 按年份、考試、類科、科目分類
  - 總大小約 2-3 GB
```

### 案例 2: 建立情境實務線上測驗
```
目標: 將 113 年情境實務 100 題轉為線上測驗
步驟:
  1. 準備 CSV 題庫（100 題）
  2. 執行 python auto_generate_form.py 題庫.csv
  3. 執行 一鍵部署.bat
  4. 點擊瀏覽器「部署」按鈕
  5. 分享 Google Form 連結給同學
結果:
  - 自動建立 100 題線上測驗
  - 自動評分
  - 可重複練習
```

---

## 📈 效能表現

### 下載速度
| 模式 | 100 檔案 | 500 檔案 |
|------|---------|---------|
| 舊版（循序） | ~500 秒 | ~2500 秒 |
| v2.0（併發5） | ~150 秒 | ~750 秒 |
| v2.0（併發10） | ~100 秒 | ~500 秒 |

### 表單生成
| 題目數 | 生成時間 | 部署時間 |
|--------|---------|---------|
| 50 題 | ~2 秒 | ~30 秒 |
| 100 題 | ~4 秒 | ~60 秒 |
| 500 題 | ~20 秒 | ~300 秒 |

---

## 🔧 技術架構

### 下載器架構
```
考古題下載.py
  ├─ 掃描考選部網站 (BeautifulSoup)
  ├─ 解析考試結構 (正則表達式)
  ├─ 併發下載 (ThreadPoolExecutor)
  ├─ 快取管理 (JSON)
  └─ 日誌記錄 (logging)
```

### 表單部署架構
```
CSV 題庫
  ↓
auto_generate_form.py
  ↓
Code.gs (Google Apps Script)
  ↓
CLASP (推送至雲端)
  ↓
Google Apps Script (執行)
  ↓
Google Form (自動建立)
```

---

## ✅ 系統需求

### 考古題下載
- Python 3.10+
- 網路連線
- 2-10 GB 硬碟空間

### 表單部署
- Python 3.10+
- Node.js (CLASP)
- Google 帳號
- Google Apps Script 權限

---

## 📚 完整文件索引

詳細文件請參閱 `docs/` 資料夾：

- [新功能使用指南](docs/NEW_FEATURES_GUIDE.md) - v2.0 新功能
- [測試報告](docs/TEST_REPORT.md) - 84 個測試
- [改進報告](docs/IMPROVEMENT_REPORT.md) - 安全性提升
- [最佳實踐](docs/BEST_PRACTICES.md) - 開發建議
- [CI/CD 指南](docs/CI_CD_GUIDE.md) - 部署流程

---

**更新日期**: 2026-01-07  
**版本**: v2.0.0  
**維護狀態**: ✅ 積極維護中
