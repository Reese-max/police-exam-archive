# -*- coding: utf-8 -*-
"""
錯誤處理模組
定義自訂例外類別和重試裝飾器
"""

import time
import functools
from typing import Callable, Any


# ==================== 自訂例外類別 ====================

class DownloadError(Exception):
    """下載錯誤基礎類別"""
    pass


class NetworkError(DownloadError):
    """網路連線錯誤"""
    pass


class PathTooLongError(DownloadError):
    """路徑過長錯誤"""
    pass


class FileValidationError(DownloadError):
    """檔案驗證錯誤"""
    pass


class ParseError(DownloadError):
    """解析錯誤"""
    pass


class ConfigError(Exception):
    """配置錯誤"""
    pass


# ==================== 重試裝飾器 ====================

def retry(max_attempts=3, delay=1, backoff=2, exceptions=(Exception,)):
    """重試裝飾器

    Args:
        max_attempts (int): 最大嘗試次數
        delay (float): 初始延遲時間（秒）
        backoff (float): 退避倍數
        exceptions (tuple): 需要重試的例外類型

    Example:
        @retry(max_attempts=3, delay=1, backoff=2)
        def download_file(url):
            # ... 下載邏輯 ...
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            attempt = 0
            current_delay = delay

            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        raise

                    # 記錄重試訊息
                    try:
                        from logger import logger
                        logger.warning(
                            f"{func.__name__} 失敗 (嘗試 {attempt}/{max_attempts}): {e}. "
                            f"將在 {current_delay:.1f} 秒後重試..."
                        )
                    except ImportError:
                        print(f"重試 {attempt}/{max_attempts} 次，{current_delay:.1f}秒後...")

                    time.sleep(current_delay)
                    current_delay *= backoff

        return wrapper
    return decorator


def ignore_errors(default_return=None, log_error=True):
    """忽略錯誤裝飾器

    Args:
        default_return: 發生錯誤時的預設返回值
        log_error (bool): 是否記錄錯誤

    Example:
        @ignore_errors(default_return=[])
        def get_optional_data():
            # ... 可能失敗的邏輯 ...
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_error:
                    try:
                        from logger import logger
                        logger.error(f"{func.__name__} 發生錯誤: {e}")
                    except ImportError:
                        print(f"錯誤: {e}")
                return default_return
        return wrapper
    return decorator


# ==================== 錯誤處理輔助函數 ====================

def handle_download_error(error: Exception, url: str, file_path: str) -> str:
    """統一處理下載錯誤

    Args:
        error: 例外物件
        url: 下載 URL
        file_path: 檔案路徑

    Returns:
        str: 錯誤訊息
    """
    import requests

    if isinstance(error, requests.exceptions.Timeout):
        return f"請求超時: {url}"
    elif isinstance(error, requests.exceptions.ConnectionError):
        return f"連線錯誤: 無法連接至伺服器"
    elif isinstance(error, requests.exceptions.HTTPError):
        return f"HTTP 錯誤 {error.response.status_code}: {url}"
    elif isinstance(error, PathTooLongError):
        return f"路徑過長 ({len(file_path)} 字元): {file_path}"
    elif isinstance(error, FileValidationError):
        return f"檔案驗證失敗: {error}"
    else:
        return f"未知錯誤: {type(error).__name__} - {error}"
