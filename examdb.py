#!/usr/bin/env python3
"""考古題資料庫查詢 API + SQLite 索引

用法:
    # 建立/更新索引
    python examdb.py build

    # 命令列查詢
    python examdb.py query --year 112 --keyword "基本權"
    python examdb.py query --subject "憲法" --answer D
    python examdb.py query --category "行政警察" --year 110
    python examdb.py stats

    # Python API
    from examdb import ExamDB
    db = ExamDB()
    results = db.search(year=112, keyword="基本權")
"""

import json
import glob
import sqlite3
import os
import re
import sys
import argparse
import tempfile
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "exam.db"
DATA_DIR = Path(__file__).resolve().parent / "考古題庫"


def _resolve_data_dir(override: str | None = None) -> Path:
    """資料來源根目錄：CLI override > 環境變數 EXAMDB_DATA_DIR > 預設 考古題庫/。"""
    if override:
        return Path(override).resolve()
    env = os.environ.get("EXAMDB_DATA_DIR")
    if env:
        return Path(env).resolve()
    return DATA_DIR


class ExamDB:
    """考古題資料庫查詢介面"""

    def __init__(self, db_path=None, data_dir=None, rebuild=False):
        self.db_path = str(db_path or DB_PATH)
        self.data_dir = _resolve_data_dir(data_dir)
        if rebuild or not os.path.exists(self.db_path):
            print(f"正在建立索引: {self.db_path}", file=sys.stderr)
            self.build()
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        try:
            self._ensure_schema()
        except Exception:
            if self.conn is not None:
                self.conn.close()
            raise

    def _ensure_schema(self):
        """以完整新索引升級舊圖片 schema；失敗時保留可用的原始索引。"""
        self._assert_generated_cache(self.conn)
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(questions)")}
        if {"option_images", "source_locator"}.issubset(columns):
            return
        self.build()

    @staticmethod
    def _assert_generated_cache(conn):
        """僅能取代本工具的可重建索引；未知 schema 可能包含使用者資料。"""
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}
        expected_files = {"id", "path", "category", "year", "subject", "exam_name", "level"}
        expected_questions = {"id", "file_id", "number", "type", "stem", "option_a", "option_b",
                              "option_c", "option_d", "answer", "passage", "section"}
        files = {row[1] for row in conn.execute("PRAGMA table_info(files)")}
        questions = {row[1] for row in conn.execute("PRAGMA table_info(questions)")}
        if tables != {"files", "questions"} or files != expected_files or not (
            expected_questions <= questions <= expected_questions | {"option_images", "source_locator"}
        ):
            raise RuntimeError("索引包含未知資料表或欄位，拒絕自動重建並保留原始資料庫")
        known_indexes = {"idx_q_type", "idx_q_answer", "idx_q_file", "idx_f_category", "idx_f_year", "idx_f_subject"}
        for kind, name in conn.execute(
            "SELECT type, name FROM sqlite_master WHERE type IN ('view','trigger','index')"
        ):
            if kind != "index" or (not name.startswith("sqlite_") and name not in known_indexes):
                raise RuntimeError("索引包含未知 schema 物件，拒絕重建並保留原始資料庫")

    def close(self):
        if self.conn is not None:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def build(self):
        """完整暫存索引通過後才原子取代；來源/SQLite 失敗不修改既有索引。"""
        files = sorted(glob.glob(str(self.data_dir / "**" / "試題.json"), recursive=True))
        if not files:
            raise RuntimeError("缺少原始題庫來源，拒絕建立或升級索引")
        previous_questions = 0
        if os.path.exists(self.db_path):
            with closing(sqlite3.connect(self.db_path)) as previous:
                self._assert_generated_cache(previous)
                sources = {Path(fp).resolve() for fp in files}
                relative_sources = {Path(fp).resolve().relative_to(self.data_dir).as_posix() for fp in files}
                for path, category in previous.execute("SELECT path, category FROM files"):
                    if Path(path).resolve() in sources:
                        continue
                    # Old caches can move between clones. Preserve the category-relative
                    # source locator rather than requiring the old machine's absolute root.
                    parts = str(path).replace("\\", "/").split("/")
                    matches = {"/".join(parts[i:]) for i, part in enumerate(parts) if part == category} & relative_sources
                    if len(matches) != 1:
                        raise RuntimeError("原始題庫來源不完整，拒絕重建並保留原始資料庫")
                previous_questions = previous.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        descriptor, temporary = tempfile.mkstemp(prefix="exam-schema-", suffix=".db", dir=Path(self.db_path).parent)
        os.close(descriptor)
        connected = getattr(self, "conn", None) is not None
        try:
            file_count, question_count = self._write_index(temporary, files)
            if not file_count or (previous_questions and not question_count):
                raise RuntimeError("原始題庫沒有可重建題目，拒絕取代既有索引")
            if connected:
                self.conn.close()
                self.conn = None
            os.replace(temporary, self.db_path)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
            if connected and self.conn is None:
                self.conn = sqlite3.connect(self.db_path)
                self.conn.row_factory = sqlite3.Row
        db_size = os.path.getsize(self.db_path)
        print(f"索引建立完成: {file_count} 個檔案, {question_count} 題, {db_size/1024/1024:.1f} MB", file=sys.stderr)

    def _write_index(self, db_path, files):
        """寫入隔離暫存檔；closing 在解析或 SQL 例外時也會釋放 Windows 檔案 handle。"""
        with closing(sqlite3.connect(db_path)) as conn:
            return self._populate_index(conn, files)

    def _populate_index(self, conn, files):
        c = conn.cursor()

        c.executescript("""
            DROP TABLE IF EXISTS questions;
            DROP TABLE IF EXISTS files;

            CREATE TABLE files (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL,
                category TEXT,
                year INTEGER,
                subject TEXT,
                exam_name TEXT,
                level TEXT
            );

            CREATE TABLE questions (
                id INTEGER PRIMARY KEY,
                file_id INTEGER NOT NULL,
                number TEXT,
                type TEXT NOT NULL,
                stem TEXT,
                option_a TEXT,
                option_b TEXT,
                option_c TEXT,
                option_d TEXT,
                answer TEXT,
                passage TEXT,
                section TEXT,
                option_images TEXT,
                source_locator TEXT,
                FOREIGN KEY (file_id) REFERENCES files(id)
            );
        """)

        file_id = 0
        q_count = 0

        for fp in files:
            with open(fp, 'r', encoding='utf-8') as f:
                d = json.load(f)

            if not isinstance(d, dict) or not isinstance(d.get('metadata', {}), dict) or not isinstance(d.get('questions'), list):
                raise ValueError(f"題庫 JSON 格式錯誤: {fp}")

            if d.get('metadata', {}).get('_is_duplicate'):
                continue

            file_id += 1
            meta = d.get('metadata', {})

            # 從路徑推斷 category 和 year
            rel = os.path.relpath(fp, str(self.data_dir))
            parts = rel.replace(os.sep, '/').split('/')
            category = parts[0] if len(parts) > 0 else ''
            year_str = parts[1].replace('年', '') if len(parts) > 1 else ''
            year = int(year_str) if year_str.isdigit() else None
            subject = meta.get('subject') or (parts[2] if len(parts) > 2 else '')

            c.execute(
                "INSERT INTO files VALUES (?,?,?,?,?,?,?)",
                (file_id, fp, category, year, subject,
                 meta.get('exam_name', ''), meta.get('level', ''))
            )

            for q in d.get('questions', []):
                if not isinstance(q, dict) or not isinstance(q.get('options', {}), dict):
                    raise ValueError(f"題目 JSON 格式錯誤: {fp}")
                for field in ('option_images', 'source_locator'):
                    if q.get(field) is not None and not isinstance(q[field], dict):
                        raise ValueError(f"{field} 必須為 JSON 物件: {fp}")
                q_count += 1
                opts = q.get('options', {})
                # answer 可能是 str / list (多答案) / None (送分) → 統一字串
                ans = q.get('answer')
                if isinstance(ans, list):
                    ans = ','.join(ans)
                elif ans is None:
                    ans = ''
                c.execute(
                    "INSERT INTO questions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (q_count, file_id, str(q.get('number', '')),
                     q.get('type', ''), q.get('stem', ''),
                     opts.get('A', ''), opts.get('B', ''),
                     opts.get('C', ''), opts.get('D', ''),
                     ans, q.get('passage', ''),
                     q.get('section', ''),
                     json.dumps(q['option_images'], ensure_ascii=False) if 'option_images' in q else None,
                     json.dumps(q['source_locator'], ensure_ascii=False) if 'source_locator' in q else None)
                )

        # 建立索引
        c.executescript("""
            CREATE INDEX idx_q_type ON questions(type);
            CREATE INDEX idx_q_answer ON questions(answer);
            CREATE INDEX idx_q_file ON questions(file_id);
            CREATE INDEX idx_f_category ON files(category);
            CREATE INDEX idx_f_year ON files(year);
            CREATE INDEX idx_f_subject ON files(subject);
        """)

        conn.commit()
        return file_id, q_count

    def search(self, keyword=None, year=None, category=None, subject=None,
               answer=None, qtype='choice', limit=50):
        """搜尋題目

        Args:
            keyword: 搜尋題幹/選項/段落中的關鍵字
            year: 年份 (e.g., 112)
            category: 學系/類別 (e.g., "行政警察")
            subject: 科目關鍵字 (e.g., "憲法")
            answer: 答案 (A/B/C/D/送分)
            qtype: 題目類型 (choice/essay/None=全部)
            limit: 回傳上限

        Returns:
            list of dict
        """
        conditions = []
        params = []

        if qtype:
            conditions.append("q.type = ?")
            params.append(qtype)
        if year:
            conditions.append("f.year = ?")
            params.append(year)
        if category:
            conditions.append("f.category LIKE ?")
            params.append(f"%{category}%")
        if subject:
            conditions.append("f.subject LIKE ?")
            params.append(f"%{subject}%")
        if answer:
            conditions.append("q.answer = ?")
            params.append(answer)
        if keyword:
            conditions.append(
                "(q.stem LIKE ? OR q.option_a LIKE ? OR q.option_b LIKE ? "
                "OR q.option_c LIKE ? OR q.option_d LIKE ? OR q.passage LIKE ?)"
            )
            kw = f"%{keyword}%"
            params.extend([kw] * 6)

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""
            SELECT q.*, f.category, f.year, f.subject, f.exam_name, f.level
            FROM questions q JOIN files f ON q.file_id = f.id
            WHERE {where}
            ORDER BY f.year DESC, f.category, q.number
            LIMIT ?
        """
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            for field in ('option_images', 'source_locator'):
                if item[field] is not None:
                    item[field] = json.loads(item[field])
            results.append(item)
        return results

    def stats(self):
        """統計摘要"""
        c = self.conn
        result = {}

        row = c.execute("SELECT COUNT(*) FROM files").fetchone()
        result['files'] = row[0]

        row = c.execute("SELECT COUNT(*) FROM questions").fetchone()
        result['total_questions'] = row[0]

        row = c.execute("SELECT COUNT(*) FROM questions WHERE type='choice'").fetchone()
        result['choice'] = row[0]

        row = c.execute("SELECT COUNT(*) FROM questions WHERE type='essay'").fetchone()
        result['essay'] = row[0]

        rows = c.execute(
            "SELECT year, COUNT(*) FROM files GROUP BY year ORDER BY year"
        ).fetchall()
        result['by_year'] = {r[0]: r[1] for r in rows}

        rows = c.execute(
            "SELECT category, COUNT(*) FROM files GROUP BY category ORDER BY COUNT(*) DESC"
        ).fetchall()
        result['by_category'] = {r[0]: r[1] for r in rows}

        rows = c.execute(
            "SELECT answer, COUNT(*) FROM questions WHERE type='choice' "
            "GROUP BY answer ORDER BY COUNT(*) DESC"
        ).fetchall()
        result['answer_dist'] = {r[0]: r[1] for r in rows}

        return result

    def random(self, n=1, **kwargs):
        """隨機抽題"""
        kwargs['limit'] = 1000  # Get a pool first
        pool = self.search(**kwargs)
        import random
        return random.sample(pool, min(n, len(pool)))


def format_question(q):
    """格式化題目為可讀文字"""
    lines = []
    lines.append(f"[{q['category']} {q['year']}年 {q['subject']}]")
    lines.append(f"Q{q['number']} ({q['type']})")
    if q.get('passage'):
        lines.append(f"段落: {q['passage'][:100]}...")
    lines.append(f"題幹: {q['stem']}")
    images = q.get('option_images') or {}
    locator = q.get('source_locator') or {}
    if isinstance(images, str):
        images = json.loads(images)
    if isinstance(locator, str):
        locator = json.loads(locator)
    if q['type'] == 'choice':
        for letter in 'ABCD':
            val = q.get(f'option_{letter.lower()}', '')
            marker = " ★" if q.get('answer') == letter else ""
            lines.append(f"  ({letter}) {val}{marker}")
            image = images.get(letter)
            if image:
                reference = image.get('public_src') or image.get('src') or ''
                lines.append(f"      圖片: {reference}")
                if image.get('src') and image.get('src') != reference:
                    lines.append(f"      原始圖片: {image['src']}")
                if image.get('alt'):
                    lines.append(f"      圖片說明: {image['alt']}")
        lines.append(f"答案: {q['answer']}")
    if locator:
        if locator.get('url'):
            lines.append(f"原始來源 URL: {locator['url']}")
        if locator.get('pdf'):
            lines.append(f"來源 PDF: {locator['pdf']}")
        if locator.get('page') is not None:
            lines.append(f"來源頁碼: {locator['page']}")
        if locator.get('pdf_sha256'):
            lines.append(f"來源 SHA-256: {locator['pdf_sha256']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='考古題資料庫查詢工具')
    parser.add_argument(
        '--data-dir', default=None,
        help='資料來源根目錄（也可用環境變數 EXAMDB_DATA_DIR）。'
             '預設 考古題庫/，可改成 cache/full_out',
    )
    parser.add_argument(
        '--db', default=None,
        help='SQLite 索引路徑（預設 exam.db）',
    )
    sub = parser.add_subparsers(dest='command')

    # build
    sub.add_parser('build', help='建立/更新 SQLite 索引')

    # query
    qp = sub.add_parser('query', help='查詢題目')
    qp.add_argument('--keyword', '-k', help='關鍵字')
    qp.add_argument('--year', '-y', type=int, help='年份')
    qp.add_argument('--category', '-c', help='學系/類別')
    qp.add_argument('--subject', '-s', help='科目')
    qp.add_argument('--answer', '-a', help='答案')
    qp.add_argument('--type', '-t', default='choice', help='題型 (choice/essay)')
    qp.add_argument('--limit', '-n', type=int, default=10, help='顯示數量')
    qp.add_argument('--json', action='store_true', help='輸出完整題目 JSON（含圖片與來源）')

    # stats
    sub.add_parser('stats', help='統計摘要')

    # random
    rp = sub.add_parser('random', help='隨機抽題')
    rp.add_argument('--count', '-n', type=int, default=5, help='抽題數量')
    rp.add_argument('--year', '-y', type=int, help='年份')
    rp.add_argument('--subject', '-s', help='科目')
    rp.add_argument('--json', action='store_true', help='輸出完整題目 JSON（含圖片與來源）')

    args = parser.parse_args()

    if args.command == 'build':
        # Build completes in isolation before replacing any existing generated cache.
        db_path = args.db or DB_PATH
        db = ExamDB(db_path=db_path, data_dir=args.data_dir, rebuild=True)
        db.close()

    elif args.command == 'query':
        with ExamDB(db_path=args.db, data_dir=args.data_dir) as db:
            results = db.search(
                keyword=args.keyword, year=args.year,
                category=args.category, subject=args.subject,
                answer=args.answer, qtype=args.type, limit=args.limit
            )
            if args.json:
                print(json.dumps(results, ensure_ascii=False))
            else:
                print(f"找到 {len(results)} 題：\n")
                for q in results:
                    print(format_question(q))
                    print("─" * 60)

    elif args.command == 'stats':
        with ExamDB(db_path=args.db, data_dir=args.data_dir) as db:
            s = db.stats()
            print(f"檔案: {s['files']}")
            print(f"總題數: {s['total_questions']} (選擇: {s['choice']}, 申論: {s['essay']})")
            print(f"\n各年檔案數:")
            for y, c in sorted(s['by_year'].items()):
                print(f"  {y}年: {c}")
            print(f"\n答案分佈:")
            for a, c in s['answer_dist'].items():
                print(f"  {a}: {c}")

    elif args.command == 'random':
        with ExamDB(db_path=args.db, data_dir=args.data_dir) as db:
            results = db.random(n=args.count, year=args.year, subject=args.subject)
            if args.json:
                print(json.dumps(results, ensure_ascii=False))
            else:
                print(f"隨機 {len(results)} 題：\n")
                for q in results:
                    print(format_question(q))
                    print("─" * 60)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
