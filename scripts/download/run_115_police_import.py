#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""115 年官方匯入器執行入口。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.download import download_115_police as importer  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(importer.main())
