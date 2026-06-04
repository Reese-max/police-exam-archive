#!/usr/bin/env python3
"""
克漏字題目本文補丁（in-place HTML 修補）

問題：克漏字題（stem 是「請依下文回答第X題至第Y題」instruction）在 SSG 渲染時
       只剩 <span class="q-number">N</span>，沒有題本文。使用者翻到第 N 題只看到
       光禿禿題號 + ABCD 選項，不知道在問什麼。

對策：從同一 q-block 上方最近的 reading-passage，找該題號 N 作為空格 token 的位置，
       切前後約 ±150 字當題本文，空格用 ___ 標示。

範圍：對所有 考古題網站/<類科>/<類科>考古題總覽.html in-place 修改。
       支援 --dry-run 印 diff、--single 指定單檔、--target 指定根目錄。
"""
import re
import argparse
import sys
from pathlib import Path
from html import escape as h

DEFAULT_ROOT = Path(r"D:/Users/Administrator/Desktop/考古題下載/考古題網站")

PASSAGE_OPEN_RE = re.compile(r'<div class="reading-passage">')
PASSAGE_CLOSE_RE = re.compile(r'</div>')
EMPTY_Q_RE = re.compile(
    r'^(\s*)<div class="mc-question"([^>]*)><span class="q-number">(\d+)</span></div>\s*$'
)

INSTRUCTION_HEADER_RE = re.compile(
    r'^請依下文回答第\s*\d+\s*題至第\s*\d+\s*題\s*'
)
TAG_RE = re.compile(r'<[^>]+>')


def passage_html_to_text(passage_html: str) -> str:
    """剝掉 <strong class="passage-qnum">N</strong> 等 tag，還原純文字。"""
    return TAG_RE.sub('', passage_html)


_UNDERSCORE_BLANK_RE = re.compile(r'_+\s*(\d+)\s*_+')


def extract_cloze_context(passage_text: str, qnum: int, ctx_chars: int = 150) -> str:
    """從 passage 抽出第 qnum 個空格位置前後 ±ctx_chars 字當題本文。"""
    if not passage_text:
        return ''

    # 部分 passage 用 __N__ 標記空格——normalize 掉兩側 underscore，避免殘留
    passage_text = _UNDERSCORE_BLANK_RE.sub(r' \1 ', passage_text)

    header = INSTRUCTION_HEADER_RE.match(passage_text)
    search_start = header.end() if header else 0

    pat = re.compile(r'(?<!\d)' + str(qnum) + r'(?!\d)')
    m = pat.search(passage_text, search_start)
    if not m:
        return ''

    pos, end = m.start(), m.end()
    left_start = max(search_start, pos - ctx_chars)
    right_end = min(len(passage_text), end + ctx_chars)

    if left_start > search_start:
        sp = passage_text.find(' ', left_start, pos)
        if 0 <= sp < pos:
            left_start = sp + 1
    if right_end < len(passage_text):
        sp = passage_text.rfind(' ', end, right_end)
        if sp > end:
            right_end = sp

    left = passage_text[left_start:pos].rstrip()
    right = passage_text[end:right_end].lstrip()

    blank = '___'
    prefix = '' if left_start <= search_start + 1 else '… '
    suffix = '' if right_end >= len(passage_text) - 1 else ' …'

    body = f'{left} {blank} {right}'.strip()
    return f'{prefix}{body}{suffix}'


def fix_html(text: str) -> tuple[str, int]:
    """逐行掃；reading-passage 可跨多行——用 state buffer 累積到 </div>。
    遇 empty mc-question 從最近 passage 切 context 注入 q-text。"""
    lines = text.splitlines(keepends=True)
    current_passage = None
    in_passage = False
    passage_buf = []
    fixed_count = 0
    out = []

    for line in lines:
        if in_passage:
            passage_buf.append(line)
            if PASSAGE_CLOSE_RE.search(line):
                joined = ''.join(passage_buf)
                inner_match = re.search(
                    r'<div class="reading-passage">(.*?)</div>',
                    joined, re.DOTALL,
                )
                if inner_match:
                    current_passage = passage_html_to_text(inner_match.group(1))
                in_passage = False
                passage_buf = []
            out.append(line)
            continue

        if PASSAGE_OPEN_RE.search(line):
            close_after_open = re.search(
                r'<div class="reading-passage">(.*?)</div>', line, re.DOTALL,
            )
            if close_after_open:
                current_passage = passage_html_to_text(close_after_open.group(1))
            else:
                in_passage = True
                passage_buf = [line]
            out.append(line)
            continue

        stripped = line.rstrip('\n').rstrip('\r')
        em = EMPTY_Q_RE.match(stripped)
        if em and current_passage:
            indent = em.group(1)
            attrs = em.group(2)
            qnum = int(em.group(3))
            context = extract_cloze_context(current_passage, qnum)
            if context:
                eol = line[len(stripped):]
                new_line = (
                    f'{indent}<div class="mc-question"{attrs}>'
                    f'<span class="q-number">{qnum}</span>'
                    f'<span class="q-text">{h(context)}</span>'
                    f'</div>{eol}'
                )
                out.append(new_line)
                fixed_count += 1
                continue

        out.append(line)

    return ''.join(out), fixed_count


def process_file(path: Path, dry_run: bool = False) -> int:
    text = path.read_text(encoding='utf-8')
    new_text, count = fix_html(text)
    if count == 0:
        return 0
    if dry_run:
        print(f'[DRY] {path.name}: would fix {count} cloze items')
    else:
        path.write_text(new_text, encoding='utf-8')
        print(f'[OK]  {path.name}: fixed {count} cloze items')
    return count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--target', type=Path, default=DEFAULT_ROOT,
                    help='考古題網站 根目錄')
    ap.add_argument('--single', type=Path, default=None,
                    help='只處理單一 HTML 檔（覆蓋 --target glob）')
    ap.add_argument('--dry-run', action='store_true',
                    help='不改檔，只印影響範圍')
    args = ap.parse_args()

    if args.single:
        files = [args.single]
    else:
        files = sorted(args.target.glob('*/*考古題總覽.html'))

    if not files:
        print('no files matched', file=sys.stderr)
        sys.exit(1)

    total = 0
    for f in files:
        total += process_file(f, dry_run=args.dry_run)
    label = 'would fix' if args.dry_run else 'fixed'
    print(f'\nTOTAL {label}: {total} cloze items across {len(files)} files')


if __name__ == '__main__':
    main()
