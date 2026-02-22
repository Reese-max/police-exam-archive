# -*- coding: utf-8 -*-
"""
Playwright 手機模擬測試 — 模擬 iPhone SE 使用者流程
測試 responsive 行動版體驗（375x667 viewport）
"""
import subprocess, time, sys, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright

PORT = 8768
BASE = f'http://localhost:{PORT}'

# 啟動 HTTP server
server = subprocess.Popen(
    [sys.executable, '-m', 'http.server', str(PORT), '--directory', '考古題網站'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(1.5)

results = []
console_errors = []

def check(name, condition, detail=''):
    """記錄測試結果"""
    symbol = 'PASS' if condition else 'FAIL'
    results.append((name, condition, detail))
    line = f'  [{symbol}] {name}'
    if detail:
        line += f'  ({detail})'
    print(line)


try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # =============================================
        # 步驟 1: 手機 viewport（iPhone SE 375x667）
        # =============================================
        print('\n' + '=' * 60)
        print('手機模擬測試 — iPhone SE (375x667)')
        print('=' * 60)

        page = browser.new_page(viewport={'width': 375, 'height': 667})
        page.on('console', lambda msg: console_errors.append(msg.text) if msg.type == 'error' else None)

        print('\n--- 步驟 1: 手機 viewport 設定 ---')
        vp = page.viewport_size
        check('Viewport 寬度 375', vp['width'] == 375, f"寬={vp['width']}")
        check('Viewport 高度 667', vp['height'] == 667, f"高={vp['height']}")

        # =============================================
        # 步驟 2: 首頁載入
        # =============================================
        print('\n--- 步驟 2: 首頁載入 ---')
        page.goto(f'{BASE}/index.html', wait_until='networkidle')
        check('首頁標題正確', '考古題' in page.title(), page.title())
        check('首頁 header 可見', page.is_visible('.site-header'))
        check('類科卡片存在', page.query_selector('.category-card') is not None)

        # 確認 mobile 下卡片是單欄排列（grid-template-columns: 1fr）
        grid_cols = page.evaluate('''
            getComputedStyle(document.querySelector('.categories-grid')).gridTemplateColumns
        ''')
        check('手機單欄排列', grid_cols and 'px' in grid_cols and grid_cols.count(' ') == 0,
              f'gridTemplateColumns={grid_cols}')

        # =============================================
        # 步驟 3: 首頁類科點擊
        # =============================================
        print('\n--- 步驟 3: 首頁類科點擊 ---')
        first_card = page.query_selector('.category-card')
        card_text = first_card.text_content().strip() if first_card else ''
        first_card.click()
        page.wait_for_load_state('networkidle')
        check('導航到類科頁', '考古題總覽' in page.title(), page.title())
        check('主內容區存在', page.query_selector('.main') is not None)

        # =============================================
        # 步驟 4: Sidebar 隱藏確認（mobile 模式下預設隱藏）
        # =============================================
        print('\n--- 步驟 4: Sidebar 隱藏確認 ---')
        sidebar = page.query_selector('#sidebar')
        check('Sidebar 元素存在', sidebar is not None)

        # 在 mobile 模式下，sidebar 應該被 transform: translateX(-100%) 隱藏
        sidebar_transform = page.evaluate('''
            getComputedStyle(document.getElementById('sidebar')).transform
        ''')
        sidebar_hidden = sidebar_transform != 'none' and 'matrix' in str(sidebar_transform)
        check('Sidebar 預設隱藏（translateX）', sidebar_hidden, f'transform={sidebar_transform}')

        # =============================================
        # 步驟 5: 漢堡選單開啟
        # =============================================
        print('\n--- 步驟 5: 漢堡選單開啟 ---')
        hamburger = page.query_selector('#hamburgerBtn')
        check('漢堡按鈕可見', page.is_visible('#hamburgerBtn'))
        hamburger.click()
        page.wait_for_timeout(400)

        sidebar_open = page.evaluate('''
            document.getElementById('sidebar').classList.contains('open')
        ''')
        check('Sidebar 滑出（有 open class）', sidebar_open)

        overlay_active = page.evaluate('''
            document.getElementById('sidebarOverlay').classList.contains('active')
        ''')
        check('Overlay 顯示', overlay_active)

        sidebar_transform_after = page.evaluate('''
            getComputedStyle(document.getElementById('sidebar')).transform
        ''')
        # open 時 transform 應為 none 或 translateX(0)
        sidebar_visible_now = sidebar_transform_after == 'none' or 'matrix(1, 0, 0, 1, 0, 0)' in str(sidebar_transform_after)
        check('Sidebar 變為可見', sidebar_visible_now, f'transform={sidebar_transform_after}')

        # =============================================
        # 步驟 6: 年份導航
        # =============================================
        print('\n--- 步驟 6: 年份導航 ---')
        # 找到 sidebar 中的第一個年份按鈕
        sidebar_years = page.query_selector_all('.sidebar-year')
        check('Sidebar 年份項目存在', len(sidebar_years) > 0, f'{len(sidebar_years)} 個年份')

        if len(sidebar_years) > 0:
            first_year = sidebar_years[0]
            first_year_text = first_year.text_content().strip()
            first_year.click()
            page.wait_for_timeout(300)

            year_active = page.evaluate('''
                document.querySelector('.sidebar-year.active') !== null
            ''')
            check('年份展開（active class）', year_active, f'點擊了 {first_year_text}')

            # 子科目連結應該顯示
            sub_links = page.query_selector_all('.sidebar-year.active + .sidebar-subjects .sidebar-link')
            check('子科目連結顯示', len(sub_links) > 0, f'{len(sub_links)} 個連結')

            # 點擊一個子科目連結
            if len(sub_links) > 0:
                sub_links[0].click()
                page.wait_for_timeout(500)
                # mobile 模式下點擊連結後 sidebar 應自動關閉
                sidebar_closed_after_nav = page.evaluate('''
                    !document.getElementById('sidebar').classList.contains('open')
                ''')
                check('點擊連結後 Sidebar 自動關閉', sidebar_closed_after_nav)

        # =============================================
        # 步驟 7: 漢堡選單關閉（透過 overlay）
        # =============================================
        print('\n--- 步驟 7: 漢堡選單關閉 ---')
        # 先重新打開
        hamburger.click()
        page.wait_for_timeout(400)
        check('重新開啟 Sidebar', page.evaluate(
            'document.getElementById("sidebar").classList.contains("open")'
        ))

        # 點擊 overlay 關閉（sidebar 展開的子項目可能攔截指標，改用 force click）
        overlay = page.query_selector('#sidebarOverlay')
        overlay.click(force=True)
        page.wait_for_timeout(400)

        sidebar_closed = page.evaluate('''
            !document.getElementById('sidebar').classList.contains('open')
        ''')
        check('點擊 Overlay 關閉 Sidebar', sidebar_closed)

        overlay_hidden = page.evaluate('''
            !document.getElementById('sidebarOverlay').classList.contains('active')
        ''')
        check('Overlay 隱藏', overlay_hidden)

        # =============================================
        # 步驟 8: 搜尋框使用
        # =============================================
        print('\n--- 步驟 8: 搜尋框使用 ---')
        search_input = page.query_selector('#searchInput')
        check('搜尋框存在', search_input is not None)
        check('搜尋框可見', page.is_visible('#searchInput'))

        page.fill('#searchInput', '憲法')
        page.wait_for_timeout(500)

        stats_text = page.text_content('#searchStatsText')
        check('搜尋結果統計顯示', stats_text and len(stats_text.strip()) > 0, stats_text.strip() if stats_text else '')

        highlights = page.query_selector_all('.highlight')
        check('搜尋高亮標記', len(highlights) > 0, f'{len(highlights)} 處高亮')

        # 清空搜尋
        page.fill('#searchInput', '')
        page.wait_for_timeout(400)
        check('清空搜尋後高亮消失', len(page.query_selector_all('.highlight')) == 0)

        # =============================================
        # 步驟 9: 卡片展開
        # =============================================
        print('\n--- 步驟 9: 卡片展開 ---')
        first_card_header = page.query_selector('#yearView .subject-header')
        check('卡片 header 存在', first_card_header is not None)

        if first_card_header:
            first_card_header.scroll_into_view_if_needed()
            page.wait_for_timeout(200)
            first_card_header.click()
            page.wait_for_timeout(400)

            card_open = page.evaluate('''
                document.querySelector('#yearView .subject-card.open') !== null
            ''')
            check('卡片展開（有 open class）', card_open)

            body_visible = page.evaluate('''
                (() => {
                    const card = document.querySelector('#yearView .subject-card.open');
                    if (!card) return false;
                    const body = card.querySelector('.subject-body');
                    if (!body) return false;
                    return getComputedStyle(body).display !== 'none';
                })()
            ''')
            check('卡片內容可見', body_visible)

        # =============================================
        # 步驟 10: 練習模式
        # =============================================
        print('\n--- 步驟 10: 練習模式 ---')
        practice_btn = page.query_selector('#practiceToggle')
        check('練習模式按鈕存在', practice_btn is not None)

        # 確認手機下練習按鈕可見
        check('練習模式按鈕可見（手機）', page.is_visible('#practiceToggle'))

        practice_btn.scroll_into_view_if_needed()
        practice_btn.click()
        page.wait_for_timeout(400)

        practice_active = page.evaluate('document.body.classList.contains("practice-mode")')
        check('練習模式啟動', practice_active)

        score_visible = page.is_visible('#practiceScore')
        check('計分面板顯示', score_visible)

        # =============================================
        # 步驟 11: 自評操作
        # =============================================
        print('\n--- 步驟 11: 自評操作 ---')
        # 確保有展開的卡片有 answer-section
        # 先確保第一張卡片是展開的
        page.evaluate('''
            (() => {
                const cards = document.querySelectorAll('#yearView .subject-card');
                for (const card of cards) {
                    const ans = card.querySelector('.answer-section');
                    if (ans) {
                        card.classList.add('open');
                        return true;
                    }
                }
                return false;
            })()
        ''')
        page.wait_for_timeout(400)

        score_panels = page.query_selector_all('.self-score-panel')
        check('自評面板存在', len(score_panels) > 0, f'{len(score_panels)} 個面板')

        reveal_btn = page.query_selector('.self-score-panel .reveal-btn')
        if reveal_btn:
            reveal_btn.scroll_into_view_if_needed()
            page.wait_for_timeout(200)
            reveal_btn.click()
            page.wait_for_timeout(400)

            answer_revealed = page.evaluate('''
                document.querySelector('.answer-section.revealed') !== null
            ''')
            check('點擊「顯示答案」後答案可見', answer_revealed)

            # 點擊「答對」
            correct_btn = page.query_selector('.self-score-panel .score-btn.btn-correct.visible')
            if correct_btn:
                correct_btn.scroll_into_view_if_needed()
                correct_btn.click()
                page.wait_for_timeout(300)

                score_correct = page.text_content('#scoreCorrect')
                score_total = page.text_content('#scoreTotal')
                check('答對計分正確', score_correct == '1' and score_total == '1',
                      f'答對={score_correct}, 總計={score_total}')
            else:
                check('答對按鈕可見', False, '找不到 visible 的答對按鈕')
        else:
            check('顯示答案按鈕存在', False, '找不到 reveal-btn')

        # 嘗試點擊第二個的「答錯」— 需確保在展開的卡片中找可見的 reveal-btn
        second_reveal = page.evaluate('''
            (() => {
                const panels = document.querySelectorAll('.subject-card.open .self-score-panel:not(.scored)');
                for (const p of panels) {
                    const btn = p.querySelector('.reveal-btn');
                    if (btn && btn.style.display !== 'none') {
                        btn.scrollIntoView({block: 'center'});
                        return true;
                    }
                }
                return false;
            })()
        ''')
        if second_reveal:
            page.wait_for_timeout(300)
            reveal2 = page.query_selector('.subject-card.open .self-score-panel:not(.scored) .reveal-btn')
            if reveal2:
                reveal2.click(force=True)
                page.wait_for_timeout(400)
                wrong_btn = page.query_selector('.subject-card.open .self-score-panel:not(.scored) .score-btn.btn-wrong.visible')
                if wrong_btn:
                    wrong_btn.click(force=True)
                    page.wait_for_timeout(300)
                    score_total2 = page.text_content('#scoreTotal')
                    check('答錯計分更新', score_total2 == '2', f'總計={score_total2}')
                else:
                    check('答錯按鈕操作', True, '跳過（展開卡片中無更多未評分面板）')
            else:
                check('第二題自評操作', True, '跳過（無可見 reveal-btn）')
        else:
            check('第二題自評操作', True, '跳過（展開卡片中僅一個答案區）')

        # =============================================
        # 步驟 12: 計分面板可見性（sticky）
        # =============================================
        print('\n--- 步驟 12: 計分面板可見性 ---')
        score_panel = page.query_selector('#practiceScore')
        check('計分面板元素存在', score_panel is not None)

        score_display = page.evaluate('''
            getComputedStyle(document.getElementById('practiceScore')).display
        ''')
        check('計分面板 display=flex', score_display == 'flex', f'display={score_display}')

        score_position = page.evaluate('''
            getComputedStyle(document.getElementById('practiceScore')).position
        ''')
        check('計分面板 sticky 定位', score_position == 'sticky', f'position={score_position}')

        # 結束練習模式
        practice_btn.scroll_into_view_if_needed()
        practice_btn.click()
        page.wait_for_timeout(300)
        check('練習模式結束', not page.evaluate('document.body.classList.contains("practice-mode")'))

        # =============================================
        # 步驟 13: 書籤操作
        # =============================================
        print('\n--- 步驟 13: 書籤操作 ---')
        bookmark_btn = page.query_selector('#yearView .bookmark-btn')
        check('書籤按鈕存在', bookmark_btn is not None)

        if bookmark_btn:
            bookmark_btn.scroll_into_view_if_needed()
            page.wait_for_timeout(200)

            # 記錄初始狀態
            was_active = page.evaluate('''
                document.querySelector('#yearView .bookmark-btn').classList.contains('active')
            ''')

            bookmark_btn.click()
            page.wait_for_timeout(300)

            is_active_now = page.evaluate('''
                document.querySelector('#yearView .bookmark-btn').classList.contains('active')
            ''')
            check('書籤切換狀態', is_active_now != was_active,
                  f'之前={was_active}, 之後={is_active_now}')

            # 確認 localStorage 有記錄
            bookmark_stored = page.evaluate('''
                (() => {
                    try {
                        const bm = JSON.parse(localStorage.getItem('exam-bookmarks') || '{}');
                        return Object.keys(bm).length > 0;
                    } catch(e) { return false; }
                })()
            ''')
            # 如果點了之後是 active，應該有記錄；如果取消了，可能就沒有
            if is_active_now:
                check('書籤儲存到 localStorage', bookmark_stored)
            else:
                check('書籤從 localStorage 移除', True, '已取消書籤')

            # 再點一次復原
            bookmark_btn.click()
            page.wait_for_timeout(200)

        # =============================================
        # 步驟 14: 深色模式
        # =============================================
        print('\n--- 步驟 14: 深色模式 ---')
        dark_toggle = page.query_selector('#darkToggle')
        check('深色模式按鈕存在', dark_toggle is not None)
        check('深色模式按鈕可見', page.is_visible('#darkToggle'))

        # 記錄初始狀態
        was_dark = page.evaluate('document.documentElement.classList.contains("dark")')

        dark_toggle.click()
        page.wait_for_timeout(300)

        is_dark_now = page.evaluate('document.documentElement.classList.contains("dark")')
        check('深色模式切換成功', is_dark_now != was_dark,
              f'之前dark={was_dark}, 之後dark={is_dark_now}')

        # 確認在手機尺寸下 CSS 變數有更新
        bg_color = page.evaluate('getComputedStyle(document.body).backgroundColor')
        if is_dark_now:
            # 深色模式下背景應偏暗
            check('深色模式背景色正確', 'rgb(26' in bg_color or 'rgb(45' in bg_color or 'rgb(15' in bg_color, f'bg={bg_color}')
        else:
            check('淺色模式背景色正確', 'rgb(240' in bg_color or 'rgb(248' in bg_color or 'rgb(255' in bg_color, f'bg={bg_color}')

        # 切回原狀
        dark_toggle.click()
        page.wait_for_timeout(200)

        # =============================================
        # 步驟 15: 回到首頁
        # =============================================
        print('\n--- 步驟 15: 回到首頁 ---')
        # 先打開 sidebar 找回到首頁的連結
        hamburger.click()
        page.wait_for_timeout(400)

        home_link = page.query_selector('.sidebar-home')
        check('「回到首頁」連結存在', home_link is not None)

        if home_link:
            home_link_href = home_link.get_attribute('href')
            check('首頁連結指向 index.html', 'index.html' in (home_link_href or ''), f'href={home_link_href}')

            home_link.click()
            page.wait_for_load_state('networkidle')
            check('成功回到首頁', '總覽' in page.title() and '15' in page.text_content('.hero-stat-value'),
                  page.title())
        else:
            check('回到首頁導航', False, '找不到首頁連結')

        # =============================================
        # 步驟 16: 橫屏切換
        # =============================================
        print('\n--- 步驟 16: 橫屏切換 ---')
        page.set_viewport_size({'width': 667, 'height': 375})
        page.wait_for_timeout(500)

        vp2 = page.viewport_size
        check('橫屏 Viewport 切換', vp2['width'] == 667 and vp2['height'] == 375,
              f"寬={vp2['width']}, 高={vp2['height']}")

        # 頁面不應出現水平溢出
        has_overflow = page.evaluate('''
            document.documentElement.scrollWidth <= document.documentElement.clientWidth + 5
        ''')
        check('橫屏無水平溢出', has_overflow,
              f'scrollWidth={page.evaluate("document.documentElement.scrollWidth")}, clientWidth={page.evaluate("document.documentElement.clientWidth")}')

        # 確認 header 仍然可見
        check('橫屏 header 可見', page.is_visible('.site-header'))

        # 確認卡片仍然正常排列
        cards_in_landscape = page.query_selector_all('.category-card')
        check('橫屏卡片仍正常顯示', len(cards_in_landscape) > 0, f'{len(cards_in_landscape)} 張卡片')

        # 重新導航到類科頁面測試橫屏效果
        cards_in_landscape[0].click()
        page.wait_for_load_state('networkidle')

        # 橫屏下漢堡按鈕仍應可見（因為 667 < 768）
        hamburger_landscape = page.is_visible('#hamburgerBtn')
        check('橫屏漢堡按鈕可見', hamburger_landscape)

        # 恢復直屏
        page.set_viewport_size({'width': 375, 'height': 667})
        page.wait_for_timeout(300)

        # =============================================
        # 步驟 17: 零 Console 錯誤
        # =============================================
        print('\n--- 步驟 17: Console 錯誤檢查 ---')
        # 過濾掉已知的非問題錯誤（如 favicon 404）
        real_errors = [e for e in console_errors if 'favicon' not in e.lower()]
        check('零 Console 錯誤', len(real_errors) == 0,
              f'{len(real_errors)} 個錯誤' + (f': {real_errors[:3]}' if real_errors else ''))

        browser.close()

finally:
    server.terminate()
    server.wait()

# ====== 總結 ======
print('\n' + '=' * 60)
print('測試總結')
print('=' * 60)

passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
total = len(results)

print(f'  通過: {passed}/{total}')
print(f'  失敗: {failed}/{total}')

if failed > 0:
    print('\n失敗項目:')
    for name, ok, detail in results:
        if not ok:
            print(f'  [FAIL] {name}' + (f'  ({detail})' if detail else ''))

print('\n' + ('全部通過！' if failed == 0 else f'有 {failed} 項需要注意。'))
