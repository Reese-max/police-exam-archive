# -*- coding: utf-8 -*-
"""
增量解析 manifest：記錄每個 PDF 的 hash + mtime + 狀態，
讓 pdf_to_questions.py 重跑時跳過未變更檔案。

格式：
    cache/parse_manifest.json
    {
        "version": 1,
        "entries": {
            "<absolute_pdf_path>": {
                "sha256": "...",
                "mtime": 1700000000.0,
                "size": 12345,
                "output": "<output_json_path>",
                "questions": 25,
                "used_ocr": false,
                "timestamp": "ISO 8601"
            },
            ...
        }
    }
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


MANIFEST_VERSION = 1


class ParseManifest:
    """檔案級別的增量處理 manifest。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"version": MANIFEST_VERSION, "entries": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("version") != MANIFEST_VERSION:
                # 版本不符直接重建
                return {"version": MANIFEST_VERSION, "entries": {}}
            data.setdefault("entries", {})
            return data
        except (json.JSONDecodeError, OSError):
            return {"version": MANIFEST_VERSION, "entries": {}}

    def save(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    @staticmethod
    def _key(pdf_path: Path) -> str:
        return str(Path(pdf_path).resolve())

    @staticmethod
    def file_sha256(pdf_path: Path, chunk: int = 1 << 16) -> str:
        h = hashlib.sha256()
        with open(pdf_path, "rb") as f:
            for blk in iter(lambda: f.read(chunk), b""):
                h.update(blk)
        return h.hexdigest()

    def is_unchanged(self, pdf_path: Path) -> bool:
        """檔案內容與 mtime 都沒變且輸出存在 → 可跳過。"""
        key = self._key(pdf_path)
        entry = self._data["entries"].get(key)
        if not entry:
            return False

        try:
            stat = pdf_path.stat()
        except OSError:
            return False

        # 快檢：size + mtime 一致
        if entry.get("size") != stat.st_size:
            return False
        if abs(entry.get("mtime", 0) - stat.st_mtime) > 1:
            return False

        # 輸出 JSON 還在
        out = entry.get("output")
        if not out or not Path(out).exists():
            return False

        return True

    def record(
        self,
        pdf_path: Path,
        output_json: Path,
        questions: int = 0,
        used_ocr: bool = False,
        sha256: Optional[str] = None,
    ) -> None:
        try:
            stat = pdf_path.stat()
        except OSError:
            return

        self._data["entries"][self._key(pdf_path)] = {
            "sha256": sha256 or self.file_sha256(pdf_path),
            "mtime": stat.st_mtime,
            "size": stat.st_size,
            "output": str(Path(output_json).resolve()),
            "questions": questions,
            "used_ocr": used_ocr,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    def remove(self, pdf_path: Path) -> None:
        self._data["entries"].pop(self._key(pdf_path), None)

    def stats(self) -> dict:
        entries = self._data["entries"]
        return {
            "total": len(entries),
            "ocr_used": sum(1 for e in entries.values() if e.get("used_ocr")),
            "total_questions": sum(e.get("questions", 0) for e in entries.values()),
        }
