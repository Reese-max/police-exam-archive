# -*- coding: utf-8 -*-
"""
新功能測試與使用範例
"""

import pytest
from logger import Logger, get_logger
from errors import retry, NetworkError, ignore_errors
from cache import DownloadCache
from concurrent_download import ConcurrentDownloader, DownloadTask


class TestLogger:
    """測試日誌系統"""

    def test_logger_creation(self):
        """測試建立 logger"""
        logger = Logger('test_logger')
        assert logger.logger.name == 'test_logger'

    def test_get_logger(self):
        """測試取得 logger"""
        logger = get_logger('another_test')
        assert logger is not None

    def test_logger_levels(self, capsys):
        """測試日誌層級"""
        logger = Logger('level_test', level='INFO')
        logger.info("測試訊息")
        captured = capsys.readouterr()
        assert "測試訊息" in captured.out


class TestRetryDecorator:
    """測試重試裝飾器"""

    def test_retry_success_on_first_attempt(self):
        """測試第一次就成功"""
        @retry(max_attempts=3)
        def successful_func():
            return "success"

        result = successful_func()
        assert result == "success"

    def test_retry_success_after_failures(self):
        """測試重試後成功"""
        attempts = []

        @retry(max_attempts=3, delay=0.1)
        def failing_then_success():
            attempts.append(1)
            if len(attempts) < 3:
                raise NetworkError("暫時失敗")
            return "success"

        result = failing_then_success()
        assert result == "success"
        assert len(attempts) == 3

    def test_retry_exhausted(self):
        """測試重試耗盡"""
        @retry(max_attempts=2, delay=0.1)
        def always_fail():
            raise NetworkError("永遠失敗")

        with pytest.raises(NetworkError):
            always_fail()


class TestIgnoreErrorsDecorator:
    """測試忽略錯誤裝飾器"""

    def test_ignore_errors_returns_default(self):
        """測試返回預設值"""
        @ignore_errors(default_return=[])
        def failing_func():
            raise ValueError("錯誤")

        result = failing_func()
        assert result == []

    def test_ignore_errors_success(self):
        """測試正常執行"""
        @ignore_errors(default_return=None)
        def success_func():
            return "ok"

        result = success_func()
        assert result == "ok"


class TestDownloadCache:
    """測試快取系統"""

    def test_cache_creation(self, tmp_path):
        """測試建立快取"""
        cache_file = tmp_path / "test_cache.json"
        cache = DownloadCache(cache_file)
        assert cache.cache_file == cache_file

    def test_cache_mark_and_check(self, tmp_path):
        """測試標記和檢查"""
        cache_file = tmp_path / "test_cache.json"
        cache = DownloadCache(cache_file)

        # 建立測試檔案
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test")

        url = "http://test.com/file.pdf"
        file_path = str(test_file)

        # 標記為已下載
        cache.mark_downloaded(url, file_path, 100)

        # 檢查
        assert cache.is_downloaded(url, file_path) is True

    def test_cache_not_downloaded(self, tmp_path):
        """測試未下載情況"""
        cache_file = tmp_path / "test_cache.json"
        cache = DownloadCache(cache_file)

        assert cache.is_downloaded("http://new.com/file.pdf", "/path/to/file.pdf") is False

    def test_cache_stats(self, tmp_path):
        """測試快取統計"""
        cache_file = tmp_path / "test_cache.json"
        cache = DownloadCache(cache_file)

        test_file = tmp_path / "test.pdf"
        test_file.write_text("test")

        cache.mark_downloaded("http://test.com/1.pdf", str(test_file), 1024)
        cache.mark_downloaded("http://test.com/2.pdf", str(test_file), 2048)

        stats = cache.get_stats()
        assert stats['total_files'] == 2
        assert stats['total_size'] == 3072


class TestConcurrentDownloader:
    """測試併發下載"""

    def test_downloader_creation(self):
        """測試建立下載器"""
        downloader = ConcurrentDownloader(max_workers=3, show_progress=False)
        assert downloader.max_workers == 3

    def test_download_tasks_creation(self):
        """測試建立任務"""
        from concurrent_download import create_download_tasks

        tasks = create_download_tasks([
            ("http://test.com/1.pdf", "/path/1.pdf"),
            ("http://test.com/2.pdf", "/path/2.pdf"),
        ])

        assert len(tasks) == 2
        assert tasks[0].url == "http://test.com/1.pdf"

    def test_concurrent_download_mock(self):
        """測試併發下載（Mock）"""
        downloader = ConcurrentDownloader(max_workers=2, show_progress=False)

        # Mock 下載函數
        def mock_download(session, url, path):
            return True, 1024

        tasks = [
            DownloadTask("http://test.com/1.pdf", "/path/1.pdf"),
            DownloadTask("http://test.com/2.pdf", "/path/2.pdf"),
        ]

        results = downloader.download_all(tasks, mock_download, session=None)

        assert len(results) == 2
        assert all(r.success for r in results)
        assert downloader.get_stats()['success'] == 2
