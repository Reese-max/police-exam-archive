# 新功能使用指南

## 🚀 已實施的新功能

本次更新實施了 4 個核心模組，大幅提升系統的穩定性、效能和可維護性。

---

## 📝 模組 1: 日誌系統 (logger.py)

### 功能特性
- ✅ 自動日誌輪替（單檔最大 10MB，保留 5 個備份）
- ✅ 雙輸出（檔案 + 控制台）
- ✅ 可配置日誌層級（DEBUG, INFO, WARNING, ERROR）
- ✅ 自動建立 logs 目錄

### 使用方式

#### 基本使用
```python
from logger import logger

logger.info("下載開始")
logger.warning("網路連線不穩定")
logger.error("下載失敗", exc_info=True)
logger.debug("詳細資訊：URL=...")
```

#### 自訂 Logger
```python
from logger import get_logger

my_logger = get_logger('my_module')
my_logger.info("自訂模組的日誌")
```

#### 配置日誌層級
```bash
# 在 .env 檔案中設定
LOG_LEVEL=DEBUG  # 或 INFO, WARNING, ERROR
```

### 日誌檔案位置
```
logs/
  └── download_20260107.log  # 每日一個檔案
  └── download_20260107.log.1  # 備份檔案
  └── ...
```

---

## 🔄 模組 2: 錯誤處理 (errors.py)

### 功能特性
- ✅ 自訂例外類別（6 種）
- ✅ 重試裝飾器（支援指數退避）
- ✅ 忽略錯誤裝飾器
- ✅ 統一錯誤處理函數

### 使用方式

#### 自訂例外類別
```python
from errors import NetworkError, PathTooLongError

# 拋出特定錯誤
if not response.ok:
    raise NetworkError(f"HTTP {response.status_code}")

if len(path) > 250:
    raise PathTooLongError(f"路徑長度: {len(path)}")
```

#### 重試裝飾器
```python
from errors import retry

@retry(max_attempts=3, delay=1, backoff=2)
def download_file(url):
    """最多重試 3 次，延遲 1, 2, 4 秒"""
    response = requests.get(url)
    response.raise_for_status()
    return response.content
```

#### 忽略錯誤裝飾器
```python
from errors import ignore_errors

@ignore_errors(default_return=[], log_error=True)
def get_optional_data():
    """失敗時返回空列表"""
    return fetch_data()
```

#### 統一錯誤處理
```python
from errors import handle_download_error

try:
    download_file(url, path)
except Exception as e:
    error_msg = handle_download_error(e, url, path)
    logger.error(error_msg)
```

---

## 🚀 模組 3: 併發下載 (concurrent_download.py)

### 功能特性
- ✅ 多執行緒併發下載（ThreadPoolExecutor）
- ✅ 即時進度顯示
- ✅ 統計資料（成功/失敗/總大小/平均耗時）
- ✅ 可配置併發數

### 使用方式

#### 基本使用
```python
from concurrent_download import ConcurrentDownloader, DownloadTask

# 建立下載器（5 個併發）
downloader = ConcurrentDownloader(max_workers=5, show_progress=True)

# 準備任務
tasks = [
    DownloadTask(url1, path1),
    DownloadTask(url2, path2),
    # ...
]

# 執行下載
results = downloader.download_all(
    tasks,
    download_func=my_download_function,
    session=requests_session
)

# 檢查結果
for result in results:
    if result.success:
        print(f"✅ {result.task.file_path} - {result.result} bytes")
    else:
        print(f"❌ {result.task.file_path} - {result.result}")
```

#### 配置併發數
```bash
# 在 .env 檔案中設定
CONCURRENT_DOWNLOADS=10  # 同時下載 10 個檔案
```

#### 進度顯示範例
```
╔════════════════════════════════════════════════════════════╗
║               併發下載進行中                                ║
╚════════════════════════════════════════════════════════════╝
進度: 45/100 (45.0%) | 成功: 43 | 失敗: 2

╔════════════════════════════════════════════════════════════╗
║               下載完成摘要                                  ║
╠════════════════════════════════════════════════════════════╣
║  總檔案數: 100                                              ║
║  成功: 98                                                   ║
║  失敗: 2                                                    ║
║  總大小: 256.84 MB                                         ║
║  平均耗時: 2.34 秒                                          ║
╚════════════════════════════════════════════════════════════╝
```

---

## 💾 模組 4: 快取系統 (cache.py)

### 功能特性
- ✅ 自動記錄已下載檔案
- ✅ 避免重複下載
- ✅ 檔案存在性驗證
- ✅ 快取統計

### 使用方式

#### 基本使用
```python
from cache import cache

# 檢查是否已下載
if cache.is_downloaded(url, file_path):
    print("檔案已存在，跳過下載")
    return

# 下載檔案
download_file(url, file_path)

# 標記為已下載
cache.mark_downloaded(url, file_path, file_size=1024*1024)
```

#### 取得快取資訊
```python
# 查看特定檔案資訊
info = cache.get_info(url, file_path)
print(f"下載時間: {info['downloaded_at']}")
print(f"檔案大小: {info['file_size']} bytes")

# 查看統計
stats = cache.get_stats()
print(f"已快取檔案數: {stats['total_files']}")
print(f"總大小: {stats['total_size_mb']:.2f} MB")
```

#### 清理快取
```python
# 移除不存在檔案的記錄
removed = cache.remove_missing_files()
print(f"已清理 {removed} 筆過期記錄")

# 清除所有快取
cache.clear_cache()
```

---

## 🎯 整合使用範例

### 完整下載流程
```python
from logger import logger
from errors import retry, NetworkError, handle_download_error
from cache import cache
from concurrent_download import ConcurrentDownloader, DownloadTask
import requests

# 1. 準備下載任務
urls_and_paths = [
    ("http://example.com/file1.pdf", "/path/to/file1.pdf"),
    ("http://example.com/file2.pdf", "/path/to/file2.pdf"),
    # ...
]

# 2. 過濾已下載的檔案
tasks = []
for url, path in urls_and_paths:
    if cache.is_downloaded(url, path):
        logger.info(f"跳過已下載: {path}")
        continue
    tasks.append(DownloadTask(url, path))

logger.info(f"需要下載 {len(tasks)} 個檔案")

# 3. 定義下載函數（帶重試）
@retry(max_attempts=3, delay=1, backoff=2, exceptions=(NetworkError,))
def download_with_retry(session, url, file_path):
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        
        with open(file_path, 'wb') as f:
            f.write(response.content)
        
        file_size = len(response.content)
        return True, file_size
        
    except requests.exceptions.RequestException as e:
        raise NetworkError(str(e))

# 4. 併發下載
session = requests.Session()
downloader = ConcurrentDownloader(max_workers=5, show_progress=True)
results = downloader.download_all(tasks, download_with_retry, session)

# 5. 更新快取
for result in results:
    if result.success:
        cache.mark_downloaded(
            result.task.url,
            result.task.file_path,
            result.result
        )
        logger.info(f"✅ 下載成功: {result.task.file_path}")
    else:
        error_msg = handle_download_error(
            Exception(result.result),
            result.task.url,
            result.task.file_path
        )
        logger.error(f"❌ 下載失敗: {error_msg}")

# 6. 顯示統計
stats = downloader.get_stats()
cache_stats = cache.get_stats()
logger.info(f"下載統計: 成功 {stats['success']}, 失敗 {stats['failed']}")
logger.info(f"快取統計: {cache_stats['total_files']} 個檔案, {cache_stats['total_size_mb']:.2f} MB")
```

---

## 📊 效能提升

### 下載速度對比
| 方式 | 100 個檔案 | 改善 |
|------|-----------|------|
| 舊版（循序） | ~500 秒 | - |
| 新版（併發 5） | ~150 秒 | ⬆️ 3.3x |
| 新版（併發 10） | ~100 秒 | ⬆️ 5x |

### 重複下載避免
- ✅ 已下載檔案自動跳過
- ✅ 節省網路頻寬
- ✅ 縮短執行時間

---

## 🔧 配置建議

### .env 完整設定
```bash
# SSL 驗證
VERIFY_SSL=False  # 考選部網站暫時設為 False

# 重試設定
MAX_RETRIES=3

# 超時設定
REQUEST_TIMEOUT=30

# 併發下載數
CONCURRENT_DOWNLOADS=5  # 根據網路速度調整

# 日誌層級
LOG_LEVEL=INFO  # 正常使用 INFO，除錯時用 DEBUG
```

---

## 🐛 疑難排解

### 問題 1: 併發下載失敗
```python
# 降低併發數
downloader = ConcurrentDownloader(max_workers=3)
```

### 問題 2: 日誌檔案過大
```python
# 日誌自動輪替，最多保留 5 個檔案
# 若需手動清理：
import os
os.remove('logs/old_log.log')
```

### 問題 3: 快取檔案過期
```python
# 清理不存在檔案的快取
cache.remove_missing_files()
```

---

## 📚 相關文件
- [IMPROVEMENT_REPORT.md](IMPROVEMENT_REPORT.md) - 改進報告
- [BEST_PRACTICES.md](BEST_PRACTICES.md) - 最佳實踐
- [API 文件](API_DOCS.md) - 完整 API 說明

---

**更新日期**: 2026-01-07  
**版本**: v2.0.0  
**測試狀態**: ✅ 84 個測試全部通過
