# -*- coding: utf-8 -*-
"""manifest.py 測試"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.parse.manifest import ParseManifest  # noqa: E402


def _make_pdf(tmp_path: Path, name: str = "a.pdf", content: bytes = b"hello") -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


class TestParseManifest:
    def test_empty_initially(self, tmp_path):
        m = ParseManifest(tmp_path / "manifest.json")
        assert m.stats()["total"] == 0

    def test_record_and_skip(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        out = tmp_path / "a.json"
        out.write_text("{}")

        m = ParseManifest(tmp_path / "manifest.json")
        assert not m.is_unchanged(pdf)

        m.record(pdf, out, questions=10, used_ocr=False)
        assert m.is_unchanged(pdf)

    def test_invalidate_on_mtime_change(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        out = tmp_path / "a.json"
        out.write_text("{}")
        m = ParseManifest(tmp_path / "manifest.json")
        m.record(pdf, out, questions=10)

        # 變更內容（mtime + size 都變）
        pdf.write_bytes(b"hello world larger")
        assert not m.is_unchanged(pdf)

    def test_invalidate_when_output_missing(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        out = tmp_path / "a.json"
        out.write_text("{}")
        m = ParseManifest(tmp_path / "manifest.json")
        m.record(pdf, out)
        out.unlink()
        assert not m.is_unchanged(pdf)

    def test_persist_across_instances(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        out = tmp_path / "a.json"
        out.write_text("{}")
        manifest_path = tmp_path / "manifest.json"

        m1 = ParseManifest(manifest_path)
        m1.record(pdf, out, questions=10)
        m1.save()

        m2 = ParseManifest(manifest_path)
        assert m2.is_unchanged(pdf)
        assert m2.stats()["total_questions"] == 10
