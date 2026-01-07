# -*- coding: utf-8 -*-
"""
日誌系統模組
提供統一的日誌管理功能
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime


class Logger:
    """日誌管理器"""

    def __init__(self, name='exam_downloader', level=None):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(self._get_log_level(level))

        # 避免重複添加 handler
        if not self.logger.handlers:
            self._setup_handlers()

    def _get_log_level(self, level):
        """取得日誌層級"""
        if level:
            return getattr(logging, level.upper(), logging.INFO)

        # 從環境變數讀取
        try:
            from config import config
            return getattr(logging, config.log_level.upper(), logging.INFO)
        except ImportError:
            return logging.INFO

    def _setup_handlers(self):
        """設定日誌處理器"""
        # 建立 logs 目錄
        log_dir = Path(__file__).parent / 'logs'
        log_dir.mkdir(exist_ok=True)

        # 檔案格式器（詳細）
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 控制台格式器（簡潔）
        console_formatter = logging.Formatter(
            '%(levelname)s: %(message)s'
        )

        # 檔案處理器（帶輪替）
        log_file = log_dir / f'download_{datetime.now():%Y%m%d}.log'
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_formatter)

        # 控制台處理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(console_formatter)

        # 添加處理器
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def debug(self, msg, *args, **kwargs):
        """除錯訊息"""
        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        """一般訊息"""
        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        """警告訊息"""
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        """錯誤訊息"""
        self.logger.error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        """嚴重錯誤訊息"""
        self.logger.critical(msg, *args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        """例外訊息（包含 traceback）"""
        self.logger.exception(msg, *args, **kwargs)


# 全域 logger 實例
logger = Logger()


def get_logger(name=None):
    """取得 logger 實例

    Args:
        name (str, optional): Logger 名稱. Defaults to None.

    Returns:
        Logger: Logger 實例
    """
    if name:
        return Logger(name)
    return logger
