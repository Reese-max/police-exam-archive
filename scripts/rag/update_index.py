#!/usr/bin/env python3
"""Update a prebuilt BGE-M3 index without ever rebuilding it from scratch."""

import argparse
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

if __package__:
    from .build_corpus import build_corpus, json_text
    from .build_index import build_index, index_write_lock, retryable_sqlite_errors
    from .build_source_map import build_source_map, write_json
    from .fetch_moex_catalog import fetch_catalog
    from .retrieval import (EMBEDDING_TEXT_VERSION, SCHEMA_VERSION, embedding_text_version, metadata, open_index,
                            pending_vector_questions, validate_model_revision)
else:
    from build_corpus import build_corpus, json_text
    from build_index import build_index, index_write_lock, retryable_sqlite_errors
    from build_source_map import build_source_map, write_json
    from fetch_moex_catalog import fetch_catalog
    from retrieval import (EMBEDDING_TEXT_VERSION, SCHEMA_VERSION, embedding_text_version, metadata, open_index,
                           pending_vector_questions, validate_model_revision)


MODEL = "BAAI/bge-m3"
ROOT = Path(__file__).resolve().parents[2]


def file_digest(stream):
    stream.seek(0)
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.digest()


@contextmanager
def _replacement_guard_local(db):
    """Hold SQLite's exclusive byte range while checking and replacing the seed.

    Do not open or close another descriptor for this inode while this guard is
    active: POSIX record locks are process-wide and a close releases them.
    """
    path = Path(db).resolve()
    def has_sidecars():
        return any(os.path.lexists(str(path) + suffix) for suffix in ("-wal", "-shm", "-journal"))
    if has_sidecars():
        raise ValueError("索引使用 WAL 或仍有 SQLite sidecar；拒絕替換，請保留原檔")
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        import msvcrt

        class Overlapped(ctypes.Structure):
            _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t),
                        ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                        ("hEvent", wintypes.HANDLE)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.LockFileEx.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped))
        kernel.UnlockFileEx.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                        wintypes.DWORD, ctypes.POINTER(Overlapped))
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.CreateFileW(str(path), 0xC0000000, 7, None, 3, 0x80, None)
        if handle == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
        except BaseException:
            kernel.CloseHandle(handle)
            raise
        stream = os.fdopen(fd, "r+b", buffering=0)
        overlapped = Overlapped(Offset=0x40000000)
        locked = kernel.LockFileEx(handle, 3, 0, 512, 0, ctypes.byref(overlapped))
        if not locked:
            error = ctypes.get_last_error()
            stream.close()
            if error in (33, 36, 158):
                raise sqlite3.OperationalError("database is locked")
            raise ctypes.WinError(error)
        def unlock():
            if not kernel.UnlockFileEx(handle, 0, 512, 0, ctypes.byref(overlapped)):
                raise ctypes.WinError(ctypes.get_last_error())
    else:
        import errno
        import fcntl

        stream = path.open("r+b", buffering=0)
        try:
            fcntl.lockf(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB, 512, 0x40000000)
        except OSError as exc:
            stream.close()
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                raise sqlite3.OperationalError("database is locked") from exc
            raise
        def unlock():
            fcntl.lockf(stream.fileno(), fcntl.LOCK_UN, 512, 0x40000000)
    try:
        opened, current = os.fstat(stream.fileno()), path.stat()
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino) or opened.st_nlink > 1:
            raise ValueError("索引已替換或有多個硬連結；請安全重試")
        header = stream.read(20)
        if (len(header) < 20 or header[:16] != b"SQLite format 3\x00" or header[18:20] != b"\x01\x01"
                or has_sidecars()):
            raise ValueError("索引使用 WAL 或仍有 SQLite sidecar；拒絕替換，請保留原檔")
        yield stream
    finally:
        try:
            unlock()
        finally:
            stream.close()


def _check_replacement_target(stream, db):
    opened = os.fstat(stream.fileno())
    try:
        current = Path(db).stat()
    except FileNotFoundError as exc:
        raise ValueError("來源索引已替換；請保留原檔並安全重試") from exc
    if (opened.st_nlink != 1 or current.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)):
        raise ValueError("來源索引已替換或有多個硬連結；請保留原檔並安全重試")


def _check_replaced_seed_unlinked(stream):
    if os.fstat(stream.fileno()).st_nlink:
        raise ValueError("原索引仍有硬連結")


def _guard_worker(db, expected_digest):
    try:
        with _replacement_guard_local(db) as stream:
            if expected_digest and file_digest(stream).hex() != expected_digest:
                raise ValueError("備份後來源索引已變更；請保留原檔並安全重試")
            print(json.dumps({"ready": True}), flush=True)
            command = sys.stdin.readline()
            if command.strip():
                candidate = json.loads(command)["candidate"]
                _, candidate_digest = snapshot_file_digest(candidate)
                _check_replacement_target(stream, db)
                try:
                    replace_candidate(candidate, db)
                    _check_replaced_seed_unlinked(stream)
                    _, destination_digest = snapshot_file_digest(db)
                    if destination_digest != candidate_digest:
                        raise ValueError("替換後目的地與候選檔雜湊不符")
                except Exception as exc:
                    raise RuntimeError(f"索引可能已替換，狀態不確定；請停止更新並檢查目的地：{exc}") from exc
                print(json.dumps({"replaced": True, "digest": candidate_digest}), flush=True)
    except Exception as exc:
        kind = "sqlite" if isinstance(exc, sqlite3.OperationalError) else "value" if isinstance(exc, ValueError) else "os"
        print(json.dumps({"error": str(exc), "kind": kind}), flush=True)
        sys.exit(1)


@contextmanager
def replacement_guard(db, expected_digest=None):
    # POSIX record locks are per-process, so the raw descriptor and lock must
    # live outside the process that may have other SQLite connections open.
    code = ("import sys; sys.path.insert(0, sys.argv[1]); "
            "from update_index import _guard_worker; _guard_worker(sys.argv[2], sys.argv[3])")
    worker = subprocess.Popen([sys.executable, "-c", code, str(Path(__file__).resolve().parent),
                               str(Path(db).resolve()), expected_digest or ""],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, encoding="utf-8")
    def receive(expected):
        try:
            line = worker.stdout.readline()
            if not line:
                raise ValueError("empty response")
            packet = json.loads(line)
        except (OSError, ValueError) as exc:
            raise RuntimeError("索引替換鎖程序中斷，狀態不確定；請停止更新並檢查目的地") from exc
        if not packet.get(expected):
            error = packet.get("error", "無法取得索引替換鎖")
            if packet.get("kind") == "sqlite":
                raise sqlite3.OperationalError(error)
            if packet.get("kind") == "value":
                raise ValueError(error)
            raise OSError(error)
        return packet

    def replace(candidate):
        try:
            worker.stdin.write(json.dumps({"candidate": str(Path(candidate).resolve())}) + "\n")
            worker.stdin.flush()
        except OSError as exc:
            raise RuntimeError("索引替換鎖程序中斷，狀態不確定；請停止更新並檢查目的地") from exc
        packet = receive("replaced")
        return packet.get("digest")

    try:
        receive("ready")
        yield replace
    finally:
        if worker.poll() is None:
            try:
                worker.stdin.write("\n")
                worker.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
        try:
            output, errors = worker.communicate(timeout=30)
        except subprocess.TimeoutExpired as exc:
            worker.kill()
            worker.communicate()
            raise RuntimeError("索引替換鎖程序逾時，狀態不確定；請停止更新並檢查目的地") from exc
        if worker.returncode and sys.exc_info()[0] is None:
            raise RuntimeError(f"索引替換鎖程序失敗，狀態不確定；請停止更新並檢查目的地：{output or errors}")


def snapshot_file_digest(db):
    # A separate process may close its file descriptor without releasing any
    # SQLite locks held by this process on POSIX.
    code = """import json, sys
sys.path.insert(0, sys.argv[1])
from update_index import file_digest
with open(sys.argv[2], 'rb') as stream:
    header = stream.read(20)
    digest = file_digest(stream).hex()
print(json.dumps({'header': header.hex(), 'digest': digest}))
"""
    result = subprocess.run([sys.executable, "-c", code, str(Path(__file__).resolve().parent),
                             str(Path(db).resolve())], check=True, capture_output=True, text=True, encoding="utf-8")
    packet = json.loads(result.stdout)
    return bytes.fromhex(packet["header"]), packet["digest"]


def verify_destination(db, candidate_digest, candidate_meta):
    # Reopen in a fresh process after the replacement handle closes. Hash and
    # read metadata in the same SQLite read transaction.
    code = """import json, sqlite3, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from update_index import file_digest
path = Path(sys.argv[2]).resolve()
con = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=0)
try:
    con.execute('BEGIN')
    meta = {k: json.loads(v) for k, v in con.execute('SELECT key,value FROM meta')}
    with path.open('rb') as stream:
        digest = file_digest(stream).hex()
    print(json.dumps({'meta': meta, 'digest': digest}))
finally:
    con.close()
"""
    try:
        result = subprocess.run([sys.executable, "-c", code, str(Path(__file__).resolve().parent),
                                 str(Path(db).resolve())], check=True, capture_output=True, text=True, encoding="utf-8")
        actual = json.loads(result.stdout)
        if actual["digest"] != candidate_digest or actual["meta"] != candidate_meta:
            raise ValueError("目的地與候選檔不符")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("索引可能已替換，狀態不確定；請停止更新並檢查目的地") from exc


def replace_candidate(candidate, db):
    if os.name != "nt":
        os.replace(candidate, db)
        return
    # Windows MoveFileEx cannot replace a target with a locked handle. POSIX
    # rename semantics permit it while preserving the old handle and its lock.
    import ctypes
    from ctypes import wintypes

    class RenameInfo(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("RootDirectory", wintypes.HANDLE),
                    ("FileNameLength", wintypes.DWORD), ("FileName", wintypes.WCHAR * 1)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.SetFileInformationByHandle.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.CreateFileW(str(Path(candidate).resolve()), 0x10000, 7, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        filename = str(Path(db).resolve()).encode("utf-16le")
        buffer = ctypes.create_string_buffer(RenameInfo.FileName.offset + len(filename) + 2)
        info = ctypes.cast(buffer, ctypes.POINTER(RenameInfo))
        info.contents.Flags = 3  # REPLACE_IF_EXISTS | POSIX_SEMANTICS
        info.contents.RootDirectory = None
        info.contents.FileNameLength = len(filename)
        ctypes.memmove(ctypes.addressof(buffer) + RenameInfo.FileName.offset, filename, len(filename))
        if not kernel.SetFileInformationByHandle(handle, 22, buffer, len(buffer)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(handle)


def _seed_info(connection):
    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise ValueError("舊索引的 SQLite 完整性檢查失敗")
    meta = metadata(connection)
    embedding_text_version(meta)
    count = connection.execute("SELECT count(*) FROM questions").fetchone()[0]
    pending = connection.execute("SELECT count(*) FROM vectors WHERE embedding IS NULL").fetchone()[0]
    pending_questions = pending_vector_questions(meta)
    missing = connection.execute(
        "SELECT count(*) FROM questions q WHERE NOT EXISTS "
        "(SELECT 1 FROM question_vectors v WHERE v.question_id=q.question_id "
        "AND substr(v.vector_id,1,length(q.question_id)+3)='q:' || q.question_id || ':')"
    ).fetchone()[0]
    invalid_links = connection.execute(
        "SELECT count(*) FROM question_vectors v LEFT JOIN questions q ON q.question_id=v.question_id "
        "LEFT JOIN vectors x ON x.vector_id=v.vector_id WHERE q.question_id IS NULL OR x.vector_id IS NULL"
    ).fetchone()[0]
    schema = meta.get("schema_version")
    if (type(schema) is not int or schema != SCHEMA_VERSION or meta.get("model") != MODEL
            or not meta.get("dimension") or not count or pending or pending_questions or missing or invalid_links):
        raise ValueError("舊索引不完整或模型/schema 不符；請先用本機 GPU 建立完整索引")
    if "model_revision" in meta:
        validate_model_revision(meta["model"], meta["model_revision"])
    ids, paths = set(), set()
    for identifier, document in connection.execute("SELECT question_id, doc_json FROM questions"):
        ids.add(identifier)
        paths.update(item["path"] for item in json.loads(document).get("appears_in", []) if item.get("path"))
    if not paths:
        raise ValueError("舊索引缺少考卷出處；請先用本機 GPU 建立完整索引")
    return meta, ids, paths


def seed_info(db):
    with closing(open_index(db)) as connection:
        return _seed_info(connection)


def update(root, db, *, catalog=None, catalog_out=None, device="cpu", batch_size=8,
           embedder_factory=None):
    with retryable_sqlite_errors():
        with index_write_lock(db):
            return _update(root, db, catalog=catalog, catalog_out=catalog_out, device=device,
                           batch_size=batch_size, embedder_factory=embedder_factory)


def _update(root, db, *, catalog, catalog_out, device, batch_size, embedder_factory):
    root, db = Path(root), Path(db)
    catalog = Path(catalog) if catalog else root / "rag/moex_catalog.json"
    with closing(open_index(db)) as source:
        source.execute("BEGIN")
        meta, old_ids, old_paths = _seed_info(source)
        initial_header, initial_digest = snapshot_file_digest(db)
    papers = sorted((root / "考古題庫").glob("*/*/*/試題.json"))
    if not papers:
        raise ValueError("沒有考古題；拒絕清空既有索引")
    years = {int(p.parent.parent.name[:-1]) for p in papers
             if p.parent.parent.name.endswith("年") and p.parent.parent.name[:-1].isdigit()}
    original_catalog = json.loads(catalog.read_text(encoding="utf-8-sig"))
    if original_catalog.get("schema_version") != 1:
        raise ValueError("考選部目錄 schema 不符")
    missing_years = years - {entry["year"] for entry in original_catalog["entries"]}
    archive = root / "考古題庫"
    new_paper_years = {
        int(p.parent.parent.name[:-1]) for p in papers
        if p.parent.relative_to(archive).as_posix() not in old_paths
        and p.parent.parent.name.endswith("年") and p.parent.parent.name[:-1].isdigit()
        and json.loads(p.read_text(encoding="utf-8-sig")).get("questions")
    }
    refresh_years = sorted(missing_years | new_paper_years)

    with tempfile.TemporaryDirectory(prefix=".rag-update-", dir=db.parent) as temporary:
        temp = Path(temporary)
        combined = original_catalog
        if refresh_years:
            from urllib.parse import parse_qs, urlsplit
            fresh, _ = fetch_catalog(temp, years=refresh_years)
            old_pages = [p for p in original_catalog["pages"]
                         if int(parse_qs(urlsplit(p["url"]).query)["y"][0]) - 1911 not in refresh_years]
            combined = {
                "schema_version": 1,
                "pages": sorted(old_pages + fresh["pages"], key=lambda p: p["url"]),
                "entries": sorted([e for e in original_catalog["entries"] if e["year"] not in refresh_years]
                                  + fresh["entries"],
                                  key=lambda x: (x["exam_code"], x["category_code"], x["subject_code"],
                                                 x["question_pdf_url"] or "", x["answer_pdf_url"] or "")),
            }
        new_catalog = temp / "moex_catalog.json"
        write_json(new_catalog, combined)
        source_map, _ = build_source_map(root, catalog_path=new_catalog)
        source_path = temp / "source_map.json"
        write_json(source_path, source_map)
        corpus, stats = build_corpus(root / "考古題庫", source_path)
        if not old_ids.intersection(record["question_id"] for record in corpus):
            raise ValueError("新語料與舊索引沒有共同題目；拒絕全量重建")
        corpus_path = temp / "corpus.jsonl"
        with corpus_path.open("w", encoding="utf-8", newline="\n") as stream:
            for record in corpus:
                stream.write(json_text(record) + "\n")

        candidate = temp / db.name
        with closing(open_index(db)) as source, closing(sqlite3.connect(candidate)) as target:
            # Hold the same SQLite read snapshot for backup and physical hash.
            source.execute("BEGIN")
            source.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
            header, seed_digest = snapshot_file_digest(db)
            if seed_digest != initial_digest:
                raise ValueError("來源索引已變更；請保留原檔並安全重試")
            source.backup(target)
            rollback_snapshot = (len(initial_header) >= 20 and initial_header[:16] == b"SQLite format 3\x00"
                                 and initial_header[18:20] == b"\x01\x01"
                                 and len(header) >= 20 and header[:16] == b"SQLite format 3\x00"
                                 and header[18:20] == b"\x01\x01")
        result = build_index(corpus_path, candidate, model=MODEL, device=device,
                             batch_size=batch_size, embedder_factory=embedder_factory)
        candidate_meta, _, _ = seed_info(candidate)
        if candidate_meta.get("model_identity") != meta.get("model_identity"):
            raise ValueError("候選索引的模型身分與原索引不一致；拒絕替換")
        if (("model_revision" in candidate_meta) != ("model_revision" in meta)
                or candidate_meta.get("model_revision") != meta.get("model_revision")):
            raise ValueError("候選索引的模型 revision 與原索引不一致；拒絕替換")
        if result["index_changed"] and embedding_text_version(candidate_meta) != EMBEDDING_TEXT_VERSION:
            raise ValueError("候選索引尚未完成向量輸入規則遷移")
        changed = result["index_changed"]
        if changed:
            if not rollback_snapshot:
                raise ValueError("備份時索引使用 WAL；拒絕替換，請保留原檔")
            with replacement_guard(db, seed_digest) as replace:
                candidate_digest = replace(candidate)
            verify_destination(db, candidate_digest, candidate_meta)
        if catalog_out:
            output = Path(catalog_out)
            output.parent.mkdir(parents=True, exist_ok=True)
            data = new_catalog.read_bytes()
            if not output.exists() or output.read_bytes() != data:
                output.write_bytes(data)
        return {**result, "index_changed": changed, "catalog_added_years": sorted(missing_years),
                "catalog_refreshed_years": refresh_years,
                "catalog_changed": combined != original_catalog,
                "questions": stats["deduplicated_question_count"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--db", type=Path, required=True, help="Existing complete BGE-M3 SQLite index")
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--catalog-out", type=Path)
    parser.add_argument("--device", choices=("cpu", "cuda", "auto"), default="cpu")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        result = update(args.root, args.db, catalog=args.catalog, catalog_out=args.catalog_out,
                        device=args.device, batch_size=args.batch_size)
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"增量更新失敗：{exc}\n")
    output = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
