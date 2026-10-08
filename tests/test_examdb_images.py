"""SQLite/API/CLI image provenance and non-destructive generated-cache upgrades."""

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

import examdb
from examdb import ExamDB, format_question


ROOT = Path(__file__).resolve().parents[1]


def write_source(root, subject="圖片科目"):
    path = root / "圖片類科" / "109年" / subject / "試題.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    images = {
        label: {"src": f"images/q2-{label}.png", "public_src": f"圖片類科/109年/images/q2-{label}.png",
                "alt": f"選項 {label} 的圖", "sha256": label.lower() * 64,
                "crop": [1, 2, 30, 40], "extra": {"preserve": True}}
        for label in "ABCD"
    }
    locator = {"pdf": "109_圖片題.pdf", "page": 2, "pdf_sha256": "f" * 64,
               "url": "https://official.example.invalid/exam.pdf", "question": 2,
               "extra": {"verified_by": "synthetic fixture"}}
    question = {"number": 2, "type": "choice", "stem": "辨認原始圖形", "options": dict.fromkeys("ABCD", "[圖片選項]"),
                "answer": "B", "passage": "原始段落", "section": "第一節",
                "option_images": images, "source_locator": locator}
    path.write_text(json.dumps({"metadata": {"subject": subject}, "questions": [question]}, ensure_ascii=False), encoding="utf-8")
    return path, question


def legacy_index(target, source, missing=("option_images", "source_locator"), custom_table=False):
    columns = ["id INTEGER PRIMARY KEY", "file_id INTEGER NOT NULL", "number TEXT", "type TEXT NOT NULL",
               "stem TEXT", "option_a TEXT", "option_b TEXT", "option_c TEXT", "option_d TEXT", "answer TEXT",
               "passage TEXT", "section TEXT"]
    extra = [name for name in ("option_images", "source_locator") if name not in missing]
    columns.extend(f"{name} TEXT" for name in extra)
    with closing(sqlite3.connect(target)) as conn:
        conn.execute("CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT NOT NULL, category TEXT, year INTEGER, subject TEXT, exam_name TEXT, level TEXT)")
        conn.execute("CREATE TABLE questions (" + ",".join(columns) + ")")
        conn.execute("INSERT INTO files VALUES (1,?, '圖片類科',109,'圖片科目','','')", (str(source),))
        row = [1, 1, "2", "choice", "舊快取仍須保留", "old A", "old B", "old C", "old D", "B", "old passage", "old section"]
        row.extend(json.dumps({"old": name}) for name in extra)
        conn.execute("INSERT INTO questions VALUES (" + ",".join("?" for _ in row) + ")", row)
        if custom_table:
            conn.execute("CREATE TABLE personal_notes (note TEXT)")
            conn.execute("INSERT INTO personal_notes VALUES ('must survive')")
        conn.commit()


def raw_snapshot(target):
    with closing(sqlite3.connect(target)) as conn:
        return conn.execute("SELECT * FROM files").fetchall(), conn.execute("SELECT * FROM questions").fetchall()


def cli(target, data_dir, *arguments):
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run([sys.executable, str(ROOT / "examdb.py"), "--db", str(target), "--data-dir", str(data_dir), *arguments],
                          capture_output=True, text=True, encoding="utf-8", env=environment, check=False)


def assert_complete(row, question):
    assert row["option_images"] == question["option_images"]
    assert row["source_locator"] == question["source_locator"]
    assert row["number"] == "2" and row["stem"] == question["stem"]
    assert row["answer"] == "B" and row["passage"] == question["passage"]
    assert row["section"] == question["section"]
    for label in "ABCD":
        assert row[f"option_{label.lower()}"] == question["options"][label]


def test_fresh_api_and_readable_format_preserve_images_and_full_provenance(tmp_path):
    root, target = tmp_path / "bank", tmp_path / "exam.db"
    _, question = write_source(root)
    with ExamDB(target, root) as db:
        rows = db.search(year=109, subject="圖片科目")
        assert len(rows) == 1
        assert_complete(rows[0], question)
        assert_complete(db.random()[0], question)
        text = format_question(rows[0])
        for image in question["option_images"].values():
            assert image["public_src"] in text and image["src"] in text and image["alt"] in text
        assert question["source_locator"]["url"] in text
        assert question["source_locator"]["pdf"] in text
        assert "來源頁碼: 2" in text and question["source_locator"]["pdf_sha256"] in text


@pytest.mark.parametrize("command", [("query", "--json"), ("random", "--count", "1", "--json")])
def test_cli_fresh_index_json_is_complete_and_diagnostics_stay_on_stderr(tmp_path, command):
    root, target = tmp_path / "bank", tmp_path / "exam.db"
    _, question = write_source(root)
    result = cli(target, root, *command)
    assert result.returncode == 0, result.stderr
    assert "索引建立完成" in result.stderr
    rows = json.loads(result.stdout)
    assert len(rows) == 1
    assert_complete(rows[0], question)
    text = cli(target, root, "query")
    assert text.returncode == 0
    assert question["source_locator"]["url"] in text.stdout
    assert all(image["public_src"] in text.stdout for image in question["option_images"].values())


@pytest.mark.parametrize("missing", [("option_images",), ("source_locator",), ("option_images", "source_locator")])
def test_legacy_missing_either_column_rebuilds_atomically(tmp_path, missing):
    root, target = tmp_path / "bank", tmp_path / "exam.db"
    source, question = write_source(root)
    legacy_index(target, source, missing)
    with ExamDB(target, root) as db:
        assert_complete(db.search()[0], question)
        assert {"option_images", "source_locator"} <= {row[1] for row in db.conn.execute("PRAGMA table_info(questions)")}
    assert not list(tmp_path.glob("exam-schema-*.db"))


def test_legacy_source_locators_allow_moving_the_bank_between_clones(tmp_path):
    root, target = tmp_path / "new-clone" / "bank", tmp_path / "exam.db"
    _, question = write_source(root)
    old_source = tmp_path / "old-clone" / "bank" / "圖片類科" / "109年" / "圖片科目" / "試題.json"
    legacy_index(target, old_source)
    with ExamDB(target, root) as db:
        assert_complete(db.search()[0], question)


@pytest.mark.parametrize("bad_source", ["{invalid JSON", '{"metadata": {}, "questions": {}}', '{"metadata": {}, "questions": [{"option_images": []}]}'])
def test_failed_source_upgrade_keeps_old_bytes_and_tables_and_closes_temporary_writer(tmp_path, monkeypatch, bad_source):
    root, target = tmp_path / "bank", tmp_path / "exam.db"
    source, _ = write_source(root)
    legacy_index(target, source)
    before, rows = target.read_bytes(), raw_snapshot(target)
    source.write_text(bad_source, encoding="utf-8")
    connections = []
    real_connect = sqlite3.connect

    def tracked_connect(path, *args, **kwargs):
        conn = real_connect(path, *args, **kwargs)
        connections.append((str(path), conn))
        return conn

    monkeypatch.setattr(examdb.sqlite3, "connect", tracked_connect)
    with pytest.raises(ValueError):
        ExamDB(target, root)
    assert target.read_bytes() == before
    assert raw_snapshot(target) == rows
    writers = [conn for path, conn in connections if Path(path).name.startswith("exam-schema-")]
    assert writers
    for writer in writers:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            writer.execute("SELECT 1")
    assert not list(tmp_path.glob("exam-schema-*.db"))


@pytest.mark.parametrize("missing", [("option_images",), ()])
def test_unknown_custom_tables_refuse_upgrade_or_force_build_without_data_loss(tmp_path, missing):
    root, target = tmp_path / "bank", tmp_path / "exam.db"
    source, _ = write_source(root)
    legacy_index(target, source, missing, custom_table=True)
    before = target.read_bytes()
    with pytest.raises(RuntimeError, match="未知"):
        ExamDB(target, root, rebuild=not missing)
    assert target.read_bytes() == before
    with closing(sqlite3.connect(target)) as conn:
        assert conn.execute("SELECT note FROM personal_notes").fetchall() == [("must survive",)]


@pytest.mark.parametrize("partial", [False, True])
def test_missing_all_or_one_recorded_source_preserves_cache(tmp_path, partial):
    root, target = tmp_path / "bank", tmp_path / "exam.db"
    source, _ = write_source(root)
    legacy_index(target, source)
    if partial:
        write_source(root, subject="另一科目")
    source.unlink()
    before = target.read_bytes()
    with pytest.raises(RuntimeError, match="來源"):
        ExamDB(target, root)
    assert target.read_bytes() == before


def test_explicit_cli_build_with_bad_source_preserves_modern_cache(tmp_path):
    root, target = tmp_path / "bank", tmp_path / "exam.db"
    source, _ = write_source(root)
    legacy_index(target, source, missing=())
    before = target.read_bytes()
    source.write_text("{broken", encoding="utf-8")
    result = cli(target, root, "build")
    assert result.returncode != 0
    assert target.read_bytes() == before
    assert not list(tmp_path.glob("exam-schema-*.db"))


def test_failed_atomic_replace_preserves_old_index_and_cleans_temp(tmp_path, monkeypatch):
    root, target = tmp_path / "bank", tmp_path / "exam.db"
    source, _ = write_source(root)
    legacy_index(target, source)
    before = target.read_bytes()

    def reject_replace(*_args):
        raise PermissionError("synthetic locked target")

    monkeypatch.setattr(examdb.os, "replace", reject_replace)
    with pytest.raises(PermissionError):
        ExamDB(target, root)
    assert target.read_bytes() == before
    assert not list(tmp_path.glob("exam-schema-*.db"))
