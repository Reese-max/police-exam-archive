#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""115 年匯入器執行入口：套用與既有資料庫一致的安全科目路徑。"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.download import download_115_police as importer  # noqa: E402


MAX_COMPONENT_CHARS = 80
MAX_COMPONENT_BYTES = 240


def safe_component(value: str) -> str:
    """清理科目資料夾名稱，並符合 Linux 單一 component 255-byte 限制。

    舊版下載器固定取前 80 字；沿用相同規則可讓 115 年與歷年科目路徑一致。
    再加上 UTF-8 byte 上限，避免 80 個多位元字元仍超過檔案系統限制。
    """
    value = html.unescape(value).strip()
    value = re.sub(r'[\\/:*?"<>|]', "", value)
    value = re.sub(r"\s+", " ", value)
    if not value:
        raise ValueError("空白科目名稱")

    value = value[:MAX_COMPONENT_CHARS].rstrip(" .")
    while value and len(value.encode("utf-8")) > MAX_COMPONENT_BYTES:
        value = value[:-1].rstrip(" .")
    if not value:
        raise ValueError("科目名稱清理後為空白")
    return value


# subject_from_link() 在執行時查找模組全域 safe_component，故可安全覆寫。
importer.safe_component = safe_component


if __name__ == "__main__":
    raise SystemExit(importer.main())
