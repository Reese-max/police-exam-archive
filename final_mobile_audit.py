"""最終手機 UX 審計 — Playwright 模擬 5 種角色"""
import subprocess, time, json, sys, os

PORT = 8799
ROOT = os.path.join(os.path.dirname(__file__), '考古題網站')

# 啟動 HTTP server
srv = subprocess.Popen(
    [sys.executable, '-m', 'http.server', str(PORT), '--directory', ROOT],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(1)
BASE = f'http://localhost:{PORT}'

from playwright.sync_api import sync_playwright

passed = 0
failed = 0
issues = []

def check(name, cond, detail=''):
    global passed, failed
    if cond:
        passed += 1
        print(f'  ✓ {name}')
    else:
        failed += 1
        issues.append(f'{name}: {detail}')
        print(f'  ✗ {name} — {detail}')

try:
    with sync_playwright() as p:
        # iPhone 12 Pro 模擬
        iphone = p.devices['iPhone 12 Pro']
        browser = p.chromium.launch()

        # =============================================
        # 角色 1: 新手考生 — 第一次進入
        # =============================================
        print('\n=== 角色 1: 新手考生 ===')
        ctx = browser.new_context(**iphone)
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)

        page.goto(f'{BASE}/index.html', wait_until='networkidle')
        check('Index 載入', '考古題' in page.title())

        # 15 類科連結可見
        links = page.query_selector_all('.category-card a, a[href*="考古題總覽"]')
        check('類科連結可見', len(links) >= 15, f'找到 {len(links)} 個')

        # 點擊第一個類科
        first_link = links[0] if links else None
        if first_link:
            first_link.click()
            page.wait_for_load_state('networkidle')
            check('類科頁面載入', page.query_selector('.page-title') is not None)

        # 漢堡選單
        hamburger = page.query_selector('#hamburgerBtn')
        check('漢堡選單存在', hamburger is not None)
        if hamburger:
            hamburger.click()
            page.wait_for_timeout(400)
            sidebar = page.query_selector('#sidebar')
            is_open = sidebar.evaluate('el => el.classList.contains("open")')
            check('漢堡打開 sidebar', is_open)
            # 點擊 overlay 右側區域（sidebar 外）關閉
            overlay = page.query_selector('#sidebarOverlay')
            if overlay:
                # sidebar 寬度 280px，點擊 x=350 確保在 sidebar 外
                page.mouse.click(350, 400)
                page.wait_for_timeout(400)
                is_closed = sidebar.evaluate('el => !el.classList.contains("open")')
                check('Overlay 關閉 sidebar', is_closed)

        # 搜尋
        search = page.query_selector('#searchInput')
        if search:
            search.fill('憲法')
            page.wait_for_timeout(400)
            stats = page.query_selector('#searchStatsText')
            check('搜尋有結果', stats and '匹配' in stats.text_content())
            highlights = page.query_selector_all('.highlight')
            check('高亮標記存在', len(highlights) > 0, f'{len(highlights)} 個')

        check('角色1 零 console error', len(errs) == 0, f'{len(errs)} errors: {errs[:3]}')
        ctx.close()

        # =============================================
        # 角色 2: 密集複習者 — 書籤+篩選+練習
        # =============================================
        print('\n=== 角色 2: 密集複習者 ===')
        ctx = browser.new_context(**iphone)
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)

        page.goto(f'{BASE}/行政警察/行政警察考古題總覽.html', wait_until='networkidle')
        check('行政警察頁面載入', page.query_selector('.page-title') is not None)

        # 展開卡片
        headers = page.query_selector_all('.subject-header')
        if len(headers) >= 3:
            for h in headers[:3]:
                h.click()
                page.wait_for_timeout(150)
            open_cards = page.query_selector_all('.subject-card.open')
            check('展開 3 張卡片', len(open_cards) >= 3)

        # 書籤
        bm_btns = page.query_selector_all('.bookmark-btn')
        if len(bm_btns) >= 2:
            bm_btns[0].click()
            page.wait_for_timeout(100)
            bm_btns[1].click()
            page.wait_for_timeout(100)
            active_bm = page.query_selector_all('.bookmark-btn.active')
            check('書籤設定成功', len(active_bm) >= 2)

        # 書籤篩選
        bmf = page.query_selector('#bookmarkFilter')
        if bmf:
            bmf.click()
            page.wait_for_timeout(300)
            visible = page.evaluate('''() => {
                return document.querySelectorAll('#yearView .subject-card:not([style*="display: none"])').length
            }''')
            check('書籤篩選', visible >= 2 and visible <= 3, f'{visible} 張可見')

        # 練習模式
        pt = page.query_selector('#practiceToggle')
        if pt:
            # 先取消書籤篩選
            bmf.click()
            page.wait_for_timeout(200)
            pt.click()
            page.wait_for_timeout(300)
            score = page.query_selector('.practice-score.visible')
            check('練習模式啟用', score is not None)

            # 確保至少有一張卡片是展開的
            first_header = page.query_selector('.subject-header')
            if first_header:
                first_card = first_header.evaluate('el => el.closest(".subject-card").classList.contains("open")')
                if not first_card:
                    first_header.click()
                    page.wait_for_timeout(300)
            # 點擊「顯示答案」
            reveal = page.query_selector('.self-score-panel .reveal-btn')
            if reveal:
                reveal.click()
                page.wait_for_timeout(200)
                revealed = page.query_selector('.answer-section.revealed')
                check('答案顯示', revealed is not None)

                # 點擊「答對」
                correct_btn = page.query_selector('.score-btn.btn-correct.visible')
                if correct_btn:
                    correct_btn.click()
                    page.wait_for_timeout(200)
                    pct = page.query_selector('#scorePct')
                    check('計分更新', pct and pct.text_content() != '--')

        check('角色2 零 console error', len(errs) == 0, f'{len(errs)} errors: {errs[:3]}')
        ctx.close()

        # =============================================
        # 角色 3: 深色模式用戶
        # =============================================
        print('\n=== 角色 3: 深色模式用戶 ===')
        ctx = browser.new_context(**iphone, color_scheme='dark')
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)

        page.goto(f'{BASE}/資訊管理/資訊管理考古題總覽.html', wait_until='networkidle')

        # 系統偏好深色 → 自動啟用
        is_dark = page.evaluate('() => document.documentElement.classList.contains("dark")')
        check('系統偏好深色自動啟用', is_dark)

        # 深色模式下搜尋
        search = page.query_selector('#searchInput')
        if search:
            search.fill('資料庫')
            page.wait_for_timeout(400)
            highlights = page.query_selector_all('.highlight')
            check('深色模式搜尋高亮', len(highlights) > 0)
            # 高亮顏色在深色模式下應為暗色系
            if highlights:
                bg = highlights[0].evaluate('el => getComputedStyle(el).backgroundColor')
                check('深色高亮非白色', 'rgb(255' not in bg, f'bg={bg}')

        # 切換回淺色
        toggle = page.query_selector('#darkToggle')
        if toggle:
            toggle.click()
            page.wait_for_timeout(300)
            is_light = page.evaluate('() => !document.documentElement.classList.contains("dark")')
            check('切換回淺色', is_light)

        # 再切回深色
        if toggle:
            toggle.click()
            page.wait_for_timeout(300)
            is_dark2 = page.evaluate('() => document.documentElement.classList.contains("dark")')
            check('再切回深色', is_dark2)

        # 清除搜尋後展開卡片在深色模式
        search.fill('')
        page.wait_for_timeout(400)
        visible_header = page.evaluate('''() => {
            const cards = document.querySelectorAll('.subject-card');
            for (const c of cards) {
                if (c.style.display !== 'none') {
                    const h = c.querySelector('.subject-header');
                    if (h) { h.click(); return true; }
                }
            }
            return false;
        }''')
        check('展開卡片', visible_header)
        page.wait_for_timeout(200)
        body_bg = page.evaluate('''() => {
            const b = document.querySelector('.subject-card.open .subject-body');
            return b ? getComputedStyle(b).backgroundColor : 'none';
        }''')
        check('深色卡片內容背景', body_bg != 'rgb(255, 255, 255)', f'bg={body_bg}')

        # 匯出面板在深色模式
        exp_btn = page.query_selector('#exportBtn')
        if exp_btn:
            exp_btn.click()
            page.wait_for_timeout(300)
            exp_panel = page.query_selector('#exportPanel')
            panel_bg = exp_panel.evaluate('el => getComputedStyle(el).backgroundColor') if exp_panel else ''
            check('深色匯出面板背景', panel_bg != 'rgb(255, 255, 255)', f'bg={panel_bg}')
            # 關閉
            cancel = page.query_selector('.export-cancel')
            if cancel:
                cancel.click()
                page.wait_for_timeout(200)

        check('角色3 零 console error', len(errs) == 0, f'{len(errs)} errors: {errs[:3]}')
        ctx.close()

        # =============================================
        # 角色 4: Galaxy Fold 極端窄螢幕
        # =============================================
        print('\n=== 角色 4: Galaxy Fold 極端窄螢幕 (280px) ===')
        ctx = browser.new_context(
            viewport={'width': 280, 'height': 653},
            user_agent='Mozilla/5.0 (Linux; Android 11) Mobile',
            is_mobile=True, has_touch=True
        )
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)

        page.goto(f'{BASE}/消防警察/消防警察考古題總覽.html', wait_until='networkidle')
        check('Galaxy Fold 頁面載入', page.query_selector('.page-title') is not None)

        # 標題不溢出
        title = page.query_selector('.page-title')
        if title:
            overflow = title.evaluate('el => el.scrollWidth > el.clientWidth')
            check('標題不水平溢出', not overflow)

        # body 不水平滾動
        body_overflow = page.evaluate('() => document.body.scrollWidth > document.body.clientWidth')
        check('Body 不水平溢出', not body_overflow, f'scrollW={page.evaluate("()=>document.body.scrollWidth")}, clientW={page.evaluate("()=>document.body.clientWidth")}')

        # toolbar 按鈕可見
        toolbar_btns = page.query_selector_all('.toolbar-btn')
        for btn in toolbar_btns[:3]:
            bbox = btn.bounding_box()
            if bbox:
                check(f'Toolbar 按鈕可觸碰 ({btn.text_content().strip()[:8]})', bbox['height'] >= 44, f'h={bbox["height"]}')
                break

        # 搜尋框不被截斷
        search = page.query_selector('#searchInput')
        if search:
            bbox = search.bounding_box()
            check('搜尋框寬度適當', bbox and bbox['width'] >= 240, f'w={bbox["width"] if bbox else 0}')

        check('角色4 零 console error', len(errs) == 0, f'{len(errs)} errors: {errs[:3]}')
        ctx.close()

        # =============================================
        # 角色 5: 鍵盤 + 無障礙專家
        # =============================================
        print('\n=== 角色 5: 鍵盤 + 無障礙 ===')
        ctx = browser.new_context(**iphone)
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)

        page.goto(f'{BASE}/鑑識科學/鑑識科學考古題總覽.html', wait_until='networkidle')

        # ARIA 完整性
        search_box = page.query_selector('#searchInput')
        check('搜尋框 aria-label', search_box and search_box.get_attribute('aria-label') is not None)

        dark_toggle = page.query_selector('#darkToggle')
        check('深色模式 aria-label', dark_toggle and dark_toggle.get_attribute('aria-label') is not None)

        back_top = page.query_selector('#backToTop')
        check('回頂部 aria-label', back_top and back_top.get_attribute('aria-label') is not None)

        hamburger = page.query_selector('#hamburgerBtn')
        check('漢堡選單 aria-label', hamburger and hamburger.get_attribute('aria-label') is not None)

        # subject-header role + aria-expanded
        headers = page.query_selector_all('.subject-header')
        header_aria = all(h.get_attribute('role') == 'button' and h.get_attribute('aria-expanded') is not None for h in headers[:5])
        check('卡片標題 role=button + aria-expanded', header_aria)

        # skip-link
        skip = page.query_selector('.skip-link')
        check('Skip link 存在', skip is not None)

        # focus-visible 樣式
        has_focus_visible = page.evaluate('''() => {
            for (const sheet of document.styleSheets) {
                try {
                    for (const rule of sheet.cssRules) {
                        if (rule.cssText && rule.cssText.includes('focus-visible')) return true;
                    }
                } catch(e) { /* cross-origin stylesheet */ }
            }
            return false;
        }''')
        check('focus-visible 樣式存在', has_focus_visible)

        # role=search
        role_search = page.query_selector('[role="search"]')
        check('role=search 搜尋區域', role_search is not None)

        # 書籤 aria-pressed
        bm_btn = page.query_selector('.bookmark-btn')
        check('書籤 aria-pressed', bm_btn and bm_btn.get_attribute('aria-pressed') is not None)

        # Escape 關鍵字清除
        search_input = page.query_selector('#searchInput')
        if search_input:
            search_input.fill('測試')
            page.wait_for_timeout(400)
            page.keyboard.press('Escape')
            page.wait_for_timeout(200)
            val = search_input.evaluate('el => el.value')
            check('Escape 清除搜尋', val == '')

        # Ctrl+K 聚焦搜尋
        page.keyboard.press('Control+k')
        page.wait_for_timeout(200)
        focused = page.evaluate('() => document.activeElement.id')
        check('Ctrl+K 聚焦搜尋', focused == 'searchInput')

        check('角色5 零 console error', len(errs) == 0, f'{len(errs)} errors: {errs[:3]}')
        ctx.close()

        # =============================================
        # 角色 6: 橫屏平板用戶
        # =============================================
        print('\n=== 角色 6: 橫屏平板 (iPad landscape) ===')
        ctx = browser.new_context(
            viewport={'width': 1024, 'height': 768},
            user_agent='Mozilla/5.0 (iPad; CPU OS 15_0 like Mac OS X) AppleWebKit/605.1.15',
            is_mobile=True, has_touch=True
        )
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)

        page.goto(f'{BASE}/刑事警察/刑事警察考古題總覽.html', wait_until='networkidle')
        check('iPad 頁面載入', page.query_selector('.page-title') is not None)

        # sidebar 可見（>768px 應顯示 sidebar）
        sidebar = page.query_selector('#sidebar')
        sb_transform = sidebar.evaluate('el => getComputedStyle(el).transform')
        check('iPad sidebar 可見', sb_transform == 'none' or sb_transform == 'matrix(1, 0, 0, 1, 0, 0)')

        # 搜尋 + 展開 + 練習一條龍
        search = page.query_selector('#searchInput')
        search.fill('偵查')
        page.wait_for_timeout(400)
        stats = page.query_selector('#searchStatsText')
        check('iPad 搜尋正常', stats and '匹配' in stats.text_content())

        # 科目瀏覽切換
        sv_btn = page.query_selector('#viewSubject')
        if sv_btn:
            sv_btn.click()
            page.wait_for_timeout(500)
            sv_visible = page.evaluate('() => document.getElementById("subjectView").style.display !== "none"')
            check('iPad 科目瀏覽', sv_visible)

        check('角色6 零 console error', len(errs) == 0, f'{len(errs)} errors: {errs[:3]}')
        ctx.close()

        # =============================================
        # 角色 7: 列印預覽
        # =============================================
        print('\n=== 角色 7: 列印品質 ===')
        ctx = browser.new_context(**iphone)
        page = ctx.new_page()
        errs = []
        page.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)

        page.goto(f'{BASE}/水上警察/水上警察考古題總覽.html', wait_until='networkidle')

        # 檢查列印 CSS 規則存在
        print_rules = page.evaluate('''() => {
            let count = 0;
            for (const s of document.styleSheets) {
                try {
                    for (const r of s.cssRules) {
                        if (r.type === CSSRule.MEDIA_RULE && r.conditionText === 'print') count++;
                    }
                } catch(e) {}
            }
            return count;
        }''')
        check('列印 CSS 規則存在', print_rules > 0, f'{print_rules} 條')

        # 列印時隱藏的元素
        hidden_in_print = ['sidebar', 'search-box', 'toolbar', 'dark-toggle', 'back-to-top', 'hamburger', 'practice-score']
        for cls in hidden_in_print:
            rule_exists = page.evaluate(f'''() => {{
                for (const s of document.styleSheets) {{
                    try {{
                        for (const r of s.cssRules) {{
                            if (r.cssText && r.cssText.includes('print') && r.cssText.includes('.{cls}')) return true;
                        }}
                    }} catch(e) {{}}
                }}
                return false;
            }}''')
            check(f'列印隱藏 .{cls}', rule_exists)

        check('角色7 零 console error', len(errs) == 0, f'{len(errs)} errors: {errs[:3]}')
        ctx.close()

        browser.close()

except Exception as e:
    print(f'\n!!! 測試異常: {e}')
    import traceback
    traceback.print_exc()
finally:
    srv.terminate()

# === 總結 ===
print(f'\n{"="*60}')
print(f'  最終手機 UX 審計總結')
print(f'{"="*60}')
print(f'  通過: {passed}/{passed+failed}')
print(f'  失敗: {failed}/{passed+failed}')
if issues:
    print(f'\n  發現問題:')
    for i, iss in enumerate(issues, 1):
        print(f'    {i}. {iss}')
print(f'\n  通過率: {passed/(passed+failed)*100:.1f}%' if (passed+failed) > 0 else '')
print(f'{"="*60}')
