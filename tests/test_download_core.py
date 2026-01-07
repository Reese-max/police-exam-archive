# -*- coding: utf-8 -*-
"""
考古題下載核心函數的單元測試
測試目標：sanitize_filename, check_path_length, get_available_years
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# 將專案根目錄加入 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 動態導入模組（避免執行 main）
import importlib.util
spec = importlib.util.spec_from_file_location(
    "exam_downloader",
    project_root / "考古題下載.py"
)
exam_downloader = importlib.util.module_from_spec(spec)


class TestSanitizeFilename:
    """測試檔名清理函數"""
    
    def setup_method(self):
        # 執行模組但不執行 main
        spec.loader.exec_module(exam_downloader)
        self.sanitize_filename = exam_downloader.sanitize_filename
    
    def test_removes_illegal_characters(self):
        """測試移除非法字元"""
        # Windows 非法字元: \ / : * ? " < > |
        input_name = '測試<檔案>名稱:2024*版本?.pdf'
        result = self.sanitize_filename(input_name)
        assert result == '測試檔案名稱2024版本.pdf'
    
    def test_unescapes_html_entities(self):
        """測試 HTML 實體解碼"""
        input_name = '&lt;警察&gt;考試&amp;題目'
        result = self.sanitize_filename(input_name)
        assert result == '警察考試&題目'
    
    def test_truncates_long_names(self):
        """測試截斷過長檔名（80字元限制）"""
        long_name = 'A' * 100
        result = self.sanitize_filename(long_name)
        assert len(result) == 80
        assert result == 'A' * 80
    
    def test_strips_whitespace(self):
        """測試去除首尾空白"""
        input_name = '  測試檔案  '
        result = self.sanitize_filename(input_name)
        assert result == '測試檔案'
    
    def test_handles_empty_string(self):
        """測試空字串"""
        result = self.sanitize_filename('')
        assert result == ''
    
    def test_handles_unicode_characters(self):
        """測試 Unicode 字元（繁體中文）"""
        input_name = '警察人員三等考試_刑事警察人員'
        result = self.sanitize_filename(input_name)
        assert result == '警察人員三等考試_刑事警察人員'


class TestCheckPathLength:
    """測試路徑長度檢查函數"""
    
    def setup_method(self):
        spec.loader.exec_module(exam_downloader)
        self.check_path_length = exam_downloader.check_path_length
    
    def test_short_path_is_valid(self):
        """測試短路徑通過檢查"""
        short_path = "test.txt"
        is_valid, length = self.check_path_length(short_path, max_length=250)
        assert is_valid is True
        assert length < 250
    
    def test_long_path_is_invalid(self):
        """測試過長路徑失敗"""
        # 建立一個超過250字元的路徑
        long_path = os.path.join('C:\\', 'A' * 100, 'B' * 100, 'C' * 100, 'test.pdf')
        is_valid, length = self.check_path_length(long_path, max_length=250)
        assert is_valid is False
        assert length > 250
    
    def test_exact_limit_path(self):
        """測試剛好在限制邊緣的路徑"""
        # 建立一個剛好250字元的路徑
        current_len = len(os.path.abspath('.'))
        remaining = 250 - current_len - 1  # -1 for path separator
        
        if remaining > 0:
            path_name = 'A' * remaining
            is_valid, length = self.check_path_length(path_name, max_length=250)
            assert length <= 250
    
    def test_returns_actual_length(self):
        """測試返回實際路徑長度"""
        test_path = "test_file.txt"
        is_valid, length = self.check_path_length(test_path)
        abs_path = os.path.abspath(test_path)
        assert length == len(abs_path)
    
    def test_custom_max_length(self):
        """測試自訂最大長度"""
        test_path = "test.txt"
        is_valid, length = self.check_path_length(test_path, max_length=10)
        # 絕對路徑一定會超過10字元
        assert is_valid is False


class TestGetAvailableYears:
    """測試動態年份範圍計算"""
    
    def setup_method(self):
        spec.loader.exec_module(exam_downloader)
        self.get_available_years = exam_downloader.get_available_years
    
    def test_returns_list_of_years(self):
        """測試返回年份清單"""
        years = self.get_available_years()
        assert isinstance(years, list)
        assert len(years) > 0
    
    def test_starts_from_year_81(self):
        """測試從民國81年開始"""
        years = self.get_available_years()
        assert years[0] == 81
    
    def test_includes_current_year(self):
        """測試包含當前年份"""
        current_minguo_year = datetime.now().year - 1911
        years = self.get_available_years()
        assert current_minguo_year in years or current_minguo_year + 1 in years
    
    def test_years_are_sequential(self):
        """測試年份連續"""
        years = self.get_available_years()
        for i in range(len(years) - 1):
            assert years[i + 1] == years[i] + 1


class TestConstants:
    """測試常數設定"""
    
    def setup_method(self):
        spec.loader.exec_module(exam_downloader)
        self.module = exam_downloader
    
    def test_base_url_exists(self):
        """測試基礎 URL 存在"""
        assert hasattr(self.module, 'BASE_URL')
        assert self.module.BASE_URL.startswith('https://')
    
    def test_headers_contains_user_agent(self):
        """測試 HEADERS 包含 User-Agent"""
        assert hasattr(self.module, 'HEADERS')
        assert 'User-Agent' in self.module.HEADERS
    
    def test_default_save_dir_exists(self):
        """測試預設儲存目錄設定"""
        assert hasattr(self.module, 'DEFAULT_SAVE_DIR')
        assert isinstance(self.module.DEFAULT_SAVE_DIR, str)
