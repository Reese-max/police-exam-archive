# -*- coding: utf-8 -*-
"""
Playwright 瀏覽器模擬測試：考生備考使用者流程
模擬一位考生從首頁進入、搜尋、練習、書籤等完整流程。
"""
import subprocess, time, sys, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright

PORT = 8766
BASE = f'http://localhost:{PORT}'

# ─── 啟動 HTTP server ───
server = subprocess.Popen(
    [sys.executable, '-m', 'http.server', str(PORT), '--directory', '考古題網站'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(1.5)

results = []
def check(step, name, condition, detail=''):
    symbol = '\u2713' if condition else '\u2717'
    results.append((step, name, condition, detail))
    line = f'  {symbol} [{step}] {name}'
    if detail:
        line += f'  ({detail})'
    print(line)

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 900})
        page = context.new_page()

        # 全程記錄 console errors
        console_errors = []
        page.on('console', lambda msg: console_errors.append(msg.text) if msg.type == 'error' else None)

        # ============================================================
        # 步驟 1：首頁瀏覽
        # ============================================================
        print('\n' + '=' * 60)
        print('步驟 1：首頁瀏覽')
        print('=' * 60)
        page.goto(f'{BASE}/index.html', wait_until='networkidle')
        check('1', '首頁載入成功', '考古題' in page.title(), page.title())

        # 確認 15 個類科連結都存在
        category_cards = page.query_selector_all('.category-card')
        check('1', '15 個類科連結存在', len(category_cards) == 15, f'找到 {len(category_cards)} 個')

        # 確認所有類科名稱
        expected_categories = [
            '行政警察學系', '外事警察學系', '刑事警察學系', '公共安全學系社安組',
            '犯罪防治學系預防組', '犯罪防治學系矯治組', '消防學系',
            '交通學系交通組', '交通學系電訊組', '資訊管理學系',
            '鑑識科學學系', '國境警察學系境管組', '水上警察學系', '法律學系', '行政管理學系'
        ]
        card_titles = [c.query_selector('.card-title').text_content().strip() for c in category_cards]
        all_found = all(cat in card_titles for cat in expected_categories)
        check('1', '所有 15 個類科名稱正確', all_found,
              f'缺少: {[c for c in expected_categories if c not in card_titles]}' if not all_found else '全部正確')

        # ============================================================
        # 步驟 2：進入「行政警察學系」類科
        # ============================================================
        print('\n' + '=' * 60)
        print('步驟 2：進入「行政警察學系」類科')
        print('=' * 60)

        # 點擊行政警察學系卡片
        admin_police_card = page.query_selector('.category-card:has(.card-title:text("行政警察學系"))')
        if admin_police_card is None:
            # fallback: 第一個卡片
            admin_police_card = category_cards[0]
        admin_police_card.click()
        page.wait_for_load_state('networkidle')

        check('2', '進入行政警察學系頁面', '行政警察學系' in page.title(), page.title())
        check('2', 'Sidebar 存在', page.is_visible('#sidebar'))
        check('2', '搜尋框存在', page.is_visible('#searchInput'))
        check('2', 'Toolbar 存在', page.is_visible('#toolbar'))

        # ============================================================
        # 步驟 3：Sidebar 年份導航
        # ============================================================
        print('\n' + '=' * 60)
        print('步驟 3：Sidebar 年份導航')
        print('=' * 60)

        # 找 sidebar 中 114年 的按鈕
        sidebar_years = page.query_selector_all('.sidebar-year')
        year114_btn = None
        for sy in sidebar_years:
            if '114' in sy.text_content():
                year114_btn = sy
                break

        check('3', 'Sidebar 有 114年 按鈕', year114_btn is not None)

        if year114_btn:
            year114_btn.click()
            page.wait_for_timeout(300)
            is_active = year114_btn.evaluate('el => el.classList.contains("active")')
            check('3', '點擊後 114年 展開 (active)', is_active)

            # 確認子連結出現
            subjects_div = year114_btn.evaluate_handle('el => el.nextElementSibling')
            subjects_visible = subjects_div.evaluate('el => el && getComputedStyle(el).display !== "none"')
            check('3', '114年 科目連結顯示', subjects_visible)

        # ============================================================
        # 步驟 4：搜尋功能 — 輸入「憲法」
        # ============================================================
        print('\n' + '=' * 60)
        print('步驟 4：搜尋功能')
        print('=' * 60)

        page.fill('#searchInput', '憲法')
        page.wait_for_timeout(500)

        stats_text = page.text_content('#searchStatsText')
        check('4', '搜尋結果統計顯示', '找到' in stats_text, stats_text.strip())

        highlights = page.query_selector_all('.highlight')
        check('4', '有高亮結果', len(highlights) > 0, f'{len(highlights)} 處高亮')

        # ============================================================
        # 步驟 5：搜尋跳轉
        # ============================================================
        print('\n' + '=' * 60)
        print('步驟 5：搜尋跳轉')
        print('=' * 60)

        jump_btns = page.query_selector_all('.search-jump button')
        has_jump = len(jump_btns) >= 2
        check('5', '跳轉按鈕出現', has_jump, f'{len(jump_btns)} 個按鈕')

        if has_jump:
            # 點「下一個」(▶) 按鈕
            next_btn = jump_btns[1]  # 第二個按鈕是 ▶
            next_btn.click()
            page.wait_for_timeout(200)
            counter_text = page.text_content('#hitCounter')
            check('5', '第一次跳轉', counter_text is not None and '1/' in counter_text, counter_text)

            next_btn.click()
            page.wait_for_timeout(200)
            counter_text2 = page.text_content('#hitCounter')
            check('5', '第二次跳轉', counter_text2 is not None and '2/' in counter_text2, counter_text2)

            # 確認有 current 高亮
            current_hit = page.query_selector('.highlight.current')
            check('5', '當前高亮標記存在', current_hit is not None)

        # ============================================================
        # 步驟 6：清除搜尋
        # ============================================================
        print('\n' + '=' * 60)
        print('步驟 6：清除搜尋')
        print('=' * 60)

        page.fill('#searchInput', '')
        page.wait_for_timeout(400)

        remaining_highlights = page.query_selector_all('.highlight')
        check('6', '清空後高亮消失', len(remaining_highlights) == 0, f'剩餘 {len(remaining_highlights)} 個')

        stats_after_clear = page.text_content('#searchStatsText')
        check('6', '統計文字清空', stats_after_clear.strip() == '', f'內容: "{stats_after_clear.strip()}"')

        # ============================================================
        # 步驟 7：年份篩選
        # ============================================================
        print('\n' + '=' * 60)
        print('步驟 7：年份篩選')
        print('=' * 60)

        # 點擊 114 年份篩選 chip
        filter_114 = page.query_selector('.filter-chip[data-year="114"]')
        check('7', '114 年篩選 chip 存在', filter_114 is not None)

        if filter_114:
            filter_114.click()
            page.wait_for_timeout(400)

            is_active = filter_114.evaluate('el => el.classList.contains("active")')
            check('7', '114 chip 變為 active', is_active)

            # 檢查只顯示 114 年的 section
            year_sections = page.query_selector_all('#yearView .year-section')
            visible_sections = []
            for sec in year_sections:
                display = sec.evaluate('el => getComputedStyle(el).display')
                if display != 'none':
                    heading = sec.query_selector('.year-heading')
                    if heading:
                        visible_sections.append(heading.text_content().strip())

            check('7', '只顯示 114年 section',
                  len(visible_sections) == 1 and '114' in visible_sections[0],
                  f'可見: {visible_sections}')

        # 恢復全部年份
        all_year_chip = page.query_selector('.filter-chip[data-year=""]')
        if all_year_chip:
            all_year_chip.click()
            page.wait_for_timeout(300)

        # ============================================================
        # 步驟 8：練習模式
        # ============================================================
        print('\n' + '=' * 60)
        print('步驟 8：練習模式')
        print('=' * 60)

        page.click('#practiceToggle')
        page.wait_for_timeout(400)

        in_practice = page.evaluate('document.body.classList.contains("practice-mode")')
        check('8', '進入練習模式', in_practice)

        score_visible = page.is_visible('#practiceScore')
        check('8', '計分面板顯示', score_visible)

        # 確認 self-score-panel 存在
        score_panels = page.query_selector_all('.self-score-panel')
        check('8', '自我評分面板產生', len(score_panels) > 0, f'{len(score_panels)} 個面板')

        # ============================================================
        # 步驟 9：答題互動（答對）
        # ============================================================
        print('\n' + '=' * 60)
        print('步驟 9：答題互動（答對）')
        print('=' * 60)

        # 先展開第一個 subject-card 讓 score panel 可見
        first_card = page.query_selector('#yearView .subject-card')
        if first_card:
            if not first_card.evaluate('el => el.classList.contains("open")'):
                header = first_card.query_selector('.subject-header')
                if header:
                    header.click()
                    page.wait_for_timeout(300)

        # 找第一個 self-score-panel
        panel1 = page.query_selector('#yearView .self-score-panel')
        check('9', '找到第一個評分面板', panel1 is not None)

        if panel1:
            # 點「顯示答案」
            reveal_btn = panel1.query_selector('.reveal-btn')
            check('9', '「顯示答案」按鈕存在', reveal_btn is not None)
            if reveal_btn:
                reveal_btn.click()
                page.wait_for_timeout(300)

                # 確認答案區顯示
                answer_section = panel1.evaluate_handle('el => el.nextElementSibling')
                revealed = answer_section.evaluate('el => el && el.classList.contains("revealed")')
                check('9', '答案區 revealed', revealed)

                # 確認「答對」「答錯」按鈕出現
                btn_correct = panel1.query_selector('.btn-correct')
                btn_visible = btn_correct.evaluate('el => el.classList.contains("visible")') if btn_correct else False
                check('9', '「答對」按鈕可見', btn_visible)

                if btn_correct and btn_visible:
                    btn_correct.click()
                    page.wait_for_timeout(300)

                    scored = panel1.evaluate('el => el.classList.contains("scored")')
                    check('9', '面板標記 scored', scored)

                    correct_count = page.text_content('#scoreCorrect')
                    total_count = page.text_content('#scoreTotal')
                    check('9', '計分: 1/1', correct_count == '1' and total_count == '1',
                          f'{correct_count}/{total_count}')

        # ============================================================
        # 步驟 10：答題互動（答錯）
        # ============================================================
        print('\n' + '=' * 60)
        print('步驟 10：答題互動（答錯）')
        print('=' * 60)

        # 展開第二張卡片（如果有的話）
        all_cards = page.query_selector_all('#yearView .subject-card')
        if len(all_cards) >= 2:
            second_card = all_cards[1]
            if not second_card.evaluate('el => el.classList.contains("open")'):
                hdr2 = second_card.query_selector('.subject-header')
                if hdr2:
                    hdr2.click()
                    page.wait_for_timeout(300)

        # 找第二個尚未 scored 的 self-score-panel
        all_panels = page.query_selector_all('#yearView .self-score-panel')
        panel2 = None
        for pp in all_panels:
            is_scored = pp.evaluate('el => el.classList.contains("scored")')
            if not is_scored:
                panel2 = pp
                break

        check('10', '找到第二個未評分面板', panel2 is not None)

        if panel2:
            reveal_btn2 = panel2.query_selector('.reveal-btn')
            if reveal_btn2:
                reveal_btn2.click()
                page.wait_for_timeout(300)

                btn_wrong = panel2.query_selector('.btn-wrong')
                btn_w_visible = btn_wrong.evaluate('el => el.classList.contains("visible")') if btn_wrong else False
                check('10', '「答錯」按鈕可見', btn_w_visible)

                if btn_wrong and btn_w_visible:
                    btn_wrong.click()
                    page.wait_for_timeout(300)

                    scored2 = panel2.evaluate('el => el.classList.contains("scored")')
                    was_wrong = panel2.evaluate('el => el.classList.contains("was-wrong")')
                    check('10', '面板標記 scored + was-wrong', scored2 and was_wrong)

        # ============================================================
        # 步驟 11：計分面板驗證
        # ============================================================
        print('\n' + '=' * 60)
        print('步驟 11：計分面板驗證')
        print('=' * 60)

        correct_now = page.text_content('#scoreCorrect')
        total_now = page.text_content('#scoreTotal')
        pct_now = page.text_content('#scorePct')
        check('11', '計分: 1/2 題', correct_now == '1' and total_now == '2',
              f'{correct_now}/{total_now}')
        check('11', '正確率 50%', pct_now.strip() == '50%', f'顯示: {pct_now.strip()}')

        # ============================================================
        # 步驟 12：關閉練習模式
        # ============================================================
        print('\n' + '=' * 60)
        print('步驟 12：關閉練習模式')
        print('=' * 60)

        page.click('#practiceToggle')
        page.wait_for_timeout(400)

        not_practice = not page.evaluate('document.body.classList.contains("practice-mode")')
        check('12', '退出練習模式', not_practice)

        score_hidden = not page.is_visible('#practiceScore')
        check('12', '計分面板隱藏', score_hidden)

        remaining_panels = page.query_selector_all('.self-score-panel')
        check('12', '評分面板已移除', len(remaining_panels) == 0, f'剩餘 {len(remaining_panels)} 個')

        # ============================================================
        # 步驟 13：書籤功能
        # ============================================================
        print('\n' + '=' * 60)
        print('步驟 13：書籤功能')
        print('=' * 60)

        # 清除既有書籤
        page.evaluate('localStorage.removeItem("exam-bookmarks")')

        # 找第一個 bookmark-btn
        bm_btn = page.query_selector('#yearView .bookmark-btn')
        check('13', '書籤按鈕存在', bm_btn is not None)

        if bm_btn:
            # 確認初始為空心星
            initial_text = bm_btn.text_content().strip()
            check('13', '初始為空心星', initial_text == '\u2606', f'文字: {repr(initial_text)}')

            bm_btn.click()
            page.wait_for_timeout(300)

            after_text = bm_btn.text_content().strip()
            is_active = bm_btn.evaluate('el => el.classList.contains("active")')
            check('13', '點擊後變為實心星', after_text == '\u2605' and is_active,
                  f'文字: {repr(after_text)}, active: {is_active}')

        # ============================================================
        # 步驟 14：書籤篩選
        # ============================================================
        print('\n' + '=' * 60)
        print('步驟 14：書籤篩選')
        print('=' * 60)

        page.click('#bookmarkFilter')
        page.wait_for_timeout(400)

        bm_filter_active = page.evaluate('document.getElementById("bookmarkFilter").classList.contains("active")')
        check('14', '書籤篩選啟用', bm_filter_active)

        # 計算可見卡片數量
        visible_cards = page.evaluate('''() => {
            const cards = document.querySelectorAll('#yearView .subject-card');
            let count = 0;
            cards.forEach(c => { if (getComputedStyle(c).display !== 'none') count++; });
            return count;
        }''')
        check('14', '只顯示已加書籤的卡片', visible_cards >= 1, f'可見 {visible_cards} 張')

        # 確認可見的就是有書籤的那張
        total_cards_count = page.evaluate('''() => {
            return document.querySelectorAll('#yearView .subject-card').length;
        }''')
        check('14', '其他卡片被隱藏', visible_cards < total_cards_count,
              f'可見 {visible_cards} / 總共 {total_cards_count}')

        # 關閉書籤篩選
        page.click('#bookmarkFilter')
        page.wait_for_timeout(300)

        # ============================================================
        # 步驟 15：深色模式
        # ============================================================
        print('\n' + '=' * 60)
        print('步驟 15：深色模式')
        print('=' * 60)

        page.click('#darkToggle')
        page.wait_for_timeout(300)

        has_dark = page.evaluate('document.documentElement.classList.contains("dark")')
        check('15', 'html 有 dark class', has_dark)

        # 再點一次恢復
        page.click('#darkToggle')
        page.wait_for_timeout(200)
        no_dark = not page.evaluate('document.documentElement.classList.contains("dark")')
        check('15', '再點恢復淺色模式', no_dark)

        # ============================================================
        # 步驟 16：URL Hash 導航
        # ============================================================
        print('\n' + '=' * 60)
        print('步驟 16：URL Hash 導航')
        print('=' * 60)

        page.goto(f'{BASE}/行政警察學系/行政警察學系考古題總覽.html#year-114', wait_until='networkidle')
        page.wait_for_timeout(500)

        # 確認 sidebar 中 114年 被 active
        sidebar_114_active = page.evaluate('''() => {
            const years = document.querySelectorAll('.sidebar-year');
            for (const y of years) {
                if (y.textContent.trim().startsWith('114') && y.classList.contains('active'))
                    return true;
            }
            return false;
        }''')
        check('16', 'Sidebar 114年 被 active', sidebar_114_active)

        # 確認年份區域在視窗中（或至少存在）
        year114_el = page.query_selector('#year-114')
        check('16', '#year-114 元素存在', year114_el is not None)

        if year114_el:
            # 給 scroll 一點時間完成
            page.wait_for_timeout(300)
            in_view = year114_el.evaluate('''el => {
                const rect = el.getBoundingClientRect();
                return rect.top < window.innerHeight && rect.bottom > 0;
            }''')
            check('16', '#year-114 在可視範圍', in_view)

        # ============================================================
        # 步驟 17：無 Console 錯誤
        # ============================================================
        print('\n' + '=' * 60)
        print('步驟 17：無 Console 錯誤')
        print('=' * 60)

        check('17', '全程無 console.error', len(console_errors) == 0,
              f'{len(console_errors)} 個錯誤' + (f': {console_errors[:5]}' if console_errors else ''))

        # ────────────────────────────────
        browser.close()

finally:
    server.terminate()
    server.wait()

# ============================================================
# 總結
# ============================================================
print('\n' + '=' * 60)
print('測試總結')
print('=' * 60)
passed = sum(1 for r in results if r[2])
failed = sum(1 for r in results if not r[2])
total = len(results)
print(f'  通過: {passed}')
print(f'  失敗: {failed}')
print(f'  總數: {total}')

if failed > 0:
    print('\n失敗項目:')
    for step, name, ok, detail in results:
        if not ok:
            print(f'  \u2717 [{step}] {name}  ({detail})')

print()
sys.exit(0 if failed == 0 else 1)
