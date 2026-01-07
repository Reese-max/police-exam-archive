# -*- coding: utf-8 -*-
"""
配置管理模組
支援從環境變數和 .env 檔案載入設定
"""

import os
from pathlib import Path


class Config:
    """專案配置類別"""

    def __init__(self):
        self.load_env_file()

    def load_env_file(self):
        """載入 .env 檔案（如果存在）"""
        env_file = Path(__file__).parent / '.env'
        if env_file.exists():
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        try:
                            key, value = line.split('=', 1)
                            os.environ[key.strip()] = value.strip()
                        except ValueError:
                            pass

    @property
    def verify_ssl(self):
        """SSL 證書驗證設定"""
        return os.getenv('VERIFY_SSL', 'False').lower() == 'true'

    @property
    def max_retries(self):
        """最大重試次數"""
        return int(os.getenv('MAX_RETRIES', '3'))

    @property
    def request_timeout(self):
        """請求超時時間（秒）"""
        return int(os.getenv('REQUEST_TIMEOUT', '30'))

    @property
    def concurrent_downloads(self):
        """併發下載數"""
        return int(os.getenv('CONCURRENT_DOWNLOADS', '5'))

    @property
    def log_level(self):
        """日誌層級"""
        return os.getenv('LOG_LEVEL', 'INFO')


# 全域配置實例
config = Config()
