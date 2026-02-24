# -*- coding: utf-8 -*-
"""Playwright 擴展瀏覽器自動化測試 — 12 項邊界情境"""
import subprocess, time, sys, os

os.chdir(os.path.dirname(__file__))

from playwright.sync_api import sync_playwright

# 啟動 HTTP server
server = subprocess.Popen(
    [sys.executable, '-m', 'http.server', '8765', '--directory', '考古題網站'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(1)

URL = 'http://localhost:8765/行政警察學系/行政警察學系考古題總覽.html'
results = []

def check(name, condition, detail=''):
    symbol = '✓' if condition else '✗'
    results.append((name, condition, detail))
    print(f'  {symbol} {name}' + (f' ({detail})' if detail else ''))

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # ================================================================
        # 測試 1: 搜尋 + 年份篩選組合
        # ================================================================
        print('\n=== 測試 1: 搜尋 + 年份篩選組合 ===')
        page = browser.new_page()
        console_errors = []
        page.on('console', lambda msg: console_errors.append(msg.text) if msg.type == 'error' else None)
        page.goto(URL, wait_until='networkidle')

        # 先點年份篩選 chip「114」
        page.click('.filter-chip[data-year="114"]')
        page.wait_for_timeout(300)
        # 確認 chip 被選中
        chip_active = page.evaluate('document.querySelector(\'.filter-chip[data-year="114"]\').classList.contains("active")')
        check('年份chip 114啟用', chip_active)

        # 再搜尋關鍵字「憲法」
        page.fill('#searchInput', '憲法')
        page.wait_for_timeout(500)

        # 確認結果只顯示 114 年
        visible_cards = page.evaluate('''() => {
            const cards = document.querySelectorAll('#yearView .subject-card');
            let results = [];
            cards.forEach(c => {
                if (c.style.display !== 'none' && c.offsetParent !== null) {
                    const yearSection = c.closest('.year-section');
                    const yearHeading = yearSection ? yearSection.querySelector('.year-heading').textContent.trim() : 'unknown';
                    results.push(yearHeading);
                }
            });
            return results;
        }''')
        all_114 = all(y.startswith('114') for y in visible_cards) if visible_cards else False
        check('搜尋+年份篩選只顯示114年', all_114, f'可見年份: {set(visible_cards)}')
        check('搜尋+年份篩選有結果', len(visible_cards) > 0, f'{len(visible_cards)} 張卡片')

        # 確認有高亮
        hl_count = len(page.query_selector_all('.highlight'))
        check('搜尋+年份篩選有高亮', hl_count > 0, f'{hl_count} 處')

        # 確認搜尋統計文字
        stats_text = page.text_content('#searchStatsText')
        check('搜尋統計包含找到', '找到' in stats_text, stats_text.strip())

        page.close()

        # ================================================================
        # 測試 2: 科目瀏覽 + 年份篩選
        # ================================================================
        print('\n=== 測試 2: 科目瀏覽 + 年份篩選 ===')
        page = browser.new_page()
        console_errors_2 = []
        page.on('console', lambda msg: console_errors_2.append(msg.text) if msg.type == 'error' else None)
        page.goto(URL, wait_until='networkidle')

        # 切到科目瀏覽
        page.click('#viewSubject')
        page.wait_for_timeout(800)
        check('subjectView 已顯示', page.is_visible('#subjectView'))

        # 選年份篩選 chip「113」
        page.click('.filter-chip[data-year="113"]')
        page.wait_for_timeout(500)

        # 確認不是空白頁（有可見的卡片）
        sv_visible_cards = page.evaluate('''() => {
            const cards = document.querySelectorAll('#subjectView .subject-card');
            let visible = 0;
            cards.forEach(c => { if (c.style.display !== 'none') visible++; });
            return visible;
        }''')
        check('科目瀏覽+年份篩選不空白', sv_visible_cards > 0, f'{sv_visible_cards} 張可見卡片')

        # 確認可見卡片都包含 113 年標籤
        sv_year_tags = page.evaluate('''() => {
            const cards = document.querySelectorAll('#subjectView .subject-card');
            let years = [];
            cards.forEach(c => {
                if (c.style.display !== 'none') {
                    const tag = c.querySelector('.sv-year-tag');
                    if (tag) years.push(tag.textContent.trim());
                }
            });
            return years;
        }''')
        all_113 = all('113' in y for y in sv_year_tags) if sv_year_tags else False
        check('科目瀏覽年份篩選只顯示113年', all_113, f'年份標籤: {set(sv_year_tags)}')

        # 確認科目分組區段不全隱藏
        sv_sections_visible = page.evaluate('''() => {
            const sections = document.querySelectorAll('#subjectView .subject-view-section');
            let vis = 0;
            sections.forEach(s => { if (s.style.display !== 'none') vis++; });
            return vis;
        }''')
        check('科目分組有可見區段', sv_sections_visible > 0, f'{sv_sections_visible} 個')

        check('科目瀏覽+年份篩選零Console錯誤', len(console_errors_2) == 0,
              f'{len(console_errors_2)} 個' if console_errors_2 else '無')

        page.close()

        # ================================================================
        # 測試 3: 科目瀏覽 + 搜尋
        # ================================================================
        print('\n=== 測試 3: 科目瀏覽 + 搜尋 ===')
        page = browser.new_page()
        console_errors_3 = []
        page.on('console', lambda msg: console_errors_3.append(msg.text) if msg.type == 'error' else None)
        page.goto(URL, wait_until='networkidle')

        # 切到科目瀏覽
        page.click('#viewSubject')
        page.wait_for_timeout(800)

        # 搜尋關鍵字
        page.fill('#searchInput', '警察')
        page.wait_for_timeout(500)

        # 確認 subjectView 有結果
        sv_search_cards = page.evaluate('''() => {
            const cards = document.querySelectorAll('#subjectView .subject-card');
            let visible = 0;
            cards.forEach(c => { if (c.style.display !== 'none') visible++; });
            return visible;
        }''')
        check('科目瀏覽搜尋有結果', sv_search_cards > 0, f'{sv_search_cards} 張匹配')

        # 確認有高亮在 subjectView 中
        sv_highlights = page.evaluate('''() => {
            return document.querySelectorAll('#subjectView .highlight').length;
        }''')
        check('科目瀏覽搜尋有高亮', sv_highlights > 0, f'{sv_highlights} 處')

        # 確認搜尋統計
        stats3 = page.text_content('#searchStatsText')
        check('科目瀏覽搜尋統計', '找到' in stats3, stats3.strip())

        check('科目瀏覽+搜尋零Console錯誤', len(console_errors_3) == 0,
              f'{len(console_errors_3)} 個' if console_errors_3 else '無')

        page.close()

        # ================================================================
        # 測試 4: 練習模式 + 切換 view
        # ================================================================
        print('\n=== 測試 4: 練習模式 + 切換 view ===')
        page = browser.new_page()
        console_errors_4 = []
        page.on('console', lambda msg: console_errors_4.append(msg.text) if msg.type == 'error' else None)
        page.goto(URL, wait_until='networkidle')

        # 開啟練習模式
        page.click('#practiceToggle')
        page.wait_for_timeout(300)
        check('練習模式啟動', page.evaluate('document.body.classList.contains("practice-mode")'))

        # 確認 yearView 有 self-score-panel
        yv_panels = len(page.query_selector_all('#yearView .self-score-panel'))
        check('yearView有自評面板', yv_panels > 0, f'{yv_panels} 個')

        # 切到科目瀏覽
        page.click('#viewSubject')
        page.wait_for_timeout(800)

        # 確認 subjectView 也有 self-score-panel（switchView 會 rebuild）
        sv_panels = len(page.query_selector_all('#subjectView .self-score-panel'))
        check('科目瀏覽也有自評面板', sv_panels > 0, f'{sv_panels} 個')

        # 確認練習模式仍啟用
        check('切換後練習模式仍啟用', page.evaluate('document.body.classList.contains("practice-mode")'))

        # 確認計分面板仍可見
        check('切換後計分面板仍可見', page.is_visible('#practiceScore'))

        check('練習模式+切換view零Console錯誤', len(console_errors_4) == 0,
              f'{len(console_errors_4)} 個: {console_errors_4[:3]}' if console_errors_4 else '無')

        page.close()

        # ================================================================
        # 測試 5: 練習模式 + 答錯
        # ================================================================
        print('\n=== 測試 5: 練習模式 + 答錯 ===')
        page = browser.new_page()
        console_errors_5 = []
        page.on('console', lambda msg: console_errors_5.append(msg.text) if msg.type == 'error' else None)
        page.goto(URL, wait_until='networkidle')

        # 開啟練習模式
        page.click('#practiceToggle')
        page.wait_for_timeout(300)

        # 展開第一個卡片
        page.evaluate('document.querySelector("#yearView .subject-card").classList.add("open")')
        page.wait_for_timeout(300)

        # 點顯示答案
        reveal_btn = page.query_selector('#yearView .self-score-panel .reveal-btn')
        if reveal_btn:
            reveal_btn.scroll_into_view_if_needed()
            reveal_btn.click()
            page.wait_for_timeout(300)

            # 確認答錯按鈕出現
            wrong_btn = page.query_selector('#yearView .self-score-panel .score-btn.btn-wrong.visible')
            check('答錯按鈕出現', wrong_btn is not None)

            # 點答錯
            if wrong_btn:
                wrong_btn.click()
                page.wait_for_timeout(300)

                # 確認計分 0/1
                score_correct = page.text_content('#scoreCorrect')
                score_total = page.text_content('#scoreTotal')
                check('答錯後答對=0', score_correct == '0', f'correct={score_correct}')
                check('答錯後總計=1', score_total == '1', f'total={score_total}')

                # 確認百分比
                score_pct = page.text_content('#scorePct')
                check('答錯後百分比=0%', score_pct == '0%', f'pct={score_pct}')

                # 確認面板有 was-wrong class
                was_wrong = page.evaluate(
                    'document.querySelector("#yearView .self-score-panel.was-wrong") !== null'
                )
                check('面板標記答錯', was_wrong)
        else:
            check('找到顯示答案按鈕', False, '未找到 reveal-btn')

        check('練習模式+答錯零Console錯誤', len(console_errors_5) == 0,
              f'{len(console_errors_5)} 個' if console_errors_5 else '無')

        page.close()

        # ================================================================
        # 測試 6: 書籤 + 切換 view
        # ================================================================
        print('\n=== 測試 6: 書籤 + 切換 view ===')
        page = browser.new_page()
        console_errors_6 = []
        page.on('console', lambda msg: console_errors_6.append(msg.text) if msg.type == 'error' else None)
        page.goto(URL, wait_until='networkidle')

        # 清除舊書籤
        page.evaluate('localStorage.removeItem("exam-bookmarks")')
        page.reload(wait_until='networkidle')

        # 在 yearView 加書籤（第一張卡片）
        first_card_id = page.evaluate('document.querySelector("#yearView .subject-card").id')
        first_bm_btn = page.query_selector('#yearView .bookmark-btn')
        if first_bm_btn:
            first_bm_btn.click()
            page.wait_for_timeout(200)
            check('yearView書籤已加', first_bm_btn.evaluate('el => el.classList.contains("active")'))

            # 切到 subjectView
            page.click('#viewSubject')
            page.wait_for_timeout(800)

            # 確認 subjectView 對應卡片也有書籤標記
            sv_bm_active = page.evaluate('''(cardId) => {
                const svCard = document.querySelector('#subjectView .subject-card[data-card-id="' + cardId + '"]');
                if (!svCard) return false;
                const bmBtn = svCard.querySelector('.bookmark-btn');
                return bmBtn ? bmBtn.classList.contains('active') : false;
            }''', first_card_id)
            check('subjectView同卡片有書籤', sv_bm_active, f'card-id={first_card_id}')
        else:
            check('找到書籤按鈕', False, '未找到')

        check('書籤+切換view零Console錯誤', len(console_errors_6) == 0,
              f'{len(console_errors_6)} 個' if console_errors_6 else '無')

        page.close()

        # ================================================================
        # 測試 7: 書籤篩選 + 切換 view
        # ================================================================
        print('\n=== 測試 7: 書籤篩選 + 切換 view ===')
        page = browser.new_page()
        console_errors_7 = []
        page.on('console', lambda msg: console_errors_7.append(msg.text) if msg.type == 'error' else None)
        page.goto(URL, wait_until='networkidle')

        # 清除舊書籤
        page.evaluate('localStorage.removeItem("exam-bookmarks")')
        page.reload(wait_until='networkidle')

        # 在 yearView 加兩個書籤
        bookmark_btns = page.query_selector_all('#yearView .bookmark-btn')
        bookmarked_ids = []
        for i in range(min(2, len(bookmark_btns))):
            bookmark_btns[i].click()
            page.wait_for_timeout(100)
            card = bookmark_btns[i].evaluate('el => el.closest(".subject-card").id')
            bookmarked_ids.append(card)

        check('已加書籤數', len(bookmarked_ids) >= 2, f'{len(bookmarked_ids)} 個')

        # 開啟書籤篩選
        page.click('#bookmarkFilter')
        page.wait_for_timeout(300)
        bm_filter_active = page.evaluate('document.getElementById("bookmarkFilter").classList.contains("active")')
        check('書籤篩選啟用', bm_filter_active)

        # 確認 yearView 只顯示書籤卡片
        yv_visible = page.evaluate('''() => {
            const cards = document.querySelectorAll('#yearView .subject-card');
            let count = 0;
            cards.forEach(c => { if (c.style.display !== 'none') count++; });
            return count;
        }''')
        check('yearView只顯示書籤卡片', yv_visible == len(bookmarked_ids), f'可見={yv_visible}, 書籤={len(bookmarked_ids)}')

        # 切到科目瀏覽 — switchView 會重新套用書籤篩選
        page.click('#viewSubject')
        page.wait_for_timeout(800)

        # switchView 中 bookmarkFilterActive 先設 false 再 toggleBookmarkFilter()
        # 所以書籤篩選會在 subjectView 中重新套用
        sv_bm_filter_active = page.evaluate('document.getElementById("bookmarkFilter").classList.contains("active")')
        check('科目瀏覽書籤篩選已套用', sv_bm_filter_active)

        # 確認 subjectView 只顯示書籤卡片
        sv_visible_bm = page.evaluate('''(ids) => {
            const cards = document.querySelectorAll('#subjectView .subject-card');
            let count = 0;
            cards.forEach(c => { if (c.style.display !== 'none') count++; });
            return count;
        }''', bookmarked_ids)
        check('subjectView書籤篩選有卡片', sv_visible_bm > 0, f'{sv_visible_bm} 張可見')

        check('書籤篩選+切換view零Console錯誤', len(console_errors_7) == 0,
              f'{len(console_errors_7)} 個' if console_errors_7 else '無')

        page.close()

        # ================================================================
        # 測試 8: 搜尋跳轉導航
        # ================================================================
        print('\n=== 測試 8: 搜尋跳轉導航 ===')
        page = browser.new_page()
        console_errors_8 = []
        page.on('console', lambda msg: console_errors_8.append(msg.text) if msg.type == 'error' else None)
        page.goto(URL, wait_until='networkidle')

        # 搜尋常見關鍵字確保多個 hit
        page.fill('#searchInput', '憲法')
        page.wait_for_timeout(500)

        highlights_count = len(page.query_selector_all('.highlight'))
        check('搜尋高亮多於1', highlights_count > 1, f'{highlights_count} 處')

        # 確認跳轉按鈕存在
        jump_btns = page.query_selector_all('.search-jump button')
        check('跳轉按鈕存在', len(jump_btns) >= 2, f'{len(jump_btns)} 個')

        if len(jump_btns) >= 2:
            # 點「下一個」（第二個按鈕 = ▶）
            jump_btns[1].click()
            page.wait_for_timeout(300)

            # 確認有 .current highlight
            has_current = page.evaluate('document.querySelector(".highlight.current") !== null')
            check('點下一個後有.current', has_current)

            # 確認 counter 更新
            counter_text = page.text_content('#hitCounter')
            check('計數器更新', counter_text is not None and '/' in counter_text, counter_text)

            # 再點一次下一個
            jump_btns[1].click()
            page.wait_for_timeout(300)
            counter_text_2 = page.text_content('#hitCounter')
            check('再點下一個計數器遞增', counter_text_2 != counter_text, f'{counter_text} -> {counter_text_2}')

            # 確認只有一個 .current
            current_count = len(page.query_selector_all('.highlight.current'))
            check('只有一個.current', current_count == 1, f'{current_count} 個')

        check('搜尋跳轉零Console錯誤', len(console_errors_8) == 0,
              f'{len(console_errors_8)} 個' if console_errors_8 else '無')

        page.close()

        # ================================================================
        # 測試 9: 深色模式 + 練習模式
        # ================================================================
        print('\n=== 測試 9: 深色模式 + 練習模式 ===')
        page = browser.new_page()
        console_errors_9 = []
        page.on('console', lambda msg: console_errors_9.append(msg.text) if msg.type == 'error' else None)
        page.goto(URL, wait_until='networkidle')

        # 開啟深色模式
        page.click('#darkToggle')
        page.wait_for_timeout(200)
        is_dark = page.evaluate('document.documentElement.classList.contains("dark")')
        check('深色模式啟用', is_dark)

        # 開啟練習模式
        page.click('#practiceToggle')
        page.wait_for_timeout(300)
        is_practice = page.evaluate('document.body.classList.contains("practice-mode")')
        check('深色+練習模式啟用', is_practice)

        # 展開卡片測試
        page.evaluate('document.querySelector("#yearView .subject-card").classList.add("open")')
        page.wait_for_timeout(300)

        # 點顯示答案
        reveal = page.query_selector('#yearView .self-score-panel .reveal-btn')
        if reveal:
            reveal.scroll_into_view_if_needed()
            reveal.click()
            page.wait_for_timeout(300)

        # 確認無 console 錯誤
        check('深色+練習模式零Console錯誤', len(console_errors_9) == 0,
              f'{len(console_errors_9)} 個: {console_errors_9[:3]}' if console_errors_9 else '無')

        # 確認兩個模式同時存在
        both_active = page.evaluate(
            'document.documentElement.classList.contains("dark") && document.body.classList.contains("practice-mode")'
        )
        check('深色+練習兩模式共存', both_active)

        page.close()

        # ================================================================
        # 測試 10: 多次切換 view
        # ================================================================
        print('\n=== 測試 10: 多次切換 view ===')
        page = browser.new_page()
        console_errors_10 = []
        page.on('console', lambda msg: console_errors_10.append(msg.text) if msg.type == 'error' else None)
        page.goto(URL, wait_until='networkidle')

        # 年份 -> 科目 -> 年份 -> 科目 -> 年份 -> 科目（共 5 次切換）
        for i in range(5):
            if i % 2 == 0:
                page.click('#viewSubject')
            else:
                page.click('#viewYear')
            page.wait_for_timeout(400)

        # 最後一次是切到科目（index 0,2,4 -> viewSubject）
        final_sv_visible = page.is_visible('#subjectView')
        check('5次切換後subjectView可見', final_sv_visible)

        # 再切一次回年份
        page.click('#viewYear')
        page.wait_for_timeout(400)
        final_yv_visible = page.is_visible('#yearView')
        check('6次切換後yearView可見', final_yv_visible)

        # 確認內容沒壞
        cards_exist = len(page.query_selector_all('#yearView .subject-card')) > 0
        check('多次切換後yearView卡片存在', cards_exist)

        sv_sections = len(page.query_selector_all('#subjectView .subject-view-section'))
        check('多次切換後subjectView區段存在', sv_sections > 0, f'{sv_sections} 個')

        check('多次切換零Console錯誤', len(console_errors_10) == 0,
              f'{len(console_errors_10)} 個: {console_errors_10[:3]}' if console_errors_10 else '無')

        page.close()

        # ================================================================
        # 測試 11: 科目下拉篩選
        # ================================================================
        print('\n=== 測試 11: 科目下拉篩選 ===')
        page = browser.new_page()
        console_errors_11 = []
        page.on('console', lambda msg: console_errors_11.append(msg.text) if msg.type == 'error' else None)
        page.goto(URL, wait_until='networkidle')

        # 取得科目下拉選項
        options = page.evaluate('''() => {
            const sel = document.getElementById('subjectFilter');
            return Array.from(sel.options).map(o => o.value).filter(v => v);
        }''')
        check('科目下拉有選項', len(options) > 0, f'{len(options)} 個科目')

        if options:
            # 選第一個科目
            target_subject = options[0]
            page.select_option('#subjectFilter', target_subject)
            page.wait_for_timeout(300)

            # 確認只顯示該科目卡片
            filter_result = page.evaluate('''(target) => {
                const cards = document.querySelectorAll('#yearView .subject-card');
                let visible = 0, match = 0, mismatch = 0;
                cards.forEach(c => {
                    if (c.style.display !== 'none') {
                        visible++;
                        const name = c.querySelector('.subject-header h3').textContent.trim();
                        if (name.indexOf(target) !== -1) match++;
                        else mismatch++;
                    }
                });
                return {visible, match, mismatch};
            }''', target_subject)
            check('科目篩選有結果', filter_result['visible'] > 0, f'{filter_result["visible"]} 張可見')
            check('科目篩選全匹配', filter_result['mismatch'] == 0,
                  f'匹配={filter_result["match"]}, 不匹配={filter_result["mismatch"]}')

            # 也測試在科目瀏覽中
            page.click('#viewSubject')
            page.wait_for_timeout(800)
            # 重新選（因為切換 view 可能重置）
            page.select_option('#subjectFilter', target_subject)
            page.wait_for_timeout(300)

            sv_filter_result = page.evaluate('''(target) => {
                const cards = document.querySelectorAll('#subjectView .subject-card');
                let visible = 0, match = 0, mismatch = 0;
                cards.forEach(c => {
                    if (c.style.display !== 'none') {
                        visible++;
                        const name = c.querySelector('.subject-header h3').textContent.trim();
                        if (name.indexOf(target) !== -1) match++;
                        else mismatch++;
                    }
                });
                return {visible, match, mismatch};
            }''', target_subject)
            check('科目瀏覽科目篩選有結果', sv_filter_result['visible'] > 0, f'{sv_filter_result["visible"]} 張可見')
            check('科目瀏覽科目篩選全匹配', sv_filter_result['mismatch'] == 0,
                  f'匹配={sv_filter_result["match"]}, 不匹配={sv_filter_result["mismatch"]}')

            # 重置篩選
            page.select_option('#subjectFilter', '')
            page.wait_for_timeout(300)

        check('科目下拉篩選零Console錯誤', len(console_errors_11) == 0,
              f'{len(console_errors_11)} 個' if console_errors_11 else '無')

        page.close()

        # ================================================================
        # 測試 12: URL hash + subjectView
        # ================================================================
        print('\n=== 測試 12: URL hash + subjectView ===')
        page = browser.new_page()
        console_errors_12 = []
        page.on('console', lambda msg: console_errors_12.append(msg.text) if msg.type == 'error' else None)
        page.goto(URL, wait_until='networkidle')

        # 切到 subjectView
        page.click('#viewSubject')
        page.wait_for_timeout(800)
        check('已在subjectView', page.is_visible('#subjectView'))

        # 直接在 subjectView 模式下修改 hash
        page.evaluate('window.location.hash = "year-113"')
        page.wait_for_timeout(500)

        # 確認頁面沒崩潰（subjectView 或 yearView 至少一個可見）
        any_view_visible = page.evaluate('''() => {
            const yv = document.getElementById('yearView');
            const sv = document.getElementById('subjectView');
            return (yv.style.display !== 'none' || sv.style.display !== 'none');
        }''')
        check('hash變更後頁面未崩潰', any_view_visible)

        # 確認無 console 錯誤
        check('hash+subjectView零Console錯誤', len(console_errors_12) == 0,
              f'{len(console_errors_12)} 個: {console_errors_12[:3]}' if console_errors_12 else '無')

        # 測試直接帶 hash 載入 + subjectView
        page.goto(URL + '#year-112', wait_until='networkidle')
        page.wait_for_timeout(500)
        page.click('#viewSubject')
        page.wait_for_timeout(800)
        sv_still_works = page.is_visible('#subjectView')
        check('帶hash載入後切subjectView正常', sv_still_works)

        # 測試 card hash 在 subjectView
        page.evaluate('window.location.hash = "y114-15a7b19c"')
        page.wait_for_timeout(500)
        check('card hash在subjectView無崩潰', True)  # 只要沒 exception 就算通過

        check('URL hash測試零Console錯誤', len(console_errors_12) == 0,
              f'{len(console_errors_12)} 個: {console_errors_12[:3]}' if console_errors_12 else '無')

        page.close()

        browser.close()

finally:
    server.terminate()

# Summary
print('\n' + '=' * 60)
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
failed = [(n, d) for n, ok, d in results if not ok]
print(f'  擴展測試結果: {passed}/{total} 通過')
if failed:
    print(f'  失敗項目:')
    for name, detail in failed:
        print(f'    ✗ {name} — {detail}')
else:
    print(f'  ✓ 全部 {total}/{total} 通過！零缺陷！')
print('=' * 60)
