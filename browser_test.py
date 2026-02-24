# -*- coding: utf-8 -*-
"""Playwright 瀏覽器自動化測試"""
import subprocess, time, sys, os

os.chdir(os.path.dirname(__file__))

from playwright.sync_api import sync_playwright

# 啟動 HTTP server
server = subprocess.Popen(
    [sys.executable, '-m', 'http.server', '8765', '--directory', '考古題網站'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(1)

results = []
def check(name, condition, detail=''):
    symbol = '✓' if condition else '✗'
    results.append((name, condition, detail))
    print(f'  {symbol} {name}' + (f' ({detail})' if detail else ''))

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        console_errors = []
        page.on('console', lambda msg: console_errors.append(msg.text) if msg.type == 'error' else None)

        # ===== 載入測試 =====
        print('\n=== 1. 頁面載入 ===')
        page.goto('http://localhost:8765/行政警察學系/行政警察學系考古題總覽.html', wait_until='networkidle')
        check('頁面載入', '行政警察學系' in page.title(), page.title())
        check('Sidebar 存在', page.is_visible('#sidebar'))
        check('搜尋框存在', page.is_visible('#searchInput'))
        check('Toolbar 存在', page.is_visible('#toolbar'))
        check('答案格存在', page.query_selector('.answer-section') is not None)

        # ===== 搜尋功能 =====
        print('\n=== 2. 搜尋功能 ===')
        page.fill('#searchInput', '憲法')
        page.wait_for_timeout(500)
        stats = page.text_content('#searchStats')
        check('搜尋統計顯示', '找到' in stats, stats.strip())
        highlights = page.query_selector_all('.highlight')
        check('高亮標記', len(highlights) > 0, f'{len(highlights)} 個')
        # 跳轉按鈕
        jump_btns = page.query_selector_all('.search-jump button')
        check('跳轉按鈕顯示', len(jump_btns) >= 2 if len(highlights) > 1 else True,
              f'{len(jump_btns)} 個按鈕, {len(highlights)} 個匹配')
        # 清空搜尋
        page.fill('#searchInput', '')
        page.wait_for_timeout(300)
        check('清空後高亮消失', len(page.query_selector_all('.highlight')) == 0)

        # ===== 練習模式 =====
        print('\n=== 3. 練習模式 ===')
        page.click('#practiceToggle')
        page.wait_for_timeout(300)
        check('練習模式啟用', page.evaluate('document.body.classList.contains("practice-mode")'))
        check('計分面板顯示', page.is_visible('#practiceScore'))
        check('答案格隱藏', not page.evaluate(
            'document.querySelector(".practice-mode .answer-section") ? '
            'getComputedStyle(document.querySelector(".practice-mode .answer-section")).display !== "none" : true'
        ))
        # 展開第一個有答案格的卡片
        page.evaluate('document.querySelector("#yearView .subject-card").classList.add("open")')
        page.wait_for_timeout(300)
        # 自我評分面板檢查
        score_panels = page.query_selector_all('.self-score-panel')
        check('自評面板存在', len(score_panels) > 0, f'{len(score_panels)} 個')
        # 點擊「顯示答案」
        reveal_btn = page.query_selector('.self-score-panel .reveal-btn')
        if reveal_btn:
            reveal_btn.scroll_into_view_if_needed()
            reveal_btn.click()
            page.wait_for_timeout(300)
            # 答案格應該有 revealed class
            answer_revealed = page.evaluate(
                'document.querySelector(".subject-card.open .answer-section.revealed") !== null'
            )
            check('顯示答案後答案格可見', answer_revealed)
            # 自評按鈕應該出現
            correct_btn = page.query_selector('.self-score-panel .score-btn.btn-correct.visible')
            check('答對按鈕出現', correct_btn is not None)
            # 點擊「答對」
            if correct_btn:
                correct_btn.click()
                page.wait_for_timeout(300)
                score_text = page.text_content('#scoreTotal')
                check('計分更新', score_text == '1', f'total={score_text}')
                correct_text = page.text_content('#scoreCorrect')
                check('答對計數', correct_text == '1', f'correct={correct_text}')
        # 結束練習
        page.click('#practiceToggle')
        page.wait_for_timeout(200)
        check('練習模式關閉', not page.evaluate('document.body.classList.contains("practice-mode")'))
        # 檢查 localStorage
        history = page.evaluate('localStorage.getItem("exam-practice-history")')
        check('練習歷史儲存', history is not None and 'scores' in str(history))

        # ===== 科目瀏覽 =====
        print('\n=== 4. 科目瀏覽 ===')
        page.click('#viewSubject')
        page.wait_for_timeout(800)
        check('subjectView 顯示', page.is_visible('#subjectView'))
        check('yearView 隱藏', not page.is_visible('#yearView'))
        sv_sections = page.query_selector_all('.subject-view-section')
        check('科目分組建立', len(sv_sections) > 0, f'{len(sv_sections)} 個科目')
        year_tags = page.query_selector_all('.sv-year-tag')
        check('年份標籤', len(year_tags) > 0, f'{len(year_tags)} 個')
        # 切回年份
        page.click('#viewYear')
        page.wait_for_timeout(200)
        check('切回年份瀏覽', page.is_visible('#yearView'))

        # ===== 書籤 =====
        print('\n=== 5. 書籤功能 ===')
        first_bm = page.query_selector('#yearView .bookmark-btn')
        if first_bm:
            first_bm.click()
            page.wait_for_timeout(100)
            check('書籤切換', first_bm.evaluate('el => el.classList.contains("active")'))
            bm_data = page.evaluate('localStorage.getItem("exam-bookmarks")')
            check('書籤存儲', bm_data is not None and bm_data != '{}')
            # 取消
            first_bm.click()
            page.wait_for_timeout(100)

        # ===== 深色模式 =====
        print('\n=== 6. 深色模式 ===')
        page.click('#darkToggle')
        page.wait_for_timeout(200)
        check('深色模式啟用', page.evaluate('document.documentElement.classList.contains("dark")'))
        page.click('#darkToggle')
        check('深色模式關閉', not page.evaluate('document.documentElement.classList.contains("dark")'))

        # ===== URL Hash =====
        print('\n=== 7. URL Hash 導航 ===')
        page.goto('http://localhost:8765/行政警察學系/行政警察學系考古題總覽.html#year-114', wait_until='networkidle')
        page.wait_for_timeout(500)
        year_el = page.query_selector('#year-114')
        check('Hash 年份定位', year_el is not None)

        # ===== Console 錯誤 =====
        print('\n=== 8. Console 錯誤 ===')
        check('零 Console 錯誤', len(console_errors) == 0,
              f'{len(console_errors)} 個: {console_errors[:3]}' if console_errors else '無')

        # ===== Index 頁面 =====
        print('\n=== 9. Index 首頁 ===')
        page.goto('http://localhost:8765/index.html', wait_until='networkidle')
        cards = page.query_selector_all('.category-card')
        check('類科卡片', len(cards) == 15, f'{len(cards)} 個')

        browser.close()

finally:
    server.terminate()

# Summary
print('\n' + '=' * 50)
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
failed = [(n, d) for n, ok, d in results if not ok]
if failed:
    print(f'  {passed}/{total} 通過')
    for name, detail in failed:
        print(f'  ✗ 失敗: {name} — {detail}')
else:
    print(f'  ✓ 全部 {total}/{total} 通過！零缺陷！')
print('=' * 50)
