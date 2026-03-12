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
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "exam.db"
DATA_DIR = Path(__file__).resolve().parent / "考古題庫"


class ExamDB:
    """考古題資料庫查詢介面"""

    def __init__(self, db_path=None):
        self.db_path = str(db_path or DB_PATH)
        if not os.path.exists(self.db_path):
            print(f"索引不存在，正在建立: {self.db_path}")
            self.build()
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def build(self):
        """建立 SQLite 索引"""
        conn = sqlite3.connect(self.db_path)
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
                FOREIGN KEY (file_id) REFERENCES files(id)
            );
        """)

        files = glob.glob(str(DATA_DIR / "**" / "試題.json"), recursive=True)
        file_id = 0
        q_count = 0

        for fp in files:
            with open(fp, 'r', encoding='utf-8') as f:
                d = json.load(f)

            if d.get('metadata', {}).get('_is_duplicate'):
                continue

            file_id += 1
            meta = d.get('metadata', {})

            # 從路徑推斷 category 和 year
            rel = os.path.relpath(fp, str(DATA_DIR))
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
                q_count += 1
                opts = q.get('options', {})
                c.execute(
                    "INSERT INTO questions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (q_count, file_id, str(q.get('number', '')),
                     q.get('type', ''), q.get('stem', ''),
                     opts.get('A', ''), opts.get('B', ''),
                     opts.get('C', ''), opts.get('D', ''),
                     q.get('answer', ''), q.get('passage', ''),
                     q.get('section', ''))
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
        conn.close()
        db_size = os.path.getsize(self.db_path)
        print(f"索引建立完成: {file_id} 個檔案, {q_count} 題, {db_size/1024/1024:.1f} MB")

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
        return [dict(r) for r in rows]

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
    if q['type'] == 'choice':
        for letter in 'ABCD':
            val = q.get(f'option_{letter.lower()}', '')
            marker = " ★" if q.get('answer') == letter else ""
            lines.append(f"  ({letter}) {val}{marker}")
        lines.append(f"答案: {q['answer']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='考古題資料庫查詢工具')
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

    # stats
    sub.add_parser('stats', help='統計摘要')

    # random
    rp = sub.add_parser('random', help='隨機抽題')
    rp.add_argument('--count', '-n', type=int, default=5, help='抽題數量')
    rp.add_argument('--year', '-y', type=int, help='年份')
    rp.add_argument('--subject', '-s', help='科目')

    args = parser.parse_args()

    if args.command == 'build':
        db = ExamDB()
        db.close()

    elif args.command == 'query':
        with ExamDB() as db:
            results = db.search(
                keyword=args.keyword, year=args.year,
                category=args.category, subject=args.subject,
                answer=args.answer, qtype=args.type, limit=args.limit
            )
            print(f"找到 {len(results)} 題：\n")
            for q in results:
                print(format_question(q))
                print("─" * 60)

    elif args.command == 'stats':
        with ExamDB() as db:
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
        with ExamDB() as db:
            results = db.random(n=args.count, year=args.year, subject=args.subject)
            print(f"隨機 {len(results)} 題：\n")
            for q in results:
                print(format_question(q))
                print("─" * 60)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
