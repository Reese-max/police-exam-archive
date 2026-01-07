# -*- coding: utf-8 -*-
"""
考古題下載 UI 互動函數的單元測試
測試 get_year_input, get_save_folder 等使用者輸入函數
"""

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

# 將專案根目錄加入 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 動態導入模組
spec = importlib.util.spec_from_file_location(
    "exam_downloader",
    project_root / "考古題下載.py"
)
exam_downloader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exam_downloader)


class TestGetYearInput:
    """測試年份輸入函數"""

    def setup_method(self):
        self.get_year_input = exam_downloader.get_year_input

    @patch('builtins.input', return_value='113')
    @patch('builtins.print')
    def test_single_year_input(self, mock_print, mock_input):
        """測試單一年份輸入"""
        result = self.get_year_input()
        assert result == [113]

    @patch('builtins.input', return_value='110-114')
    @patch('builtins.print')
    def test_year_range_input(self, mock_print, mock_input):
        """測試年份範圍輸入"""
        result = self.get_year_input()
        assert result == [110, 111, 112, 113, 114]

    @patch('builtins.input', return_value='110,112,114')
    @patch('builtins.print')
    def test_multiple_years_input(self, mock_print, mock_input):
        """測試多個年份輸入"""
        result = self.get_year_input()
        assert result == [110, 112, 114]

    @patch('builtins.input', return_value='all')
    @patch('builtins.print')
    def test_all_years_input(self, mock_print, mock_input):
        """測試全部年份輸入"""
        result = self.get_year_input()
        assert isinstance(result, list)
        assert len(result) > 0
        assert 81 in result  # 應包含民國81年

    @patch('builtins.input', side_effect=['', '113'])
    @patch('builtins.print')
    def test_empty_input_retry(self, mock_print, mock_input):
        """測試空輸入後重試"""
        result = self.get_year_input()
        assert result == [113]
        assert mock_input.call_count == 2

    @patch('builtins.input', side_effect=['999', '113'])
    @patch('builtins.print')
    def test_invalid_year_retry(self, mock_print, mock_input):
        """測試無效年份後重試"""
        result = self.get_year_input()
        assert result == [113]
        assert mock_input.call_count == 2

    @patch('builtins.input', side_effect=['abc', '113'])
    @patch('builtins.print')
    def test_non_numeric_input_retry(self, mock_print, mock_input):
        """測試非數字輸入後重試"""
        result = self.get_year_input()
        assert result == [113]
        assert mock_input.call_count == 2

    @patch('builtins.input', return_value='110,110,112')
    @patch('builtins.print')
    def test_duplicate_years_removed(self, mock_print, mock_input):
        """測試重複年份被移除"""
        result = self.get_year_input()
        assert result == [110, 112]
        assert result.count(110) == 1


class TestGetSaveFolder:
    """測試儲存資料夾選擇函數"""

    def setup_method(self):
        self.get_save_folder = exam_downloader.get_save_folder
        self.DEFAULT_SAVE_DIR = exam_downloader.DEFAULT_SAVE_DIR

    @patch('builtins.input', return_value='')
    @patch('builtins.print')
    @patch('os.makedirs')
    @patch('builtins.open', create=True)
    @patch('os.remove')
    def test_default_folder(
            self,
            mock_remove,
            mock_open,
            mock_makedirs,
            mock_print,
            mock_input):
        """測試使用預設資料夾"""
        result = self.get_save_folder()
        expected = os.path.abspath(self.DEFAULT_SAVE_DIR)
        assert result == expected

    @patch('builtins.input', return_value='custom_folder')
    @patch('builtins.print')
    @patch('os.makedirs')
    @patch('builtins.open', create=True)
    @patch('os.remove')
    def test_custom_folder(
            self,
            mock_remove,
            mock_open,
            mock_makedirs,
            mock_print,
            mock_input):
        """測試自訂資料夾"""
        result = self.get_save_folder()
        assert 'custom_folder' in result
        mock_makedirs.assert_called_once()

    @patch('builtins.input', side_effect=['C:\\test', 'test_retry'])
    @patch('builtins.print')
    @patch('os.makedirs', side_effect=[PermissionError(), None])
    @patch('builtins.open', create=True)
    @patch('os.remove')
    def test_permission_error_retry(
            self,
            mock_remove,
            mock_open,
            mock_makedirs,
            mock_print,
            mock_input):
        """測試權限錯誤後重試"""
        result = self.get_save_folder()
        assert 'test_retry' in result
        assert mock_input.call_count == 2


class TestGetFilterInput:
    """測試考試類型篩選函數"""

    def setup_method(self):
        self.get_filter_input = exam_downloader.get_filter_input

    @patch('builtins.print')
    def test_returns_police_keywords(self, mock_print):
        """測試返回警察相關關鍵字"""
        keywords = self.get_filter_input()

        assert isinstance(keywords, list)
        assert len(keywords) > 0
        assert "警察人員考試" in keywords
        assert "一般警察人員考試" in keywords
        assert "司法人員考試" in keywords


class TestConfirmSettings:
    """測試設定確認函數"""

    def setup_method(self):
        self.confirm_settings = exam_downloader.confirm_settings

    @patch('builtins.input', return_value='Y')
    @patch('builtins.print')
    def test_confirm_yes(self, mock_print, mock_input):
        """測試確認 Y"""
        result = self.confirm_settings('C:\\test', [113], ['警察'])
        assert result is True

    @patch('builtins.input', return_value='N')
    @patch('builtins.print')
    def test_confirm_no(self, mock_print, mock_input):
        """測試拒絕 N"""
        result = self.confirm_settings('C:\\test', [113], ['警察'])
        assert result is False

    @patch('builtins.input', side_effect=['X', 'Y'])
    @patch('builtins.print')
    def test_invalid_input_retry(self, mock_print, mock_input):
        """測試無效輸入後重試"""
        result = self.confirm_settings('C:\\test', [113], ['警察'])
        assert result is True
        assert mock_input.call_count == 2

    @patch('builtins.input', return_value='y')
    @patch('builtins.print')
    def test_case_insensitive(self, mock_print, mock_input):
        """測試大小寫不敏感"""
        result = self.confirm_settings('C:\\test', [113], ['警察'])
        assert result is True


class TestPrintBanner:
    """測試橫幅顯示函數"""

    def setup_method(self):
        self.print_banner = exam_downloader.print_banner

    @patch('builtins.print')
    def test_prints_banner(self, mock_print):
        """測試顯示橫幅"""
        self.print_banner()
        assert mock_print.called
        # 檢查是否包含關鍵字
        printed_text = ''.join(str(call[0][0])
                               for call in mock_print.call_args_list)
        assert '考選部' in printed_text or '考古題' in printed_text


class TestInputValidation:
    """測試輸入驗證相關函數"""

    @patch('builtins.input', return_value='115-110')
    @patch('builtins.print')
    def test_invalid_year_range_order(self, mock_print, mock_input):
        """測試年份範圍順序錯誤"""
        get_year_input = exam_downloader.get_year_input

        # 修改為接受第二次有效輸入
        with patch('builtins.input', side_effect=['115-110', '110-115']):
            result = get_year_input()
            assert result == [110, 111, 112, 113, 114, 115]

    @patch('builtins.input', side_effect=['50', '113'])
    @patch('builtins.print')
    def test_year_too_old(self, mock_print, mock_input):
        """測試年份過舊（小於81）"""
        get_year_input = exam_downloader.get_year_input
        result = get_year_input()
        assert result == [113]
        assert mock_input.call_count == 2


class TestEdgeCases:
    """測試邊界情況"""

    @patch('builtins.input', return_value='*')
    @patch('builtins.print')
    def test_asterisk_for_all_years(self, mock_print, mock_input):
        """測試使用 * 代表全部年份"""
        get_year_input = exam_downloader.get_year_input
        result = get_year_input()
        assert isinstance(result, list)
        assert len(result) > 0

    @patch('builtins.input', return_value='110, 111, 112')
    @patch('builtins.print')
    def test_years_with_spaces(self, mock_print, mock_input):
        """測試年份間有空格"""
        get_year_input = exam_downloader.get_year_input
        result = get_year_input()
        assert result == [110, 111, 112]

    @patch('builtins.input', return_value='  113  ')
    @patch('builtins.print')
    def test_year_with_surrounding_spaces(self, mock_print, mock_input):
        """測試年份前後有空格"""
        get_year_input = exam_downloader.get_year_input
        result = get_year_input()
        assert result == [113]
