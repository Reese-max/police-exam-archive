# -*- coding: utf-8 -*-
"""http_client.py 測試（用本地檔系統，不打外網）"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from scripts.download.http_client import (  # noqa: E402
    DownloadInfo,
    RobustDownloader,
    make_session,
    verify_pdf,
)


# -------- verify_pdf --------
class TestVerifyPdf:
    def test_valid_pdf(self, tmp_path):
        p = tmp_path / "a.pdf"
        body = b"%PDF-1.4\n" + b"x" * 2000 + b"%%EOF\n"
        p.write_bytes(body)
        ok, _ = verify_pdf(p)
        assert ok

    def test_missing_header(self, tmp_path):
        p = tmp_path / "a.pdf"
        p.write_bytes(b"NOTPDF" + b"x" * 2000 + b"%%EOF")
        ok, reason = verify_pdf(p)
        assert not ok and "header" in reason

    def test_missing_eof(self, tmp_path):
        p = tmp_path / "a.pdf"
        p.write_bytes(b"%PDF-1.4\n" + b"x" * 2000)
        ok, reason = verify_pdf(p)
        assert not ok and "EOF" in reason

    def test_too_small(self, tmp_path):
        p = tmp_path / "a.pdf"
        p.write_bytes(b"%PDF-")
        ok, reason = verify_pdf(p)
        assert not ok and "small" in reason


# -------- make_session --------
class TestMakeSession:
    def test_has_retry_adapter(self):
        s = make_session(total_retries=3)
        adapter = s.get_adapter("https://example.com")
        assert adapter.max_retries.total == 3

    def test_default_headers(self):
        s = make_session()
        assert "User-Agent" in s.headers


# -------- skip-if-valid 流程（不打網路） --------
class TestSkipIfValid:
    def test_existing_valid_skip(self, tmp_path):
        p = tmp_path / "a.pdf"
        p.write_bytes(b"%PDF-1.4\n" + b"x" * 2000 + b"%%EOF\n")
        dl = RobustDownloader(cache_dir=tmp_path / "cache")
        ok, info = dl.download(
            "http://localhost:0/nonexistent",  # 不會真的打
            p,
            skip_if_valid=True,
        )
        assert ok
        assert info.cached_not_modified
        assert info.bytes_downloaded > 0
