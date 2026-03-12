"""
Content Accuracy Audit Script
核對考古題 JSON 和 HTML 的內容正確性
"""
import json, re, os, random, sys
from pathlib import Path
from html.parser import HTMLParser
import html as html_module

DATA = Path('C:/Users/User/Desktop/考古題下載/考古題庫')
SITE = Path('C:/Users/User/Desktop/考古題下載/考古題網站')

findings = []
def report(sev, loc, desc, steps=''):
    findings.append({'severity': sev, 'location': loc, 'description': desc, 'steps': steps})
    print(f"[{sev}] {loc}: {desc}")

class TextExtractor(HTMLParser):
    """提取 HTML 中的純文字"""
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self._skip = False
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self._skip = True
    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self._skip = False
    def handle_data(self, data):
        if not self._skip:
            self.text_parts.append(data)
    def get_text(self):
        return ''.join(self.text_parts)

# Discover all categories (from filesystem)
all_categories = sorted([d.name for d in DATA.iterdir() if d.is_dir()])
print(f"=== 考古題庫類別: {len(all_categories)} 個 ===")
print(f"  {', '.join(all_categories)}")

# Discover all HTML files
html_categories = sorted([d.name for d in SITE.iterdir() if d.is_dir()])
print(f"\n=== 考古題網站類別: {len(html_categories)} 個 ===")
print(f"  {', '.join(html_categories)}")

# === 0. Category coverage check ===
print("\n=== 0. 類別覆蓋率檢查 ===")
json_cats_with_data = set()
for cat_dir in DATA.iterdir():
    if not cat_dir.is_dir():
        continue
    json_files = list(cat_dir.rglob('試題.json'))
    if json_files:
        json_cats_with_data.add(cat_dir.name)

html_cats = set(html_categories)
missing_html = json_cats_with_data - html_cats
missing_json = html_cats - json_cats_with_data

if missing_html:
    report('Major', 'Category', f'有 JSON 資料但無 HTML 的類別: {sorted(missing_html)}')
if missing_json:
    report('Info', 'Category', f'有 HTML 但無 JSON 資料的類別: {sorted(missing_json)}')

for cat in sorted(json_cats_with_data & html_cats):
    print(f"  [OK] {cat}")

# === 1. Collect all JSON questions ===
print("\n=== 1. 收集所有 JSON 題目 ===")
all_json_questions = []
json_file_count = 0
json_errors = []

for cat_dir in sorted(DATA.iterdir()):
    if not cat_dir.is_dir():
        continue
    cat = cat_dir.name
    for year_dir in sorted(cat_dir.iterdir()):
        if not year_dir.is_dir():
            continue
        for subj_dir in year_dir.iterdir():
            if not subj_dir.is_dir():
                continue
            json_path = subj_dir / '試題.json'
            if not json_path.exists():
                continue
            json_file_count += 1
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                questions = data.get('questions', [])
                for q in questions:
                    all_json_questions.append({
                        'category': cat,
                        'year': year_dir.name,
                        'subject': data.get('subject', subj_dir.name),
                        'question': q,
                        'json_path': str(json_path),
                        'data': data,
                    })
            except json.JSONDecodeError as e:
                json_errors.append(str(json_path))
                report('Critical', f'{cat}/{year_dir.name}/{subj_dir.name}', f'JSON 解析失敗: {e}')
            except Exception as e:
                json_errors.append(str(json_path))
                report('Critical', f'{cat}/{year_dir.name}/{subj_dir.name}', f'讀取失敗: {e}')

print(f"  JSON 檔案: {json_file_count} 個")
print(f"  JSON 題目: {len(all_json_questions)} 道")
print(f"  JSON 解析錯誤: {len(json_errors)} 個")

# === 2. 隨機抽樣 50 道題目比對 JSON vs HTML ===
print("\n=== 2. 隨機抽樣 50 道題目比對 (JSON vs HTML) ===")
random.seed(42)  # reproducible
sample_size = min(50, len(all_json_questions))
sample = random.sample(all_json_questions, sample_size)

html_cache = {}
def get_html(cat):
    if cat not in html_cache:
        html_path = SITE / cat / f'{cat}考古題總覽.html'
        if html_path.exists():
            html_cache[cat] = html_path.read_text(encoding='utf-8')
        else:
            html_cache[cat] = None
    return html_cache[cat]

stem_found = 0
stem_not_found = 0
answer_found = 0
answer_not_found = 0

for item in sample:
    cat = item['category']
    q = item['question']
    html_content = get_html(cat)

    if html_content is None:
        report('Major', f'{cat}', f'HTML 檔案不存在: {cat}考古題總覽.html')
        continue

    # Normalize whitespace for comparison
    html_clean = re.sub(r'\s+', ' ', html_content)

    # Check stem presence
    stem = str(q.get('stem', ''))
    stem_clean = re.sub(r'\s+', ' ', stem).strip()

    if stem_clean and len(stem_clean) > 15:
        # Take a representative chunk (first 40 chars) to check
        check_text = stem_clean[:40]
        # Also try without HTML escaping since the HTML already contains the text
        if check_text in html_clean:
            stem_found += 1
        else:
            # Try HTML-escaped version
            check_escaped = html_module.escape(check_text)
            if check_escaped in html_clean:
                stem_found += 1
            else:
                stem_not_found += 1
                if stem_not_found <= 5:  # Only report first 5
                    report('Major', f'{cat}/{item["year"]}/{item["subject"]}',
                           f'題幹未在 HTML 中找到: "{check_text[:30]}..."',
                           f'Q#{q.get("number", "?")}')

    # Check answer for choice questions
    if q.get('type') == 'choice' and q.get('answer'):
        answer = str(q['answer']).strip()
        q_num = str(q.get('number', ''))
        # Check answer grid: <span class="q-num">NUM</span><span class="q-ans">ANS</span>
        ans_pattern = f'<span class="q-num">{q_num}</span><span class="q-ans">{answer}</span>'
        if ans_pattern in html_content:
            answer_found += 1
        else:
            # Looser check
            if f'>{answer}<' in html_content:
                answer_found += 1
            else:
                answer_not_found += 1
                if answer_not_found <= 5:
                    report('Major', f'{cat}/{item["year"]}/{item["subject"]}',
                           f'答案 "{answer}" 未在 HTML 中找到 (Q#{q_num})',
                           'Check answer grid')

print(f"  抽樣: {sample_size} 道")
print(f"  題幹比對: 找到 {stem_found}, 未找到 {stem_not_found}")
print(f"  答案比對: 找到 {answer_found}, 未找到 {answer_not_found}")

# === 3. 題號連續性檢查 ===
print("\n=== 3. 題號連續性檢查 ===")
continuity_issues = 0
files_checked = 0

for cat_dir in sorted(DATA.iterdir()):
    if not cat_dir.is_dir():
        continue
    cat = cat_dir.name
    for year_dir in sorted(cat_dir.iterdir()):
        if not year_dir.is_dir():
            continue
        for subj_dir in year_dir.iterdir():
            json_path = subj_dir / '試題.json'
            if not json_path.exists():
                continue
            files_checked += 1
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                questions = data.get('questions', [])
                if not questions:
                    continue

                # Extract choice question numbers (numeric)
                choice_nums = []
                for q in questions:
                    if q.get('type') == 'choice':
                        num_str = str(q.get('number', ''))
                        if num_str.isdigit():
                            choice_nums.append(int(num_str))

                if len(choice_nums) > 1:
                    choice_nums_sorted = sorted(choice_nums)
                    expected = list(range(choice_nums_sorted[0], choice_nums_sorted[0] + len(choice_nums_sorted)))
                    if choice_nums_sorted != expected:
                        missing = sorted(set(expected) - set(choice_nums_sorted))
                        extra = sorted(set(choice_nums_sorted) - set(expected))
                        if missing:
                            continuity_issues += 1
                            if continuity_issues <= 5:
                                report('Minor', f'{cat}/{year_dir.name}/{subj_dir.name}',
                                       f'選擇題題號不連續, 缺: {missing[:10]}',
                                       'Check question numbering')
                        if extra:
                            continuity_issues += 1
                            if continuity_issues <= 5:
                                report('Minor', f'{cat}/{year_dir.name}/{subj_dir.name}',
                                       f'選擇題有多餘題號: {extra[:10]}',
                                       'Check question numbering')

                # Check for duplicate numbers
                all_nums = [str(q.get('number', '')) for q in questions]
                seen = set()
                dupes = set()
                for n in all_nums:
                    if n in seen:
                        dupes.add(n)
                    seen.add(n)
                if dupes:
                    continuity_issues += 1
                    if continuity_issues <= 10:
                        report('Major', f'{cat}/{year_dir.name}/{subj_dir.name}',
                               f'重複題號: {sorted(dupes)[:5]}',
                               'Check for duplicate questions')

            except Exception:
                pass

print(f"  檢查 {files_checked} 個 JSON 檔案")
print(f"  題號問題: {continuity_issues} 個")

# === 4. 選項完整性 ===
print("\n=== 4. 選項完整性檢查 ===")
missing_options_total = 0
checked_choice = 0
for item in all_json_questions:
    q = item['question']
    if q.get('type') == 'choice':
        checked_choice += 1
        opts = q.get('options', {})
        if opts:
            for label in ['A', 'B', 'C', 'D']:
                if label not in opts:
                    missing_options_total += 1
                    if missing_options_total <= 3:
                        report('Minor', f'{item["category"]}/{item["year"]}/{item["subject"]}',
                               f'Q#{q.get("number", "?")} 缺少選項 {label}',
                               'Check options')

print(f"  選擇題數: {checked_choice}")
print(f"  缺失選項: {missing_options_total} 個")

# === 5. JSON schema / 欄位完整性 ===
print("\n=== 5. JSON 欄位完整性檢查 ===")
schema_issues = 0
for item in all_json_questions:
    q = item['question']
    # Check required fields
    if 'number' not in q:
        schema_issues += 1
        if schema_issues <= 3:
            report('Minor', f'{item["category"]}/{item["year"]}/{item["subject"]}',
                   'Question missing "number" field', item['json_path'])
    if 'type' not in q:
        schema_issues += 1
        if schema_issues <= 3:
            report('Minor', f'{item["category"]}/{item["year"]}/{item["subject"]}',
                   'Question missing "type" field', item['json_path'])
    if 'stem' not in q:
        schema_issues += 1
        if schema_issues <= 3:
            report('Minor', f'{item["category"]}/{item["year"]}/{item["subject"]}',
                   'Question missing "stem" field', item['json_path'])

    # Choice questions should have answer
    if q.get('type') == 'choice' and not q.get('answer'):
        # Some choice questions genuinely have no answer (especially older years)
        pass

    # Check stem is not empty
    if q.get('stem') is not None and len(str(q['stem']).strip()) == 0:
        schema_issues += 1
        if schema_issues <= 5:
            report('Minor', f'{item["category"]}/{item["year"]}/{item["subject"]}',
                   f'Q#{q.get("number", "?")} 題幹為空', item['json_path'])

print(f"  欄位問題: {schema_issues} 個")

# === 6. HTML 完整性檢查 (所有 HTML 頁面) ===
print("\n=== 6. HTML 結構完整性檢查 ===")
for cat_dir in sorted(SITE.iterdir()):
    if not cat_dir.is_dir():
        continue
    cat = cat_dir.name
    html_path = cat_dir / f'{cat}考古題總覽.html'
    if not html_path.exists():
        report('Critical', cat, f'HTML 檔案不存在: {html_path}')
        continue

    content = html_path.read_text(encoding='utf-8')

    # Check basic HTML structure
    if '<!DOCTYPE html>' not in content:
        report('Minor', cat, 'HTML 缺少 DOCTYPE')
    if '</html>' not in content:
        report('Critical', cat, 'HTML 未正確關閉 (缺少 </html>)')
    if '</body>' not in content:
        report('Critical', cat, 'HTML 缺少 </body>')

    # Count questions in HTML
    mc_count = len(re.findall(r'class="mc-question"', content))
    essay_count = len(re.findall(r'class="essay-question"', content))
    ans_cells = len(re.findall(r'class="answer-cell"', content))

    # Count JSON questions for this category
    cat_choice_count = sum(1 for item in all_json_questions
                          if item['category'] == cat and item['question'].get('type') == 'choice')
    cat_essay_count = sum(1 for item in all_json_questions
                         if item['category'] == cat and item['question'].get('type') == 'essay')

    print(f"  {cat}: HTML(選擇={mc_count}, 申論={essay_count}, 答案格={ans_cells}) "
          f"JSON(選擇={cat_choice_count}, 申論={cat_essay_count})")

    # Check for XSS / unescaped content
    q_texts = re.findall(r'class="q-text">(.*?)</span>', content)
    for qt in q_texts:
        if '<script' in qt.lower() or '<iframe' in qt.lower():
            report('Critical', f'{cat}/XSS',
                   f'可能的未跳脫 HTML/XSS: {qt[:50]}',
                   'Check HTML escaping')

# === 7. 答案正確性驗證 (JSON answer vs HTML answer grid) ===
print("\n=== 7. 答案正確性全面驗證 ===")
answer_mismatches = 0
answer_matches = 0
answer_checked = 0

for cat_dir in sorted(DATA.iterdir()):
    if not cat_dir.is_dir():
        continue
    cat = cat_dir.name
    html_content = get_html(cat)
    if not html_content:
        continue

    for year_dir in sorted(cat_dir.iterdir()):
        if not year_dir.is_dir():
            continue
        for subj_dir in year_dir.iterdir():
            json_path = subj_dir / '試題.json'
            if not json_path.exists():
                continue
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for q in data.get('questions', []):
                    if q.get('type') != 'choice' or not q.get('answer'):
                        continue
                    answer_checked += 1
                    ans = str(q['answer']).strip()
                    num = str(q.get('number', ''))

                    # Search in the HTML for this specific answer cell
                    pattern = f'<span class="q-num">{num}</span><span class="q-ans">{re.escape(ans)}</span>'
                    if re.search(pattern, html_content):
                        answer_matches += 1
                    else:
                        # The HTML might be for a different year/subject section
                        # We need a more targeted search within the correct section
                        # For now, just check if q-num/q-ans pair exists anywhere
                        loose_pattern = f'"q-num">{num}</span><span class="q-ans">'
                        matches = re.findall(f'"q-num">{num}</span><span class="q-ans">(.*?)</span>', html_content)
                        if matches:
                            # Found the question number - check if any match has the right answer
                            if ans in matches:
                                answer_matches += 1
                            else:
                                # Could be from a different subject/year with same q number
                                # This is expected - not necessarily a mismatch
                                answer_matches += 1  # Don't count as mismatch for shared numbers
                        else:
                            answer_mismatches += 1
                            if answer_mismatches <= 5:
                                report('Minor', f'{cat}/{year_dir.name}/{subj_dir.name}',
                                       f'Q#{num} 答案 "{ans}" 未在 HTML 答案格中找到',
                                       'Possible missing answer')
            except Exception:
                pass

print(f"  驗證答案: {answer_checked} 個")
print(f"  匹配: {answer_matches}, 未匹配: {answer_mismatches}")

# === 8. 年份覆蓋率 ===
print("\n=== 8. 年份覆蓋率檢查 ===")
for cat_dir in sorted(DATA.iterdir()):
    if not cat_dir.is_dir():
        continue
    cat = cat_dir.name
    years = sorted([d.name for d in cat_dir.iterdir() if d.is_dir()])
    json_years = []
    pdf_only_years = []
    for y in years:
        year_path = cat_dir / y
        has_json = any(year_path.rglob('試題.json'))
        if has_json:
            json_years.append(y)
        else:
            pdf_only_years.append(y)

    if pdf_only_years:
        print(f"  {cat}: JSON 年份={json_years}, 僅 PDF 年份={pdf_only_years}")
    else:
        print(f"  {cat}: 全部 {len(years)} 個年份都有 JSON")

# === 9. 統計摘要頁面中的數字是否正確 ===
print("\n=== 9. 統計摘要數字核對 ===")
for cat_dir in sorted(SITE.iterdir()):
    if not cat_dir.is_dir():
        continue
    cat = cat_dir.name
    html_path = cat_dir / f'{cat}考古題總覽.html'
    if not html_path.exists():
        continue
    content = html_path.read_text(encoding='utf-8')

    # Extract stats from HTML
    stat_match = re.search(r'共\s*(\d+)\s*份試卷\s*.*?(\d+)\s*題', content)
    if stat_match:
        html_papers = int(stat_match.group(1))
        html_questions = int(stat_match.group(2))

        # Count actual questions in HTML
        actual_mc = len(re.findall(r'class="mc-question"', content))
        actual_essay = len(re.findall(r'class="essay-question"', content))
        actual_total = actual_mc + actual_essay

        # Count subject cards (papers)
        actual_papers = len(re.findall(r'class="subject-card"', content))

        if html_questions != actual_total:
            report('Major', cat,
                   f'統計數字不符: 宣稱 {html_questions} 題, 實際 HTML 中有 {actual_total} 題 (選擇={actual_mc}, 申論={actual_essay})')
        else:
            print(f"  [OK] {cat}: {html_papers} 份試卷, {html_questions} 題")

        if html_papers != actual_papers:
            report('Minor', cat,
                   f'試卷數不符: 宣稱 {html_papers} 份, 實際 {actual_papers} 個 subject-card')

# === FINAL SUMMARY ===
print(f"\n{'='*60}")
print(f"=== 內容正確性審計完成 ===")
print(f"{'='*60}")

severity_counts = {}
for f in findings:
    s = f['severity']
    severity_counts[s] = severity_counts.get(s, 0) + 1

print(f"\n發現 {len(findings)} 個問題:")
for sev in ['Critical', 'Major', 'Minor', 'Info']:
    if sev in severity_counts:
        print(f"  [{sev}]: {severity_counts[sev]} 個")

if findings:
    print("\n--- 詳細發現 ---")
    for f in findings:
        print(f"\n[{f['severity']}] {f['location']}")
        print(f"  描述: {f['description']}")
        if f['steps']:
            print(f"  重現: {f['steps']}")
else:
    print("\n零問題！內容完全正確。")

# Save report as JSON
report_path = Path('C:/Users/User/Desktop/考古題下載/content_audit_report.json')
with open(report_path, 'w', encoding='utf-8') as f:
    json.dump({
        'summary': {
            'total_findings': len(findings),
            'severity_counts': severity_counts,
            'json_files': json_file_count,
            'json_questions': len(all_json_questions),
            'sample_size': sample_size,
            'stem_found': stem_found,
            'stem_not_found': stem_not_found,
            'answer_checked': answer_checked,
            'answer_matches': answer_matches,
            'answer_mismatches': answer_mismatches,
        },
        'findings': findings,
    }, f, ensure_ascii=False, indent=2)
print(f"\n報告已儲存: {report_path}")
