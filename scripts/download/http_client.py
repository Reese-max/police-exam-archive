# -*- coding: utf-8 -*-
"""
強化版 HTTP client：
  * Retry + exponential backoff（429 / 5xx 自動重試）
  * Range 斷點續傳（部分下載 → 接續抓而非整檔重下）
  * PDF 完整性檢查（檔頭 %PDF- + 尾部 %%EOF）
  * ETag/Last-Modified 304 快取（避免重下未變更檔）

用法：
    from scripts.download.http_client import RobustDownloader
    dl = RobustDownloader(cache_dir=".cache")
    success, info = dl.download(url, "out.pdf")
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logger = logging.getLogger(__name__)


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}

PDF_HEADER = b"%PDF-"
PDF_EOF = b"%%EOF"


@dataclass
class DownloadInfo:
    bytes_downloaded: int = 0
    resumed: bool = False
    cached_not_modified: bool = False
    elapsed: float = 0.0
    status_code: int = 0
    error: Optional[str] = None


def make_session(
    pool_connections: int = 10,
    pool_maxsize: int = 10,
    total_retries: int = 5,
    backoff_factor: float = 0.5,
) -> requests.Session:
    """建立帶 Retry/Backoff 的 Session。"""
    retry = Retry(
        total=total_retries,
        connect=total_retries,
        read=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(
        pool_connections=pool_connections,
        pool_maxsize=pool_maxsize,
        max_retries=retry,
    )

    s = requests.Session()
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update(DEFAULT_HEADERS)
    return s


def verify_pdf(path: Path, min_size: int = 1024) -> tuple[bool, str]:
    """驗證 PDF 檔頭/尾與最小大小。"""
    try:
        size = path.stat().st_size
    except OSError as e:
        return False, f"stat error: {e}"

    if size < min_size:
        return False, f"too small: {size} bytes"

    with open(path, "rb") as f:
        head = f.read(8)
        if not head.startswith(PDF_HEADER):
            return False, f"bad header: {head!r}"
        # 讀尾部 2KB 找 %%EOF
        f.seek(max(0, size - 2048))
        tail = f.read()
        if PDF_EOF not in tail:
            return False, "missing %%EOF"

    return True, "ok"


class RobustDownloader:
    """支援 retry / resume / completeness check / 304 cache 的下載器。"""

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        cache_dir: Optional[Path] = None,
        timeout: int = 60,
        verify_ssl: bool = True,
    ):
        self.session = session or make_session()
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._meta = self._load_meta()

    # ---------- HTTP meta cache (ETag / Last-Modified) ----------
    def _meta_file(self) -> Optional[Path]:
        if self.cache_dir is None:
            return None
        return self.cache_dir / "http_meta.json"

    def _load_meta(self) -> dict:
        mf = self._meta_file()
        if not mf or not mf.exists():
            return {}
        try:
            return json.loads(mf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_meta(self) -> None:
        mf = self._meta_file()
        if not mf:
            return
        try:
            tmp = mf.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self._meta, indent=2), encoding="utf-8")
            os.replace(tmp, mf)
        except OSError as e:
            logger.warning(f"meta cache 寫入失敗: {e}")

    @staticmethod
    def _url_key(url: str) -> str:
        return hashlib.sha1(url.encode("utf-8")).hexdigest()

    # ---------- 主入口 ----------
    def download(
        self,
        url: str,
        file_path: str | Path,
        skip_if_valid: bool = True,
        use_resume: bool = True,
        use_cache_headers: bool = True,
    ) -> tuple[bool, DownloadInfo]:
        """
        下載 url 到 file_path。

        Args:
            skip_if_valid: 若檔案已存在且 verify_pdf 通過，直接跳過
            use_resume: 部分下載（.part）存在時用 Range 續傳
            use_cache_headers: 帶 If-None-Match / If-Modified-Since 利用 304

        Returns:
            (success, DownloadInfo)
        """
        info = DownloadInfo()
        start = time.time()
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # 已存在且完整 → 跳過
        if skip_if_valid and file_path.exists():
            ok, _ = verify_pdf(file_path)
            if ok:
                info.elapsed = time.time() - start
                info.bytes_downloaded = file_path.stat().st_size
                info.cached_not_modified = True
                return True, info

        headers = {}
        url_key = self._url_key(url)
        cached_meta = self._meta.get(url_key, {}) if use_cache_headers else {}

        # 304 cache headers
        if cached_meta:
            if cached_meta.get("etag"):
                headers["If-None-Match"] = cached_meta["etag"]
            if cached_meta.get("last_modified"):
                headers["If-Modified-Since"] = cached_meta["last_modified"]

        # Resume header
        part_path = file_path.with_suffix(file_path.suffix + ".part")
        resumed_from = 0
        if use_resume and part_path.exists():
            resumed_from = part_path.stat().st_size
            if resumed_from > 0:
                headers["Range"] = f"bytes={resumed_from}-"
                info.resumed = True

        try:
            with self.session.get(
                url,
                headers=headers,
                stream=True,
                timeout=self.timeout,
                verify=self.verify_ssl,
            ) as resp:
                info.status_code = resp.status_code

                # 304：伺服器確認未變更
                if resp.status_code == 304:
                    info.cached_not_modified = True
                    info.elapsed = time.time() - start
                    if file_path.exists():
                        info.bytes_downloaded = file_path.stat().st_size
                    return True, info

                # Range 不支援時，伺服器回 200 + 全檔，需要重新開始
                if info.resumed and resp.status_code == 200:
                    resumed_from = 0
                    info.resumed = False
                    if part_path.exists():
                        part_path.unlink()

                resp.raise_for_status()

                mode = "ab" if resumed_from > 0 else "wb"
                written = resumed_from
                with open(part_path, mode) as f:
                    for chunk in resp.iter_content(chunk_size=1 << 15):
                        if chunk:
                            f.write(chunk)
                            written += len(chunk)

                info.bytes_downloaded = written

                # 完整性檢查
                ok, reason = verify_pdf(part_path)
                if not ok:
                    info.error = f"verify failed: {reason}"
                    info.elapsed = time.time() - start
                    return False, info

                # 原子搬移
                if file_path.exists():
                    file_path.unlink()
                os.replace(part_path, file_path)

                # 記錄 ETag / Last-Modified
                etag = resp.headers.get("ETag")
                last_modified = resp.headers.get("Last-Modified")
                if etag or last_modified:
                    self._meta[url_key] = {
                        "url": url,
                        "etag": etag,
                        "last_modified": last_modified,
                        "saved_at": time.time(),
                    }
                    self._save_meta()

        except requests.RequestException as e:
            info.error = str(e)
            info.elapsed = time.time() - start
            return False, info

        info.elapsed = time.time() - start
        return True, info
