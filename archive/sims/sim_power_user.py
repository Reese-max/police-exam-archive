# -*- coding: utf-8 -*-
"""Playwright 進階用戶模擬測試 — 跨類科瀏覽、壓力測試、邊界情境"""
import subprocess, time, sys, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright

PORT = 8769
BASE = f'http://localhost:{PORT}'
SITE_DIR = '考古題網站'

# 啟動 HTTP server
server = subprocess.Popen(
    [sys.executable, '-m', 'http.server', str(PORT), '--directory', SITE_DIR],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(1.5)

results = []
console_errors_global = []

def check(name, condition, detail=''):
    symbol = '\u2713' if condition else '\u2717'
    results.append((name, condition, detail))
    print(f'  {symbol} {name}' + (f'  ({detail})' if detail else ''))

# ===== 類科對應表 =====
CATEGORIES = {
    '行政警察學系': '行政警察學系/行政警察學系考古題總覽.html',
    '刑事警察學系': '刑事警察學系/刑事警察學系考古題總覽.html',
    '消防學系': '消防學系/消防學系考古題總覽.html',
    '鑑識科學學系': '鑑識科學學系/鑑識科學學系考古題總覽.html',
    '資訊管理學系': '資訊管理學系/資訊管理學系考古題總覽.html',
}

SEARCH_KEYWORDS = {
    '行政警察學系': '憲法',
    '刑事警察學系': '偵查',
    '消防學系': '消防',
    '鑑識科學學系': '鑑識',
    '資訊管理學系': '資訊',
}

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        # 收集全域 console error 的輔助函式
        def make_page():
            pg = context.new_page()
            pg.on('console', lambda msg: console_errors_global.append(msg.text) if msg.type == 'error' else None)
            return pg

        # =================================================================
        # 測試 1: 多類科巡覽
        # =================================================================
        print('\n=== 測試 1: 多類科巡覽 ===')
        page = make_page()
        for cat_name, cat_path in CATEGORIES.items():
            url = f'{BASE}/{cat_path}'
            page.goto(url, wait_until='networkidle')
            title_ok = cat_name in page.title()
            cards = page.query_selector_all('.subject-card')
            check(f'{cat_name} 頁面載入', title_ok, page.title())
            check(f'{cat_name} 有題目卡片', len(cards) > 0, f'{len(cards)} 張')
        page.close()

        # =================================================================
        # 測試 2: 各類科搜尋
        # =================================================================
        print('\n=== 測試 2: 各類科搜尋 ===')
        page = make_page()
        for cat_name, cat_path in CATEGORIES.items():
            url = f'{BASE}/{cat_path}'
            page.goto(url, wait_until='networkidle')
            keyword = SEARCH_KEYWORDS[cat_name]
            page.fill('#searchInput', keyword)
            page.wait_for_timeout(400)
            stats = page.text_content('#searchStatsText')
            highlights = page.query_selector_all('.highlight')
            check(f'{cat_name} 搜尋「{keyword}」有結果', '找到' in stats, stats.strip())
            check(f'{cat_name} 搜尋有高亮', len(highlights) > 0, f'{len(highlights)} 處')
        page.close()

        # =================================================================
        # 測試 3: 快速功能切換
        # =================================================================
        print('\n=== 測試 3: 快速功能切換 ===')
        page = make_page()
        page.goto(f'{BASE}/{CATEGORIES["行政警察學系"]}', wait_until='networkidle')

        err_before = len(console_errors_global)

        # 依年份 -> 依科目 -> 依年份
        page.click('#viewYear')
        page.wait_for_timeout(100)
        page.click('#viewSubject')
        page.wait_for_timeout(100)
        page.click('#viewYear')
        page.wait_for_timeout(100)

        # 搜尋 -> 清除搜尋
        page.fill('#searchInput', '警察')
        page.wait_for_timeout(300)
        page.fill('#searchInput', '')
        page.wait_for_timeout(300)

        # 書籤篩選 -> 取消書籤篩選
        page.click('#bookmarkFilter')
        page.wait_for_timeout(200)
        page.click('#bookmarkFilter')
        page.wait_for_timeout(200)

        err_after = len(console_errors_global)
        check('快速功能切換無 console error', err_after == err_before,
              f'新增 {err_after - err_before} 個 error')
        page.close()

        # =================================================================
        # 測試 4: 空搜尋處理
        # =================================================================
        print('\n=== 測試 4: 空搜尋處理 ===')
        page = make_page()
        page.goto(f'{BASE}/{CATEGORIES["行政警察學系"]}', wait_until='networkidle')

        err_before = len(console_errors_global)

        # 空字串
        page.fill('#searchInput', '')
        page.wait_for_timeout(300)
        visible_after_empty = page.evaluate(
            '() => document.querySelectorAll("#yearView .subject-card:not([style*=\\"display: none\\"])").length'
        )
        check('空字串搜尋不出錯', visible_after_empty > 0, f'{visible_after_empty} 張卡片可見')

        # 純空白
        page.fill('#searchInput', '   ')
        page.wait_for_timeout(300)
        visible_after_spaces = page.evaluate(
            '() => document.querySelectorAll("#yearView .subject-card:not([style*=\\"display: none\\"])").length'
        )
        check('純空白搜尋不出錯', visible_after_spaces > 0, f'{visible_after_spaces} 張卡片可見')

        err_after = len(console_errors_global)
        check('空搜尋無 console error', err_after == err_before)
        page.close()

        # =================================================================
        # 測試 5: 特殊字元搜尋 (XSS 防護)
        # =================================================================
        print('\n=== 測試 5: 特殊字元搜尋 ===')
        page = make_page()
        page.goto(f'{BASE}/{CATEGORIES["行政警察學系"]}', wait_until='networkidle')

        err_before = len(console_errors_global)

        special_chars = ['<script>alert(1)</script>', '&amp;', '"引號"', "' OR 1=1 --"]
        # 記錄搜尋前的 script 標籤數量
        scripts_before = page.evaluate('() => document.querySelectorAll("script").length')
        for sc in special_chars:
            page.fill('#searchInput', sc)
            page.wait_for_timeout(300)
            # 確認頁面還活著（能正常執行 JS）
            page_alive = page.evaluate('() => !!document.body && !!document.title')
            # 確認沒有新增 script（XSS 注入檢測）
            scripts_after = page.evaluate('() => document.querySelectorAll("script").length')
            no_xss = scripts_after == scripts_before
            check(f'特殊字元「{sc[:20]}」不崩潰', page_alive and no_xss,
                  f'alive={page_alive}, scripts={scripts_before}->{scripts_after}')

        err_after = len(console_errors_global)
        check('特殊字元搜尋無 console error', err_after == err_before,
              f'新增 {err_after - err_before} 個 error')
        page.close()

        # =================================================================
        # 測試 6: 超長關鍵字
        # =================================================================
        print('\n=== 測試 6: 超長關鍵字 ===')
        page = make_page()
        page.goto(f'{BASE}/{CATEGORIES["行政警察學系"]}', wait_until='networkidle')

        err_before = len(console_errors_global)
        long_str = 'A' * 200
        page.fill('#searchInput', long_str)
        page.wait_for_timeout(400)
        page_alive = page.evaluate('() => document.body !== null')
        check('200字元搜尋不崩潰', page_alive)
        stats = page.text_content('#searchStatsText')
        check('超長關鍵字有統計回應', '找到' in stats or stats.strip() == '', stats.strip()[:60])

        err_after = len(console_errors_global)
        check('超長關鍵字無 console error', err_after == err_before)
        page.close()

        # =================================================================
        # 測試 7: 跨類科書籤
        # =================================================================
        print('\n=== 測試 7: 跨類科書籤 ===')
        page = make_page()

        bookmark_ids = {}
        for cat_name, cat_path in list(CATEGORIES.items())[:3]:
            page.goto(f'{BASE}/{cat_path}', wait_until='networkidle')
            # 找到第一張未被書籤的卡片的書籤按鈕
            card_id = page.evaluate('''() => {
                const btns = document.querySelectorAll('.bookmark-btn:not(.active)');
                if (btns.length === 0) return null;
                btns[0].click();
                const card = btns[0].closest('.subject-card');
                return card ? card.id : null;
            }''')
            page.wait_for_timeout(300)
            if card_id:
                # 再次確認是否真的加上了 active
                is_active = page.evaluate(f'''() => {{
                    const card = document.getElementById("{card_id}");
                    if (!card) return false;
                    const btn = card.querySelector('.bookmark-btn');
                    return btn ? btn.classList.contains('active') : false;
                }}''')
                bookmark_ids[cat_name] = card_id
                check(f'{cat_name} 書籤設定成功', is_active, f'卡片 {card_id}')
            else:
                check(f'{cat_name} 書籤設定成功', False, '找不到未書籤的卡片')

        # 回到每個頁面，確認書籤保持（localStorage 跨刷新保留）
        for cat_name, cat_path in list(CATEGORIES.items())[:3]:
            card_id = bookmark_ids.get(cat_name)
            if not card_id:
                continue
            page.goto(f'{BASE}/{cat_path}', wait_until='networkidle')
            is_active = page.evaluate(f'''() => {{
                const card = document.getElementById("{card_id}");
                if (!card) return false;
                const btn = card.querySelector('.bookmark-btn');
                return btn ? btn.classList.contains('active') : false;
            }}''')
            check(f'{cat_name} 書籤保持', is_active, f'卡片 {card_id}')
        page.close()

        # =================================================================
        # 測試 8: 練習模式壓力
        # =================================================================
        print('\n=== 測試 8: 練習模式壓力 ===')
        page = make_page()
        page.goto(f'{BASE}/{CATEGORIES["行政警察學系"]}', wait_until='networkidle')

        err_before = len(console_errors_global)

        # 進入練習模式
        page.click('#practiceToggle')
        page.wait_for_timeout(300)
        is_practice = page.evaluate('() => document.body.classList.contains("practice-mode")')
        check('練習模式啟用', is_practice)

        # 快速展開多張卡片
        headers = page.query_selector_all('#yearView .subject-header')
        expand_count = min(5, len(headers))
        for i in range(expand_count):
            headers[i].click()
            page.wait_for_timeout(50)
        check(f'快速展開 {expand_count} 張卡片', True)

        # 快速點擊多個「顯示答案」按鈕
        reveal_btns = page.query_selector_all('.reveal-btn')
        click_count = min(5, len(reveal_btns))
        for i in range(click_count):
            if reveal_btns[i].is_visible():
                reveal_btns[i].click()
                page.wait_for_timeout(50)
        check(f'快速點擊 {click_count} 個顯示答案', True)

        err_after = len(console_errors_global)
        check('練習模式壓力無 console error', err_after == err_before,
              f'新增 {err_after - err_before} 個 error')
        page.close()

        # =================================================================
        # 測試 9: 大量展開
        # =================================================================
        print('\n=== 測試 9: 大量展開 ===')
        page = make_page()
        page.goto(f'{BASE}/{CATEGORIES["行政警察學系"]}', wait_until='networkidle')

        err_before = len(console_errors_global)

        # 展開所有卡片（至少 10+）
        t_start = time.time()
        expanded = page.evaluate('''() => {
            const headers = document.querySelectorAll('#yearView .subject-header');
            let count = 0;
            headers.forEach(h => {
                h.click();
                count++;
            });
            return count;
        }''')
        page.wait_for_timeout(500)
        t_elapsed = time.time() - t_start
        page_alive = page.evaluate('() => document.body !== null')
        check(f'展開 {expanded} 張卡片頁面不崩潰', page_alive and expanded >= 10,
              f'{expanded} 張, 耗時 {t_elapsed:.2f}s')
        check('大量展開耗時合理', t_elapsed < 10, f'{t_elapsed:.2f}s')

        err_after = len(console_errors_global)
        check('大量展開無 console error', err_after == err_before)
        page.close()

        # =================================================================
        # 測試 10: URL hash 直接訪問
        # =================================================================
        print('\n=== 測試 10: URL hash 直接訪問 ===')
        page = make_page()
        base_url = f'{BASE}/{CATEGORIES["行政警察學系"]}'

        err_before = len(console_errors_global)

        # 正確的 hash — 年份
        page.goto(f'{base_url}#year-114', wait_until='networkidle')
        page.wait_for_timeout(300)
        page_alive = page.evaluate('() => document.body !== null')
        check('正確年份 hash 存取', page_alive)

        # 正確的 hash — 卡片 ID
        first_card_id = page.evaluate('''() => {
            const card = document.querySelector('#yearView .subject-card');
            return card ? card.id : null;
        }''')
        if first_card_id:
            page.goto(f'{base_url}#{first_card_id}', wait_until='networkidle')
            page.wait_for_timeout(300)
            is_open = page.evaluate(f'() => document.getElementById("{first_card_id}").classList.contains("open")')
            check('正確卡片 hash 展開', is_open, first_card_id)

        # 錯誤的 hash
        page.goto(f'{base_url}#nonexistent-id-12345', wait_until='networkidle')
        page.wait_for_timeout(300)
        page_alive = page.evaluate('() => document.body !== null')
        check('錯誤 hash 不崩潰', page_alive)

        # 空 hash
        page.goto(f'{base_url}#', wait_until='networkidle')
        page.wait_for_timeout(300)
        page_alive = page.evaluate('() => document.body !== null')
        check('空 hash 不崩潰', page_alive)

        err_after = len(console_errors_global)
        check('URL hash 無 console error', err_after == err_before,
              f'新增 {err_after - err_before} 個 error')
        page.close()

        # =================================================================
        # 測試 11: 刷新保持深色模式
        # =================================================================
        print('\n=== 測試 11: 刷新保持深色模式 ===')
        page = make_page()
        page.goto(f'{BASE}/{CATEGORIES["行政警察學系"]}', wait_until='networkidle')

        # 先確保是淺色模式
        is_dark = page.evaluate('() => document.documentElement.classList.contains("dark")')
        if is_dark:
            page.click('#darkToggle')
            page.wait_for_timeout(200)

        # 切換到深色模式
        page.click('#darkToggle')
        page.wait_for_timeout(200)
        is_dark_after = page.evaluate('() => document.documentElement.classList.contains("dark")')
        check('深色模式啟用', is_dark_after)

        # 刷新頁面
        page.reload(wait_until='networkidle')
        page.wait_for_timeout(300)
        is_dark_reload = page.evaluate('() => document.documentElement.classList.contains("dark")')
        check('刷新後深色模式保持', is_dark_reload)

        # 切回淺色以免影響後續測試
        page.click('#darkToggle')
        page.wait_for_timeout(200)
        page.close()

        # =================================================================
        # 測試 12: 列印樣式
        # =================================================================
        print('\n=== 測試 12: 列印樣式 ===')
        page = make_page()
        page.goto(f'{BASE}/{CATEGORIES["行政警察學系"]}', wait_until='networkidle')

        # 檢查是否有 @media print 規則
        has_print = page.evaluate('''() => {
            for (const sheet of document.styleSheets) {
                try {
                    for (const rule of sheet.cssRules) {
                        if (rule.type === CSSRule.MEDIA_RULE && rule.conditionText === 'print') {
                            return true;
                        }
                    }
                } catch(e) {}
            }
            return false;
        }''')
        check('列印媒體查詢存在', has_print)

        # 用 emulateMedia 模擬列印，檢查 sidebar 隱藏
        page.emulate_media(media='print')
        page.wait_for_timeout(200)
        sidebar_hidden = page.evaluate('''() => {
            const sidebar = document.querySelector('.sidebar');
            if (!sidebar) return true;
            const style = window.getComputedStyle(sidebar);
            return style.display === 'none';
        }''')
        check('列印時 sidebar 隱藏', sidebar_hidden)

        toolbar_hidden = page.evaluate('''() => {
            const tb = document.querySelector('.toolbar');
            if (!tb) return true;
            return window.getComputedStyle(tb).display === 'none';
        }''')
        check('列印時 toolbar 隱藏', toolbar_hidden)
        page.emulate_media(media='screen')
        page.close()

        # =================================================================
        # 測試 13: a11y 基本檢查
        # =================================================================
        print('\n=== 測試 13: a11y 基本檢查 ===')
        page = make_page()
        page.goto(f'{BASE}/{CATEGORIES["行政警察學系"]}', wait_until='networkidle')

        # 深色模式切換有 aria-label
        dark_label = page.evaluate('() => document.getElementById("darkToggle").getAttribute("aria-label")')
        check('深色模式按鈕有 aria-label', dark_label is not None and len(dark_label) > 0, dark_label)

        # 搜尋框有 aria-label
        search_label = page.evaluate('() => document.getElementById("searchInput").getAttribute("aria-label")')
        check('搜尋框有 aria-label', search_label is not None and len(search_label) > 0, search_label)

        # subject-header 有 role=button 和 aria-expanded
        header_a11y = page.evaluate('''() => {
            const headers = document.querySelectorAll('.subject-header');
            let ok = 0, total = 0;
            headers.forEach(h => {
                total++;
                if (h.getAttribute('role') === 'button' && h.hasAttribute('aria-expanded')) ok++;
            });
            return { ok, total };
        }''')
        check('卡片標題有 role=button + aria-expanded',
              header_a11y['ok'] == header_a11y['total'] and header_a11y['total'] > 0,
              f'{header_a11y["ok"]}/{header_a11y["total"]}')

        # 書籤篩選有 aria-pressed
        bm_pressed = page.evaluate('() => document.getElementById("bookmarkFilter").hasAttribute("aria-pressed")')
        check('書籤篩選有 aria-pressed', bm_pressed)

        # 回到頂部按鈕有 aria-label
        btt_label = page.evaluate('() => document.getElementById("backToTop").getAttribute("aria-label")')
        check('回到頂部有 aria-label', btt_label is not None and len(btt_label) > 0, btt_label)

        # 搜尋區域有 role=search
        search_role = page.evaluate('() => document.querySelector(".search-box").getAttribute("role")')
        check('搜尋區域有 role=search', search_role == 'search')

        page.close()

        # =================================================================
        # 測試 14: index 頁面所有 15 個類科連結
        # =================================================================
        print('\n=== 測試 14: index 頁面 15 類科連結 ===')
        page = make_page()
        page.goto(f'{BASE}/index.html', wait_until='networkidle')

        links = page.evaluate('''() => {
            const anchors = document.querySelectorAll('.category-card');
            return Array.from(anchors).map(a => ({
                href: a.getAttribute('href'),
                name: a.querySelector('.card-title').textContent.trim()
            }));
        }''')
        check('index 有 15 個類科連結', len(links) == 15, f'實際 {len(links)} 個')

        # 驗證每個連結都能導航
        nav_ok = 0
        nav_fail = []
        for link in links:
            href = link['href']
            name = link['name']
            try:
                resp = page.goto(f'{BASE}/{href}', wait_until='networkidle', timeout=10000)
                if resp and resp.status == 200:
                    has_cards = page.evaluate('() => document.querySelectorAll(".subject-card").length > 0')
                    if has_cards:
                        nav_ok += 1
                    else:
                        nav_fail.append(f'{name}(無卡片)')
                else:
                    nav_fail.append(f'{name}(HTTP {resp.status if resp else "null"})')
            except Exception as e:
                nav_fail.append(f'{name}({str(e)[:30]})')

        check(f'所有連結可導航', nav_ok == len(links),
              f'{nav_ok}/{len(links)} 成功' + (f', 失敗: {nav_fail}' if nav_fail else ''))
        page.close()

        # =================================================================
        # 測試 15: 零 Console 錯誤總結
        # =================================================================
        print('\n=== 測試 15: 全程 Console 錯誤統計 ===')
        check('全程零 console.error', len(console_errors_global) == 0,
              f'{len(console_errors_global)} 個 error')
        if console_errors_global:
            for i, err in enumerate(console_errors_global[:10]):
                print(f'    error[{i}]: {err[:120]}')

        browser.close()

finally:
    server.terminate()
    server.wait()

# ===== 總結報告 =====
print('\n' + '=' * 60)
print('  進階用戶模擬測試總結')
print('=' * 60)
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
total = len(results)
print(f'  通過: {passed}/{total}')
print(f'  失敗: {failed}/{total}')

if failed:
    print('\n  失敗項目:')
    for name, ok, detail in results:
        if not ok:
            print(f'    \u2717 {name}' + (f'  ({detail})' if detail else ''))

pct = passed / total * 100 if total else 0
print(f'\n  通過率: {pct:.1f}%')
print('=' * 60)

sys.exit(0 if failed == 0 else 1)
