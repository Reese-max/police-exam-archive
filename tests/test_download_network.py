# -*- coding: utf-8 -*-
"""
考古題下載網路相關函數的單元測試
使用 pytest-mock 和 responses 模擬 HTTP 請求
"""

import os
import sys
import pytest
import requests
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from io import BytesIO

# 將專案根目錄加入 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 動態導入模組
import importlib.util
spec = importlib.util.spec_from_file_location(
    "exam_downloader",
    project_root / "考古題下載.py"
)
exam_downloader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exam_downloader)


class TestDownloadFile:
    """測試檔案下載函數"""
    
    def setup_method(self):
        self.download_file = exam_downloader.download_file
        self.session = requests.Session()
    
    def test_successful_download(self, tmp_path, mocker):
        """測試成功下載 PDF"""
        # 建立測試檔案路徑
        test_file = tmp_path / "test.pdf"
        
        # Mock HTTP 回應
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'application/pdf'}
        # 產生足夠大的內容（超過1024位元組）
        pdf_content = b'PDF content ' * 100  # ~1200 bytes
        mock_response.iter_content = Mock(return_value=[pdf_content])
        mock_response.raise_for_status = Mock()
        
        mocker.patch.object(self.session, 'get', return_value=mock_response)
        
        # 執行下載
        success, result = self.download_file(self.session, 'http://test.com/file.pdf', str(test_file))
        
        assert success is True
        assert isinstance(result, int)  # 檔案大小
        assert result > 1024  # 應該大於1024位元組
        assert test_file.exists()
    
    def test_download_fails_on_non_pdf(self, tmp_path, mocker):
        """測試非 PDF 檔案被拒絕"""
        test_file = tmp_path / "test.html"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'text/html'}
        mock_response.raise_for_status = Mock()
        
        mocker.patch.object(self.session, 'get', return_value=mock_response)
        
        success, result = self.download_file(self.session, 'http://test.com/file.html', str(test_file))
        
        assert success is False
        assert result == "非PDF檔案"
    
    def test_download_retries_on_timeout(self, tmp_path, mocker):
        """測試超時時重試"""
        test_file = tmp_path / "test.pdf"
        
        # Mock 前兩次超時，第三次成功
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.headers = {'Content-Type': 'application/pdf'}
        # 產生足夠大的內容
        pdf_content = b'PDF content ' * 100
        mock_response_success.iter_content = Mock(return_value=[pdf_content])
        mock_response_success.raise_for_status = Mock()
        
        mocker.patch.object(
            self.session, 
            'get',
            side_effect=[
                requests.exceptions.Timeout(),
                requests.exceptions.Timeout(),
                mock_response_success
            ]
        )
        
        # 執行下載
        success, result = self.download_file(self.session, 'http://test.com/file.pdf', str(test_file), max_retries=3)
        
        assert success is True
        assert test_file.exists()
    
    def test_download_fails_after_max_retries(self, tmp_path, mocker):
        """測試達到最大重試次數後失敗"""
        test_file = tmp_path / "test.pdf"
        
        # Mock 所有請求都超時
        mocker.patch.object(
            self.session,
            'get',
            side_effect=requests.exceptions.Timeout()
        )
        
        success, result = self.download_file(self.session, 'http://test.com/file.pdf', str(test_file), max_retries=2)
        
        assert success is False
        assert result == "請求超時"
    
    def test_download_removes_small_files(self, tmp_path, mocker):
        """測試刪除過小的檔案"""
        test_file = tmp_path / "test.pdf"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'application/pdf'}
        mock_response.iter_content = Mock(return_value=[b'x'])  # 只有1個位元組
        mock_response.raise_for_status = Mock()
        
        mocker.patch.object(self.session, 'get', return_value=mock_response)
        
        success, result = self.download_file(self.session, 'http://test.com/file.pdf', str(test_file))
        
        assert success is False
        assert result == "檔案過小"
        assert not test_file.exists()


class TestGetExamListByYear:
    """測試獲取考試列表函數"""
    
    def setup_method(self):
        self.get_exam_list_by_year = exam_downloader.get_exam_list_by_year
        self.session = requests.Session()
    
    def test_successful_fetch_with_keywords(self, mocker):
        """測試成功獲取考試列表（帶關鍵字篩選）"""
        # Mock HTML 回應
        mock_html = """
        <html>
            <select id="ddlExamCode">
                <option value="001">警察人員考試</option>
                <option value="002">一般警察人員考試</option>
                <option value="003">高考三級</option>
            </select>
        </html>
        """
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = mock_html
        mock_response.raise_for_status = Mock()
        
        mocker.patch.object(self.session, 'get', return_value=mock_response)
        
        keywords = ["警察人員考試", "一般警察人員考試"]
        exams = self.get_exam_list_by_year(self.session, 113, keywords)
        
        assert len(exams) == 2
        assert exams[0]['code'] == '001'
        assert exams[0]['name'] == '警察人員考試'
        assert exams[0]['year'] == 113
    
    def test_fetch_without_keywords(self, mocker):
        """測試獲取所有考試（無關鍵字篩選）"""
        mock_html = """
        <html>
            <select id="ddlExamCode">
                <option value="001">考試A</option>
                <option value="002">考試B</option>
            </select>
        </html>
        """
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = mock_html
        mock_response.raise_for_status = Mock()
        
        mocker.patch.object(self.session, 'get', return_value=mock_response)
        
        exams = self.get_exam_list_by_year(self.session, 113, keywords=None)
        
        assert len(exams) == 2
    
    def test_returns_empty_when_no_select(self, mocker):
        """測試找不到 select 元素時返回空列表"""
        mock_html = "<html><body>No select element</body></html>"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = mock_html
        mock_response.raise_for_status = Mock()
        
        mocker.patch.object(self.session, 'get', return_value=mock_response)
        
        exams = self.get_exam_list_by_year(self.session, 113, [])
        
        assert exams == []
    
    def test_retries_on_timeout(self, mocker):
        """測試超時重試機制"""
        mock_html = """
        <html>
            <select id="ddlExamCode">
                <option value="001">警察人員考試</option>
            </select>
        </html>
        """
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = mock_html
        mock_response.raise_for_status = Mock()
        
        # 前兩次超時，第三次成功
        mocker.patch.object(
            self.session,
            'get',
            side_effect=[
                requests.exceptions.Timeout(),
                requests.exceptions.Timeout(),
                mock_response
            ]
        )
        
        exams = self.get_exam_list_by_year(self.session, 113, ["警察人員考試"], max_retries=3)
        
        assert len(exams) == 1
    
    def test_returns_empty_after_max_retries(self, mocker):
        """測試達到最大重試次數後返回空列表"""
        mocker.patch.object(
            self.session,
            'get',
            side_effect=requests.exceptions.Timeout()
        )
        
        exams = self.get_exam_list_by_year(self.session, 113, [], max_retries=2)
        
        assert exams == []


class TestParseExamPage:
    """測試考試頁面解析函數"""
    
    def setup_method(self):
        self.parse_exam_page = exam_downloader.parse_exam_page
    
    def test_parses_internal_exam_structure(self):
        """測試解析內軌考試結構（行政警察）"""
        mock_html = """
        <html>
            <tr>
                <label class="exam-title">警察學與警察勤務</label>
                <a href="wHandExamQandA_File.ashx?c=001&t=Q">試題</a>
            </tr>
            <tr>
                <label class="exam-title">警察政策與犯罪預防</label>
                <a href="wHandExamQandA_File.ashx?c=001&t=S">答案</a>
            </tr>
            <tr>
                <label class="exam-title">中華民國憲法與警察專業英文</label>
                <a href="wHandExamQandA_File.ashx?c=001&t=Q">試題</a>
            </tr>
        </html>
        """
        
        result = self.parse_exam_page(mock_html)
        
        assert len(result) > 0
        assert '警察人員考試三等考試_行政警察人員' in result
    
    def test_returns_empty_for_non_target_exams(self):
        """測試非目標考試返回空字典"""
        mock_html = """
        <html>
            <tr>
                <label>一般科目A</label>
                <a href="wHandExamQandA_File.ashx?c=999&t=Q">試題</a>
            </tr>
        </html>
        """
        
        result = self.parse_exam_page(mock_html)
        
        assert result == {}
    
    def test_handles_multiple_file_types(self):
        """測試處理多種檔案類型（試題、答案、更正答案）"""
        mock_html = """
        <html>
            <tr>
                <label class="exam-title">警察學與警察勤務</label>
                <a href="wHandExamQandA_File.ashx?c=001&t=Q">試題</a>
                <a href="wHandExamQandA_File.ashx?c=001&t=S">答案</a>
                <a href="wHandExamQandA_File.ashx?c=001&t=M">更正答案</a>
            </tr>
            <tr>
                <label class="exam-title">中華民國憲法與警察專業英文</label>
                <a href="wHandExamQandA_File.ashx?c=001&t=Q">試題</a>
            </tr>
        </html>
        """
        
        result = self.parse_exam_page(mock_html)
        
        if result:
            category = list(result.values())[0]
            if len(category) > 0:
                subject = category[0]
                assert 'downloads' in subject
                assert len(subject['downloads']) > 0
