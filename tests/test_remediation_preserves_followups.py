from pathlib import Path

import pytest

from scripts import remediate_115_audit as repair


@pytest.mark.parametrize('relative', ['scripts/build_search_index.py', '考古題網站/js/search-engine.js'])
def test_historical_writer_preserves_image_enabled_corpus_module(tmp_path, monkeypatch, relative):
    original = (repair.ROOT / relative).read_text(encoding='utf-8')
    assert 'optImageA' in original
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(original, encoding='utf-8')
    monkeypatch.setattr(repair, 'ROOT', tmp_path)
    monkeypatch.setattr(repair, 'APPLY', True)
    frozen = repair.build_search_index_source() if relative.endswith('.py') else repair.search_engine_source()
    repair.patch_frontend_module(path, frozen)
    assert path.read_text(encoding='utf-8') == original


@pytest.mark.parametrize('relative', ['scripts/build_search_index.py', '考古題網站/js/answer-utils.js'])
def test_historical_writer_rejects_unknown_module_without_overwriting(tmp_path, monkeypatch, relative):
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    content = '# Custom implementation requiring an explicit migration review.\n'
    path.write_text(content, encoding='utf-8')
    monkeypatch.setattr(repair, 'ROOT', tmp_path)
    monkeypatch.setattr(repair, 'APPLY', True)
    with pytest.raises(RuntimeError, match='未知前端版本'):
        replacement = repair.build_search_index_source() if relative.endswith('.py') else repair.answer_utils_source()
        repair.patch_frontend_module(path, replacement)
    assert path.read_text(encoding='utf-8') == content
