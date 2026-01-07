# 考古題下載專案 - 改進建議與最佳實踐

## 🎯 已實施的改進

### 1. 安全性加固 ✅

#### 修正 Shell Injection 漏洞
**問題**: `os.system()` 和 `subprocess.run(shell=True)` 容易遭受命令注入攻擊

**修正前**:
```python
os.system('cls' if os.name == 'nt' else 'clear')  # 🔴 危險
subprocess.run(cmd, shell=True, ...)  # 🔴 危險
```

**修正後**:
```python
# 安全版本
if os.name == 'nt':
    subprocess.run(['cmd', '/c', 'cls'], check=False)  # ✅ 安全
else:
    subprocess.run(['clear'], check=False)  # ✅ 安全

# 使用 shlex 安全分割命令
import shlex
cmd_list = shlex.split(cmd)
subprocess.run(cmd_list, shell=False, ...)  # ✅ 安全
```

**影響**: 
- Bandit 高嚴重度問題: 2 → 0
- 防止命令注入攻擊
- 符合 OWASP 安全標準

---

### 2. 配置管理系統 ✅

#### 新增環境變數支援
**新增檔案**:
- `.env.example` - 環境變數範本
- `config.py` - 配置管理模組

**功能**:
```python
from config import config

# 可配置的設定
config.verify_ssl  # SSL 驗證（預設 False，可改 True）
config.max_retries  # 重試次數（預設 3）
config.request_timeout  # 超時時間（預設 30 秒）
config.concurrent_downloads  # 併發數（預設 5）
config.log_level  # 日誌層級（預設 INFO）
```

**優勢**:
- 靈活的配置管理
- 支援不同環境（開發/測試/生產）
- 不需修改程式碼即可調整行為

---

## 🔄 建議的後續改進

### 3. 程式碼重構（降低複雜度）

#### 高複雜度函數清單
| 函數 | 位置 | 複雜度 | 建議 |
|------|------|--------|------|
| `download_exam()` | 考古題下載.py:602 | E (37) | 🔴 拆分為 3-5 個子函數 |
| `load_questions()` | auto_generate_form.py:242 | E (35) | 🔴 拆分為多個子函數 |
| `parse_exam_page()` | 考古題下載.py:335 | D (21) | 🟡 重構內嵌函數 |
| `get_year_input()` | 考古題下載.py:106 | C (18) | 🟡 簡化輸入驗證邏輯 |

#### 重構範例: download_exam()

**重構前** (37 行複雜度):
```python
def download_exam(...):  # 200+ 行
    # 獲取考試資料
    # 解析結構
    # 建立資料夾
    # 下載檔案
    # 更新統計
    # 錯誤處理
    ...
```

**重構後**:
```python
def download_exam(...):
    exam_data = fetch_exam_data(...)
    structure = parse_structure(exam_data)
    folders = create_folder_structure(structure)
    results = download_files(structure, folders)
    update_statistics(results, stats)

def fetch_exam_data(...):  # 單一職責
    ...

def parse_structure(...):  # 單一職責
    ...

def create_folder_structure(...):  # 單一職責
    ...

def download_files(...):  # 單一職責
    ...
```

**預期改善**: E (37) → B (6)

---

### 4. 效能優化

#### 4.1 併發下載
**現狀**: 循序下載，速度慢
```python
# 現在
for file in files:
    download_file(file)  # 一次一個
```

**建議**: 使用 ThreadPoolExecutor 併發下載
```python
# 建議
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=5) as executor:
    executor.map(download_file, files)  # 同時下載 5 個
```

**預期提升**: 下載速度提升 3-5 倍

#### 4.2 快取機制
**建議**: 快取已下載的檔案清單
```python
import json

def load_cache():
    if os.path.exists('.download_cache.json'):
        with open('.download_cache.json') as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open('.download_cache.json', 'w') as f:
        json.dump(cache, f)

# 跳過已下載的檔案
if file_path in cache:
    print(f"跳過已下載: {file_path}")
    continue
```

---

### 5. 日誌系統

#### 新增結構化日誌
**建議**: 使用 Python logging 模組
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('download.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# 使用
logger.info(f"開始下載: {file_name}")
logger.error(f"下載失敗: {error}")
logger.debug(f"詳細資訊: {details}")
```

---

### 6. 錯誤處理強化

#### 6.1 自訂例外類別
```python
class DownloadError(Exception):
    """下載錯誤基礎類別"""
    pass

class NetworkError(DownloadError):
    """網路錯誤"""
    pass

class PathTooLongError(DownloadError):
    """路徑過長錯誤"""
    pass

# 使用
try:
    download_file(url)
except NetworkError as e:
    logger.error(f"網路錯誤: {e}")
    retry_download(url)
except PathTooLongError as e:
    logger.warning(f"路徑過長: {e}")
    shorten_path(path)
```

#### 6.2 重試裝飾器
```python
def retry(max_attempts=3, delay=1):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(delay * (2 ** attempt))
        return wrapper
    return decorator

@retry(max_attempts=3)
def download_file(url):
    ...
```

---

### 7. 文件完善

#### 7.1 API 文件（Docstrings）
```python
def download_file(session, url, file_path, max_retries=5):
    """下載檔案至指定路徑

    Args:
        session (requests.Session): HTTP session 物件
        url (str): 檔案下載 URL
        file_path (str): 本地儲存路徑
        max_retries (int, optional): 最大重試次數. Defaults to 5.

    Returns:
        tuple[bool, Union[int, str]]: (成功與否, 檔案大小或錯誤訊息)

    Raises:
        NetworkError: 網路連線失敗
        PathTooLongError: 路徑超過系統限制

    Example:
        >>> session = requests.Session()
        >>> success, size = download_file(session, "http://...", "test.pdf")
        >>> if success:
        ...     print(f"下載成功，大小: {size} bytes")
    """
    ...
```

#### 7.2 使用者文件
- [ ] 新增 CONTRIBUTING.md（貢獻指南）
- [ ] 新增 CHANGELOG.md（變更日誌）
- [ ] 新增 FAQ.md（常見問題）

---

### 8. 測試增強

#### 8.1 效能測試
```python
# tests/test_performance.py
import pytest
import time

def test_download_speed():
    """測試下載速度"""
    start = time.time()
    download_multiple_files(files[:10])
    duration = time.time() - start
    assert duration < 30, f"下載過慢: {duration}秒"

def test_memory_usage():
    """測試記憶體使用"""
    import tracemalloc
    tracemalloc.start()
    download_large_file()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 100 * 1024 * 1024, f"記憶體用量過高: {peak/1024/1024:.2f}MB"
```

#### 8.2 整合測試
```python
# tests/test_integration.py
def test_full_download_workflow():
    """測試完整下載流程"""
    # 1. 設定
    save_dir = setup_temp_dir()
    
    # 2. 執行下載
    main(years=[113], save_dir=save_dir, keywords=['警察'])
    
    # 3. 驗證
    assert os.path.exists(save_dir / "民國113年")
    assert len(list(save_dir.rglob("*.pdf"))) > 0
    
    # 4. 清理
    cleanup(save_dir)
```

---

## 📊 改進優先級

### 立即執行（本週）
1. ✅ 安全性修正（已完成）
2. ✅ 配置管理（已完成）
3. [ ] 日誌系統（2 小時）

### 短期執行（本月）
4. [ ] 併發下載（4 小時）
5. [ ] 重構高複雜度函數（8 小時）
6. [ ] 錯誤處理強化（3 小時）

### 中期執行（下季度）
7. [ ] 快取機制（3 小時）
8. [ ] 效能測試（4 小時）
9. [ ] 完善文件（8 小時）

---

## 🎯 預期成果

### 程式碼品質
- 安全性: C → A
- 可維護性: B → A
- 效能: C → A
- 測試涵蓋率: 68% → 85%

### 使用者體驗
- 下載速度: ↑ 3-5 倍
- 錯誤提示: 更清晰
- 配置彈性: 更靈活

---

**報告生成時間**: 2026-01-07 21:00:00  
**分析工具**: Bandit, Radon, Manual Review  
**維護者**: 專案團隊
