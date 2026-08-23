#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修正 115 修復器對 _answer_source 的非冪等子字串替換。"""

from pathlib import Path

path = Path("scripts/remediate_115_audit.py")
text = path.read_text(encoding="utf-8")
old = 'payload["_answer_source"] = answer_path.name if answer_path else ""'
new = 'payload["_answer_source"] = (answer_path.name if answer_path is not None else "")'

count = text.count(old)
if count != 1:
    raise SystemExit(f"預期找到 1 個非冪等替換輸出，實際 {count} 個")

path.write_text(text.replace(old, new, 1), encoding="utf-8")
