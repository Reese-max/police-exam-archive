import hashlib
import subprocess
from pathlib import Path

import pytest

from scripts.check_corpus_claims import _check_search
from scripts.build_quality_summary import _fingerprint_at_commit


@pytest.mark.parametrize('lead', [
    '跨部門搜尋 42,483 道警察特考考古題。',
    '跨類科搜尋 42,483 道歷年警察特考考古題與閱讀題組。',
])
def test_current_search_wording_cannot_reintroduce_fixed_count(tmp_path: Path, lead: str):
    site = tmp_path / '考古題網站'
    site.mkdir()
    page = (
        f'<p class="lead">{lead}</p>\n'
        "SearchEngine.loadIndex().then(function(stats){\n"
        "document.getElementById('statTotal').textContent=stats.total.toLocaleString();\n"
    )
    (site / 'search.html').write_text(page, encoding='utf-8')
    findings = _check_search(tmp_path, {})
    assert any('固定搜尋題數' in finding.actual for finding in findings)


def test_git_corpus_fingerprint_ignores_checkout_newline_conversion(tmp_path: Path):
    repo = tmp_path / 'repo'
    repo.mkdir()

    def git(*args: str) -> bytes:
        result = subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)
        return result.stdout

    git('init')
    git('config', 'core.autocrlf', 'false')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.test')
    data = repo / '考古題庫'
    contents = {
        'Case/115年/LF/試題.json': b'{\n"questions": []\n}\n',
        'Case/115年/CRLF/試題.json': b'{\r\n"questions": []\r\n}\r\n',
    }
    files = []
    expected = hashlib.sha256()
    for relative, content in sorted(contents.items()):
        path = data / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        files.append(str(path))
        expected.update(relative.encode('utf-8'))
        expected.update(b'\0')
        expected.update(hashlib.sha256(content).digest())
    git('add', '.')
    git('commit', '-m', 'Corpus fixture')
    sha = git('rev-parse', 'HEAD').decode('ascii').strip()
    identity = 'sha256:' + expected.hexdigest()
    assert _fingerprint_at_commit(files, data, repo, sha) == identity
    git('config', 'core.autocrlf', 'true')
    assert _fingerprint_at_commit(files, data, repo, sha) == identity
