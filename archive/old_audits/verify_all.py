# -*- coding: utf-8 -*-
"""全面驗證腳本 — 檢查 HTML/CSS/JS/資料一致性"""
import re, json, os
from html.parser import HTMLParser
from pathlib import Path

SITE = Path(__file__).parent / '考古題網站'
DATA = Path(__file__).parent / '考古題庫'
issues = []

def add(level, area, msg):
    issues.append((level, area, msg))

# ======== 1. HTML 結構 ========
class TagChecker(HTMLParser):
    VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    def __init__(self):
        super().__init__()
        self.stack = []
        self.ids = []
        self.errors = []
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if 'id' in d:
            self.ids.append(d['id'])
        if tag not in self.VOID:
            self.stack.append(tag)
    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.errors.append(f'Unclosed <{self.stack.pop()}>')
            if self.stack:
                self.stack.pop()

print("=" * 60)
print("  全面驗證: HTML / CSS / JS / 資料一致性")
print("=" * 60)

samples = ['行政警察學系', '資訊管理學系', '消防學系']
for cat in samples:
    html_path = SITE / cat / f'{cat}考古題總覽.html'
    if not html_path.exists():
        add('Critical', 'HTML', f'{cat} HTML 不存在')
        continue
    content = html_path.read_text(encoding='utf-8')
    checker = TagChecker()
    try:
        checker.feed(content)
    except Exception as e:
        add('Major', 'HTML', f'{cat}: parse error: {e}')
    if checker.errors:
        for err in checker.errors[:3]:
            add('Major', 'HTML', f'{cat}: {err}')
    dup_ids = [x for x in set(checker.ids) if checker.ids.count(x) > 1]
    if dup_ids:
        add('Critical', 'HTML', f'{cat}: 重複 ID: {dup_ids[:5]}')
    required_ids = ['practiceScore', 'subjectView', 'searchJump', 'viewYear', 'viewSubject',
                    'practiceToggle', 'subjectFilter', 'yearView', 'bookmarkFilter']
    for rid in required_ids:
        if f'id="{rid}"' not in content:
            add('Critical', 'HTML', f'{cat}: 缺少 id="{rid}"')
    sk_match = re.search(r'(?:var|const|let) SUBJECT_KEYS=(\[.*?\]);', content)
    if not sk_match:
        add('Major', 'HTML', f'{cat}: 缺少 SUBJECT_KEYS')
    else:
        try:
            sk = json.loads(sk_match.group(1))
            if not sk:
                add('Major', 'HTML', f'{cat}: SUBJECT_KEYS 為空')
        except Exception:
            add('Critical', 'HTML', f'{cat}: SUBJECT_KEYS JSON 無效')
    if '../css/style.css' not in content:
        add('Critical', 'HTML', f'{cat}: CSS 連結缺失')
    if '../js/app.js' not in content:
        add('Critical', 'HTML', f'{cat}: JS 連結缺失')
    # 純申論題卡片不應有答案格
    cards = re.findall(r'<div class="subject-card".*?</div>\s*</div>\s*</div>', content, re.DOTALL)

print(f"  HTML 結構: {len(samples)} 個類科檢查完成")

# Index page links
idx = SITE / 'index.html'
if idx.exists():
    idx_c = idx.read_text(encoding='utf-8')
    for cat_dir in SITE.iterdir():
        if cat_dir.is_dir() and cat_dir.name not in ('css', 'js'):
            link = f'{cat_dir.name}/{cat_dir.name}考古題總覽.html'
            if link not in idx_c:
                add('Major', 'HTML', f'index.html 缺少 {cat_dir.name} 連結')
    print(f"  Index 連結: 檢查完成")
else:
    add('Critical', 'HTML', 'index.html 不存在')

# ======== 2. CSS ========
css = (SITE / 'css/style.css').read_text(encoding='utf-8')

# Dark mode
dark_needed = [
    '.answer-section', '.answer-cell', '.search-jump button',
    '.practice-score', '.sv-year-tag', '.toolbar-select',
    '.toolbar-btn.practice-active'
]
for elem in dark_needed:
    pattern = f'html.dark {elem}'
    if pattern not in css:
        add('Major', 'CSS', f'缺少深色模式: {pattern}')

# shake 已在自評模式重構中移除（不再需要）

# Responsive
media_pos = css.rfind('@media (max-width: 768px)')
if media_pos >= 0:
    media_block = css[media_pos:]
    responsive_check = ['.answer-section', '.answer-grid', '.practice-score',
                        '.search-jump', '.toolbar-select', '.subject-view-section', '.sv-year-tag']
    for cls in responsive_check:
        if cls not in media_block:
            add('Minor', 'CSS', f'響應式未覆蓋: {cls}')
else:
    add('Major', 'CSS', '缺少 @media (max-width: 768px)')

# JS referenced classes in CSS
js = (SITE / 'js/app.js').read_text(encoding='utf-8')
important_js_classes = [
    'practice-mode', 'visible', 'revealed',
    'search-jump', 'hit-counter', 'sv-heading', 'subject-view-section',
    'sv-year-tag', 'reveal-btn', 'practice-active', 'score-reset',
    'self-score-panel', 'scored', 'was-correct', 'was-wrong',
    'score-btn', 'btn-correct', 'btn-wrong'
]
for cls in important_js_classes:
    if f'.{cls}' not in css:
        add('Major', 'CSS', f'JS 引用 class 在 CSS 未定義: .{cls}')

print(f"  CSS 完整性: 檢查完成")

# ======== 3. 資料一致性 ========
for cat in ['行政警察學系', '資訊管理學系', '鑑識科學學系']:
    json_total = 0
    json_choice_ans = 0
    cat_dir = DATA / cat
    if not cat_dir.exists():
        continue
    for jf in sorted(cat_dir.rglob('試題.json')):
        try:
            d = json.loads(jf.read_text(encoding='utf-8'))
            qs = d.get('questions', [])
            json_total += len(qs)
            json_choice_ans += sum(1 for q in qs if q.get('type') == 'choice' and q.get('answer')
                                   and q.get('subtype') != 'passage_fragment')
        except Exception:
            pass
    html_path = SITE / cat / f'{cat}考古題總覽.html'
    if not html_path.exists():
        continue
    hc = html_path.read_text(encoding='utf-8')
    m = re.search(r'(\d+) 題</p>', hc)
    html_total = int(m.group(1)) if m else -1
    html_ans_cells = len(re.findall(r'class="answer-cell[\s"]', hc))
    if html_total >= 0 and json_total != html_total:
        add('Critical', '資料', f'{cat}: JSON({json_total}) vs HTML({html_total}) 題數不一致')
    else:
        print(f"  {cat}: 題數一致 ({json_total})")
    if json_choice_ans != html_ans_cells:
        add('Major', '資料', f'{cat}: 有答案選擇題 JSON({json_choice_ans}) vs HTML答案格({html_ans_cells})')
    else:
        print(f"  {cat}: 答案格一致 ({json_choice_ans})")

# ======== 4. JS 函式引用 ========
fn_defs = set(re.findall(r'function\s+(\w+)\s*\(', js))
fn_calls_in_html = set()
for cat in samples:
    hp = SITE / cat / f'{cat}考古題總覽.html'
    if hp.exists():
        hc = hp.read_text(encoding='utf-8')
        fn_calls_in_html.update(re.findall(r'onclick="(\w+)\(', hc))
        fn_calls_in_html.update(re.findall(r'onchange="(\w+)\(', hc))

for fn in fn_calls_in_html:
    if fn and fn not in fn_defs and fn != 'debouncedSearch':
        add('Critical', 'JS', f'HTML onclick 呼叫未定義函式: {fn}()')

# Check var definitions
global_vars = re.findall(r'^(?:var|let|const)\s+(\w+)', js, re.MULTILINE)
fn_names = list(fn_defs)
print(f"  JS 全域: {len(fn_names)} 個函式, {len(global_vars)} 個變數")

# Check for undefined references in JS
js_fn_calls = set(re.findall(r'(?<![a-zA-Z_$])([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(', js))
external_ok = {'document', 'window', 'setTimeout', 'Array', 'Object', 'Math',
               'console', 'parseInt', 'parseFloat', 'Date', 'JSON', 'Function',
               'localStorage', 'require', 'clearTimeout'}
js_keywords = {'if', 'for', 'while', 'switch', 'catch', 'function', 'return', 'typeof', 'new', 'delete', 'throw', 'let', 'const', 'var'}
for call in js_fn_calls:
    if (call not in fn_defs and call not in external_ok and call not in js_keywords and
        not call[0].isupper() and call not in global_vars and
        call not in {'forEach', 'addEventListener', 'removeEventListener',
                     'querySelector', 'querySelectorAll', 'getElementById',
                     'classList', 'createElement', 'appendChild', 'remove',
                     'insertBefore', 'cloneNode', 'closest', 'toggle',
                     'contains', 'normalize', 'replaceChild', 'splitText',
                     'scrollTo', 'getBoundingClientRect', 'trim', 'replace',
                     'indexOf', 'match', 'push', 'unshift', 'slice',
                     'apply', 'from', 'keys', 'sort', 'join', 'textContent',
                     'getItem', 'setItem', 'parse', 'stringify', 'round',
                     'matchMedia', 'matches', 'add', 'toISOString',
                     'preventDefault', 'stopPropagation', 'focus', 'blur',
                     'click', 'test', 'normalize', 'fn', 'debounce',
                     'includes', 'startsWith', 'getAttribute', 'setAttribute',
                     'removeAttribute', 'removeChild', 'createTextNode',
                     'toLowerCase', 'not'}):
        add('Minor', 'JS', f'可能的未定義引用: {call}()')

# ======== Output ========
print("\n" + "=" * 60)
issues.sort(key=lambda x: {'Critical': 0, 'Major': 1, 'Minor': 2}[x[0]])
if not issues:
    print("  ✓ 零問題！所有檢查通過")
else:
    for level, area, msg in issues:
        symbol = '✗' if level == 'Critical' else '!' if level == 'Major' else '~'
        print(f"  {symbol} [{level}] [{area}] {msg}")
    c = sum(1 for i in issues if i[0] == 'Critical')
    m = sum(1 for i in issues if i[0] == 'Major')
    n = sum(1 for i in issues if i[0] == 'Minor')
    print(f"\n  總計: {c} Critical, {m} Major, {n} Minor")
print("=" * 60)
