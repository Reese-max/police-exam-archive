"""Round 2 UX Audit - Playwright Tests
Verifies Round 1 fixes and tests additional UX scenarios.
"""
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

SITE_ROOT = Path(r"C:\Users\User\Desktop\考古題下載\考古題網站")
INDEX_URL = (SITE_ROOT / "index.html").as_uri()
CATEGORY_URL = (SITE_ROOT / "行政警察學系" / "行政警察學系考古題總覽.html").as_uri()
REPORT_DIR = Path(r"C:\Users\User\Desktop\考古題下載\reports")
SCREENSHOT_DIR = REPORT_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

results = []

def record(section, test_name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append({"section": section, "name": test_name, "status": status, "detail": detail})
    print(f"  [{status}] {test_name}" + (f" -- {detail}" if detail else ""))


def run_all():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # =====================================================
        # SECTION A: Round 1 Fix Verification
        # =====================================================
        print("\n=== A. Round 1 Fix Verification ===")

        # A1: --text-light contrast
        print("\n--- A1: CSS Variable Values ---")
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        text_light = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--text-light').trim()")
        record("A-R1-Fix", "--text-light value is #4a5a6e (improved contrast)", text_light == "#4a5a6e", f"got: {text_light}")

        accent = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()")
        record("A-R1-Fix", "--accent value is #3182ce", accent == "#3182ce", f"got: {accent}")

        # A2: sidebar-link min-height 44px
        sidebar_link_height = page.evaluate("""() => {
            const link = document.querySelector('.sidebar-link');
            if (!link) return -1;
            return parseFloat(getComputedStyle(link).minHeight);
        }""")
        record("A-R1-Fix", ".sidebar-link min-height >= 44px", sidebar_link_height >= 44, f"got: {sidebar_link_height}px")

        # A3: body overflow-x: hidden
        overflow_x = page.evaluate("getComputedStyle(document.body).overflowX")
        record("A-R1-Fix", "body overflow-x: hidden", overflow_x == "hidden", f"got: {overflow_x}")

        # A4: Bookmark buttons have aria-label and aria-pressed
        # Need to expand a card first to trigger bookmark init
        bm_aria = page.evaluate("""() => {
            const btns = document.querySelectorAll('.bookmark-btn');
            if (btns.length === 0) return {count: 0, hasLabel: false, hasPressed: false};
            let allLabel = true, allPressed = true;
            btns.forEach(b => {
                if (!b.getAttribute('aria-label')) allLabel = false;
                if (b.getAttribute('aria-pressed') === null) allPressed = false;
            });
            return {count: btns.length, hasLabel: allLabel, hasPressed: allPressed};
        }""")
        record("A-R1-Fix", "Bookmark buttons have aria-label", bm_aria["count"] > 0 and bm_aria["hasLabel"],
               f"count={bm_aria['count']}, allHaveLabel={bm_aria['hasLabel']}")
        record("A-R1-Fix", "Bookmark buttons have aria-pressed", bm_aria["count"] > 0 and bm_aria["hasPressed"],
               f"count={bm_aria['count']}, allHavePressed={bm_aria['hasPressed']}")

        # A5: Search jump buttons have aria-label
        page.fill("#searchInput", "憲法")
        page.wait_for_timeout(300)
        jump_aria = page.evaluate("""() => {
            const btns = document.querySelectorAll('.search-jump button');
            if (btns.length === 0) return {count: 0, allLabel: false};
            let ok = true;
            btns.forEach(b => { if (!b.getAttribute('aria-label')) ok = false; });
            return {count: btns.length, allLabel: ok};
        }""")
        record("A-R1-Fix", "Search jump buttons have aria-label", jump_aria["count"] > 0 and jump_aria["allLabel"],
               f"count={jump_aria['count']}, allLabel={jump_aria['allLabel']}")

        # A6: Index page skip-link
        page.close()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(INDEX_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(300)

        skip_link = page.evaluate("""() => {
            const sl = document.querySelector('.skip-link');
            if (!sl) return null;
            return {href: sl.getAttribute('href'), text: sl.textContent.trim()};
        }""")
        record("A-R1-Fix", "Index page has skip-link", skip_link is not None,
               f"found: {skip_link}" if skip_link else "not found")

        # A7: Google Fonts non-blocking on INDEX page
        fonts_nonblocking_idx = page.evaluate("""() => {
            const links = document.querySelectorAll('link[rel="stylesheet"][href*="fonts.googleapis.com"]');
            if (links.length === 0) return {ok: true, detail: 'no font links'};
            const details = [];
            let ok = true;
            let hasNonBlockingLink = false;
            for (const link of links) {
                // Skip noscript fallback links
                if (link.closest('noscript')) continue;
                const media = link.getAttribute('media');
                const onload = link.getAttribute('onload');
                details.push('media=' + media + ',onload=' + (onload ? 'yes' : 'no'));
                // OK if media=print (with onload swap) or already swapped to 'all' (after onload fired)
                if (media === 'print' || media === 'all') hasNonBlockingLink = true;
                else ok = false;
            }
            if (!hasNonBlockingLink && details.length === 0) ok = true; // only noscript links
            return {ok: ok && (hasNonBlockingLink || details.length === 0), detail: details.join('; ') || 'only noscript links'};
        }""")
        record("A-R1-Fix", "Google Fonts non-blocking on index page",
               fonts_nonblocking_idx["ok"],
               fonts_nonblocking_idx["detail"])

        # Also check category page
        page.close()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(300)
        fonts_nonblocking_cat = page.evaluate("""() => {
            const links = document.querySelectorAll('link[rel="stylesheet"][href*="fonts.googleapis.com"]');
            if (links.length === 0) return {ok: true, detail: 'no font links'};
            const details = [];
            let ok = true;
            for (const link of links) {
                const media = link.getAttribute('media');
                const onload = link.getAttribute('onload');
                details.push('media=' + media + ',onload=' + (onload ? 'yes' : 'no'));
                if (media !== 'print' && media !== 'all') ok = false;
            }
            return {ok: ok, detail: details.join('; ')};
        }""")
        record("A-R1-Fix", "Google Fonts non-blocking on category page",
               fonts_nonblocking_cat["ok"],
               fonts_nonblocking_cat["detail"])
        record("A-R1-Fix", "Google Fonts non-blocking (media=print+onload)", fonts_nonblocking_cat["ok"],
               fonts_nonblocking_cat["detail"])

        # A8: Sidebar links have title attribute
        page.close()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(300)

        sidebar_titles = page.evaluate("""() => {
            const links = document.querySelectorAll('.sidebar-link');
            let withTitle = 0;
            links.forEach(l => { if (l.getAttribute('title')) withTitle++; });
            return {total: links.length, withTitle: withTitle};
        }""")
        record("A-R1-Fix", "Sidebar links have title attribute",
               sidebar_titles["total"] > 0 and sidebar_titles["total"] == sidebar_titles["withTitle"],
               f"{sidebar_titles['withTitle']}/{sidebar_titles['total']} have title")

        # A9: highlightText full match (search for a word that occurs multiple times)
        page.fill("#searchInput", "警察")
        page.wait_for_timeout(400)
        highlight_info = page.evaluate("""() => {
            const highlights = document.querySelectorAll('.highlight');
            return {count: highlights.length};
        }""")
        record("A-R1-Fix", "highlightText finds multiple matches for '警察'",
               highlight_info["count"] > 10,
               f"found {highlight_info['count']} highlights")

        # A10: Search index pre-built
        cache_built = page.evaluate("() => window._cardTextCache instanceof Map && window._cardTextCache.size > 0")
        record("A-R1-Fix", "Search text cache pre-built", cache_built,
               f"cache exists and populated" if cache_built else "cache not found")

        page.close()

        # =====================================================
        # SECTION B: Keyboard Navigation (Full Flow)
        # =====================================================
        print("\n=== B. Keyboard Navigation ===")
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        # B1: First Tab lands on skip-link
        page.keyboard.press("Tab")
        first_focus = page.evaluate("document.activeElement.className")
        first_focus_tag = page.evaluate("document.activeElement.tagName")
        record("B-Keyboard", "First Tab focuses skip-link",
               "skip-link" in first_focus,
               f"focused: {first_focus_tag}.{first_focus}")

        # B2: Tab through to search input
        # Keep tabbing until we reach search input (max 20 tabs)
        found_search = False
        for i in range(25):
            page.keyboard.press("Tab")
            active_id = page.evaluate("document.activeElement.id")
            if active_id == "searchInput":
                found_search = True
                break
        record("B-Keyboard", "Tab reaches searchInput", found_search, f"found after {i+1} tabs")

        # B3: Ctrl+K focuses search
        page.keyboard.press("Escape")  # blur first
        page.wait_for_timeout(100)
        page.keyboard.press("Control+k")
        ctrl_k_focus = page.evaluate("document.activeElement.id")
        record("B-Keyboard", "Ctrl+K focuses searchInput", ctrl_k_focus == "searchInput")

        # B4: / focuses search
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
        page.keyboard.press("/")
        slash_focus = page.evaluate("document.activeElement.id")
        record("B-Keyboard", "/ focuses searchInput", slash_focus == "searchInput")

        # B5: Escape clears search and blurs
        page.fill("#searchInput", "test query")
        page.wait_for_timeout(200)
        page.keyboard.press("Escape")
        search_val = page.evaluate("document.getElementById('searchInput').value")
        is_blurred = page.evaluate("document.activeElement.id !== 'searchInput'")
        record("B-Keyboard", "Escape clears search + blurs", search_val == "" and is_blurred,
               f"value='{search_val}', blurred={is_blurred}")

        # B6: Enter/Space on subject-header
        page.evaluate("document.querySelector('.subject-header').focus()")
        page.keyboard.press("Enter")
        is_open = page.evaluate("document.querySelector('.subject-card').classList.contains('open')")
        record("B-Keyboard", "Enter expands subject card", is_open)

        page.keyboard.press("Space")
        is_closed = page.evaluate("!document.querySelector('.subject-card').classList.contains('open')")
        record("B-Keyboard", "Space collapses subject card", is_closed)

        # B7: Enter on sidebar-year
        page.evaluate("document.querySelector('.sidebar-year').focus()")
        page.keyboard.press("Enter")
        sidebar_year_expanded = page.evaluate("document.querySelector('.sidebar-year').classList.contains('active')")
        record("B-Keyboard", "Enter expands sidebar year", sidebar_year_expanded)

        # B8: Escape closes export panel
        page.evaluate("document.getElementById('exportPanel').style.display = ''")
        page.keyboard.press("Escape")
        export_hidden = page.evaluate("document.getElementById('exportPanel').style.display === 'none'")
        record("B-Keyboard", "Escape closes export panel", export_hidden)

        # B9: Tab to bookmark button
        page.evaluate("document.querySelector('.subject-header').focus()")
        page.keyboard.press("Enter")  # expand card first
        page.wait_for_timeout(100)
        # Tab from header should reach bookmark button
        page.keyboard.press("Tab")
        bm_focused = page.evaluate("document.activeElement.classList.contains('bookmark-btn')")
        record("B-Keyboard", "Tab reaches bookmark button", bm_focused,
               f"focused element class: {page.evaluate('document.activeElement.className')}")

        # B10: Tab to practice toggle
        # Reset focus and find practice toggle
        page.evaluate("document.getElementById('practiceToggle').focus()")
        practice_focused = page.evaluate("document.activeElement.id === 'practiceToggle'")
        record("B-Keyboard", "Practice toggle is focusable", practice_focused)

        page.screenshot(path=str(SCREENSHOT_DIR / "r2_keyboard_nav.png"), full_page=False)
        page.close()

        # =====================================================
        # SECTION C: Mobile Deep Test
        # =====================================================
        print("\n=== C. Mobile Deep Test ===")

        # C1: 375px no horizontal overflow
        page = browser.new_page(viewport={"width": 375, "height": 667})
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        scroll_w_375 = page.evaluate("document.documentElement.scrollWidth")
        record("C-Mobile", "375px: no horizontal overflow",
               scroll_w_375 <= 375,
               f"scrollWidth={scroll_w_375}, viewport=375")

        # C2: 320px (Galaxy Fold) no horizontal overflow
        page.close()
        page = browser.new_page(viewport={"width": 320, "height": 658})
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        scroll_w_320 = page.evaluate("document.documentElement.scrollWidth")
        record("C-Mobile", "320px: no horizontal overflow",
               scroll_w_320 <= 320,
               f"scrollWidth={scroll_w_320}, viewport=320")

        page.screenshot(path=str(SCREENSHOT_DIR / "r2_galaxy_fold_320.png"), full_page=False)

        # C3: Sidebar overlay click closes sidebar
        page.close()
        page = browser.new_page(viewport={"width": 375, "height": 667})
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        # Open sidebar
        page.click("#hamburgerBtn")
        page.wait_for_timeout(300)
        sidebar_open = page.evaluate("document.getElementById('sidebar').classList.contains('open')")
        record("C-Mobile", "Hamburger opens sidebar", sidebar_open)

        # Click overlay to close
        page.evaluate("document.getElementById('sidebarOverlay').click()")
        page.wait_for_timeout(300)
        sidebar_closed = page.evaluate("!document.getElementById('sidebar').classList.contains('open')")
        record("C-Mobile", "Overlay click closes sidebar", sidebar_closed)

        # C4: Sidebar link click closes sidebar (Round 1 Issue #1)
        page.click("#hamburgerBtn")
        page.wait_for_timeout(300)
        # Expand a year using JS evaluate (avoid Playwright viewport check on sidebar)
        page.evaluate("document.querySelector('.sidebar-year').click()")
        page.wait_for_timeout(200)
        # Click a sidebar link using JS
        sidebar_link_clicked = page.evaluate("""() => {
            const links = document.querySelectorAll('.sidebar-link');
            if (links.length === 0) return false;
            links[0].click();
            return true;
        }""")
        page.wait_for_timeout(300)
        if sidebar_link_clicked:
            sidebar_closed_after_link = page.evaluate("!document.getElementById('sidebar').classList.contains('open')")
            record("C-Mobile", "Sidebar link click closes sidebar (R1 #1 fix)",
                   sidebar_closed_after_link,
                   f"sidebar open={not sidebar_closed_after_link}")
        else:
            record("C-Mobile", "Sidebar link click closes sidebar (R1 #1 fix)", False, "no sidebar links found")

        # C5: Escape closes mobile sidebar
        page.click("#hamburgerBtn")
        page.wait_for_timeout(300)
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        sidebar_closed_esc = page.evaluate("!document.getElementById('sidebar').classList.contains('open')")
        record("C-Mobile", "Escape closes mobile sidebar", sidebar_closed_esc)

        # C6: Touch targets >= 44px
        touch_targets = page.evaluate("""() => {
            const selectors = ['.sidebar-link', '.sidebar-year', '.sidebar-home', '.filter-chip',
                               '.toolbar-btn', '.search-jump button', '.bookmark-btn',
                               '.hamburger', '.back-to-top', '.dark-toggle'];
            const issues = [];
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                els.forEach((el, i) => {
                    const rect = el.getBoundingClientRect();
                    const cs = getComputedStyle(el);
                    const mh = parseFloat(cs.minHeight) || rect.height;
                    const mw = parseFloat(cs.minWidth) || rect.width;
                    if (mh < 44 || mw < 44) {
                        // Only report visible elements
                        if (rect.width > 0 && rect.height > 0) {
                            issues.push(`${sel}[${i}]: ${Math.round(rect.width)}x${Math.round(rect.height)} (min: ${mw}x${mh})`);
                        }
                    }
                });
            }
            return issues;
        }""")
        record("C-Mobile", "All visible touch targets >= 44px",
               len(touch_targets) == 0,
               f"issues: {touch_targets}" if touch_targets else "all pass")

        # C7: select#subjectFilter no overflow (Round 1 Issue #2)
        select_overflow = page.evaluate("""() => {
            const sel = document.getElementById('subjectFilter');
            if (!sel) return {width: 0, right: 0, maxWidth: 'n/a', display: 'n/a'};
            const rect = sel.getBoundingClientRect();
            const cs = getComputedStyle(sel);
            return {
                width: Math.round(rect.width),
                right: Math.round(rect.right),
                maxWidth: cs.maxWidth,
                display: cs.display
            };
        }""")
        # The select overflows its container but body overflow-x:hidden clips it visually.
        # Still, the element width is 792px which is a layout issue.
        record("C-Mobile", "select#subjectFilter width <= viewport (R1 #2 fix)",
               select_overflow["width"] <= 375,
               f"width={select_overflow['width']}, right={select_overflow['right']}, maxWidth={select_overflow['maxWidth']}")

        # C8: filter-chip no page overflow (Round 1 Issue #3)
        page_scroll_w = page.evaluate("document.documentElement.scrollWidth")
        record("C-Mobile", "filter-chip no page overflow (R1 #3 fix)",
               page_scroll_w <= 375,
               f"scrollWidth={page_scroll_w}")

        page.screenshot(path=str(SCREENSHOT_DIR / "r2_mobile_375.png"), full_page=False)
        page.close()

        # =====================================================
        # SECTION D: Visual Consistency (Dark Mode)
        # =====================================================
        print("\n=== D. Visual Consistency (Dark Mode) ===")
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(300)

        # Enable dark mode
        page.click("#darkToggle")
        page.wait_for_timeout(300)

        is_dark = page.evaluate("document.documentElement.classList.contains('dark')")
        record("D-DarkMode", "Dark mode activates", is_dark)

        # D1: Dark mode CSS variables
        dark_vars = page.evaluate("""() => {
            const cs = getComputedStyle(document.documentElement);
            return {
                bg: cs.getPropertyValue('--bg').trim(),
                cardBg: cs.getPropertyValue('--card-bg').trim(),
                text: cs.getPropertyValue('--text').trim(),
                textLight: cs.getPropertyValue('--text-light').trim(),
                accent: cs.getPropertyValue('--accent').trim()
            };
        }""")
        record("D-DarkMode", "Dark mode --bg is dark (#1a202c)", dark_vars["bg"] == "#1a202c", f"got: {dark_vars['bg']}")
        record("D-DarkMode", "Dark mode --text is light (#e2e8f0)", dark_vars["text"] == "#e2e8f0", f"got: {dark_vars['text']}")

        # D2: Dark mode search highlight readability
        page.fill("#searchInput", "憲法")
        page.wait_for_timeout(400)
        highlight_style = page.evaluate("""() => {
            const h = document.querySelector('.highlight');
            if (!h) return null;
            const cs = getComputedStyle(h);
            return {bg: cs.backgroundColor, color: cs.color};
        }""")
        record("D-DarkMode", "Search highlight in dark mode has visible style",
               highlight_style is not None,
               f"bg={highlight_style['bg']}, color={highlight_style['color']}" if highlight_style else "no highlights")

        # D3: Practice mode panel in dark mode
        page.evaluate("document.getElementById('searchInput').value = ''")
        page.evaluate("doSearch('')")
        page.click("#practiceToggle")
        page.wait_for_timeout(300)
        practice_visible = page.evaluate("document.getElementById('practiceScore').classList.contains('visible')")
        practice_bg = page.evaluate("""() => {
            const p = document.getElementById('practiceScore');
            return getComputedStyle(p).backgroundImage || getComputedStyle(p).backgroundColor;
        }""")
        record("D-DarkMode", "Practice score panel visible in dark mode",
               practice_visible, f"bg: {practice_bg}")

        # D4: Free point and passage fragment styling in dark mode
        free_point_style = page.evaluate("""() => {
            const fp = document.querySelector('.answer-cell.free-point');
            if (!fp) return 'no free-point cells found';
            const cs = getComputedStyle(fp);
            return `bg=${cs.backgroundImage}, border=${cs.borderColor}`;
        }""")
        record("D-DarkMode", "Free point cells styled in dark mode",
               "no free-point" not in str(free_point_style),
               str(free_point_style))

        passage_style = page.evaluate("""() => {
            const pf = document.querySelector('.mc-question[data-subtype="passage_fragment"]');
            if (!pf) return 'no passage_fragment found';
            const cs = getComputedStyle(pf);
            return `bg=${cs.backgroundColor}, borderLeft=${cs.borderLeftColor}`;
        }""")
        record("D-DarkMode", "Passage fragment styled in dark mode (if exists)",
               True,  # informational
               str(passage_style))

        page.screenshot(path=str(SCREENSHOT_DIR / "r2_dark_mode.png"), full_page=False)

        # D5: Turn dark mode off and verify
        page.click("#darkToggle")
        page.wait_for_timeout(300)
        is_light = page.evaluate("!document.documentElement.classList.contains('dark')")
        record("D-DarkMode", "Dark mode deactivates correctly", is_light)

        page.close()

        # =====================================================
        # SECTION E: New Feature Verification
        # =====================================================
        print("\n=== E. New Feature Verification ===")
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        # E1: highlightText full match -- search a common word
        page.fill("#searchInput", "警察")
        page.wait_for_timeout(400)

        hl_stats = page.evaluate("""() => {
            const statsText = document.getElementById('searchStatsText').textContent;
            const highlights = document.querySelectorAll('.highlight');
            // Check that highlights exist in multiple cards
            const cards = document.querySelectorAll('.subject-card.open');
            return {
                statsText: statsText,
                highlightCount: highlights.length,
                openCards: cards.length
            };
        }""")
        record("E-Features", "highlightText: '警察' finds many matches",
               hl_stats["highlightCount"] > 50,
               f"highlights={hl_stats['highlightCount']}, cards={hl_stats['openCards']}, stats='{hl_stats['statsText']}'")

        # E2: Search jump navigation
        jump_exists = page.evaluate("document.querySelectorAll('.search-jump button').length")
        record("E-Features", "Search jump buttons appear for multi-match", jump_exists >= 2,
               f"found {jump_exists} jump buttons")

        if jump_exists >= 2:
            # Click next button
            page.click(".search-jump button:last-child")
            page.wait_for_timeout(200)
            counter_text = page.evaluate("document.getElementById('hitCounter')?.textContent || ''")
            has_current = page.evaluate("document.querySelector('.highlight.current') !== null")
            record("E-Features", "Search jump: next button works",
                   "1/" in counter_text and has_current,
                   f"counter='{counter_text}', hasCurrent={has_current}")

            # Click prev button
            page.click(".search-jump button:first-child")
            page.wait_for_timeout(200)
            counter_text2 = page.evaluate("document.getElementById('hitCounter')?.textContent || ''")
            record("E-Features", "Search jump: prev button works",
                   "/" in counter_text2,
                   f"counter='{counter_text2}'")

        # E3: Search index (pre-built cache)
        cache_info = page.evaluate("""() => {
            if (!(window._cardTextCache instanceof Map)) return {exists: false, size: 0};
            return {exists: true, size: window._cardTextCache.size};
        }""")
        record("E-Features", "Search index pre-built with entries",
               cache_info["exists"] and cache_info["size"] > 0,
               f"cache size={cache_info['size']}")

        # E4: Skip-link (index page)
        page.close()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(INDEX_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(300)

        page.keyboard.press("Tab")
        skip_focused = page.evaluate("""() => {
            const el = document.activeElement;
            return {
                isSkipLink: el.classList.contains('skip-link'),
                tag: el.tagName,
                text: el.textContent.trim(),
                href: el.getAttribute('href')
            };
        }""")
        record("E-Features", "Index page: Tab first focuses skip-link",
               skip_focused["isSkipLink"],
               f"focused: {skip_focused['tag']} '{skip_focused['text']}' href={skip_focused['href']}")

        # E5: Skip-link on category page
        page.close()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(300)

        page.keyboard.press("Tab")
        skip_focused2 = page.evaluate("""() => {
            const el = document.activeElement;
            return {
                isSkipLink: el.classList.contains('skip-link'),
                text: el.textContent.trim()
            };
        }""")
        record("E-Features", "Category page: Tab first focuses skip-link",
               skip_focused2["isSkipLink"],
               f"focused: '{skip_focused2['text']}'")

        page.close()

        # =====================================================
        # SECTION F: Dark Mode Position Consistency
        # =====================================================
        print("\n=== F. Dark Mode Button Position ===")

        # F1: Index page dark toggle position
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(INDEX_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(300)

        idx_toggle_pos = page.evaluate("""() => {
            const btn = document.getElementById('darkToggle');
            const rect = btn.getBoundingClientRect();
            const cs = getComputedStyle(btn);
            return {
                left: Math.round(rect.left),
                right: Math.round(rect.right),
                cssRight: cs.right,
                cssLeft: cs.left,
                bottom: Math.round(window.innerHeight - rect.bottom)
            };
        }""")
        record("F-Position", "Index dark toggle position",
               True,  # informational
               f"left={idx_toggle_pos['left']}, cssLeft={idx_toggle_pos['cssLeft']}, cssRight={idx_toggle_pos['cssRight']}")
        page.close()

        # F2: Category page dark toggle position
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(300)

        cat_toggle_pos = page.evaluate("""() => {
            const btn = document.getElementById('darkToggle');
            const rect = btn.getBoundingClientRect();
            const cs = getComputedStyle(btn);
            return {
                left: Math.round(rect.left),
                right: Math.round(rect.right),
                cssRight: cs.right,
                cssLeft: cs.left,
                bottom: Math.round(window.innerHeight - rect.bottom)
            };
        }""")
        record("F-Position", "Category dark toggle position",
               True,  # informational
               f"left={cat_toggle_pos['left']}, cssLeft={cat_toggle_pos['cssLeft']}, cssRight={cat_toggle_pos['cssRight']}")

        # Check consistency (Round 1 Issue #6)
        # The index has inline css with right:2rem, category has left:2rem in style.css
        # If both are on the same side, it's consistent
        idx_side = "left" if idx_toggle_pos["left"] < 400 else "right"
        cat_side = "left" if cat_toggle_pos["left"] < 400 else "right"
        record("F-Position", "Dark toggle position consistent across pages (R1 #6)",
               idx_side == cat_side,
               f"index={idx_side} (x={idx_toggle_pos['left']}), category={cat_side} (x={cat_toggle_pos['left']})")

        page.close()

        # =====================================================
        # SECTION G: Console Errors Check
        # =====================================================
        print("\n=== G. Console Errors ===")
        errors_found = []

        for label, url in [("Index", INDEX_URL), ("Category", CATEGORY_URL)]:
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page_errors = []
            page.on("pageerror", lambda err: page_errors.append(str(err)))
            console_errors = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(500)

            if page_errors or console_errors:
                errors_found.extend([f"{label}: {e}" for e in page_errors + console_errors])

            record("G-Errors", f"No JS errors on {label} page",
                   len(page_errors) == 0 and len(console_errors) == 0,
                   f"errors: {page_errors + console_errors}" if (page_errors or console_errors) else "clean")
            page.close()

        # =====================================================
        # SECTION H: Focus Visible Styles
        # =====================================================
        print("\n=== H. Focus Visible Styles ===")
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(300)

        # Check :focus-visible by reading the CSS file directly (file:// CORS blocks cssRules access)
        css_path = SITE_ROOT / "css" / "style.css"
        css_content = css_path.read_text(encoding="utf-8")
        has_focus_visible = ":focus-visible" in css_content
        record("H-A11y", ":focus-visible rule exists in CSS (file check)", has_focus_visible,
               f"found in {css_path.name}" if has_focus_visible else "not found")

        # Check ARIA roles
        aria_checks = page.evaluate("""() => {
            const results = [];
            // Search box role=search
            const searchBox = document.querySelector('[role="search"]');
            results.push({name: 'Search box has role=search', pass: !!searchBox});

            // Toolbar role=toolbar
            const toolbar = document.querySelector('[role="toolbar"]');
            results.push({name: 'Toolbar has role=toolbar', pass: !!toolbar});

            // Export panel role=dialog
            const exportPanel = document.getElementById('exportPanel');
            results.push({name: 'Export panel has role=dialog',
                         pass: exportPanel?.getAttribute('role') === 'dialog'});

            // searchStats has aria-live
            const stats = document.getElementById('searchStats');
            results.push({name: 'Search stats has aria-live=polite',
                         pass: stats?.getAttribute('aria-live') === 'polite'});

            // Sidebar nav has aria-label
            const sidebarNav = document.querySelector('nav.sidebar');
            results.push({name: 'Sidebar nav has aria-label',
                         pass: !!sidebarNav?.getAttribute('aria-label')});

            return results;
        }""")

        for check in aria_checks:
            record("H-A11y", check["name"], check["pass"])

        page.close()

        # =====================================================
        # SECTION I: All 15 Category Links Accessible
        # =====================================================
        print("\n=== I. Category Links Check ===")
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(INDEX_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(300)

        cat_links = page.evaluate("""() => {
            const cards = document.querySelectorAll('.category-card');
            return Array.from(cards).map(c => ({
                title: c.querySelector('.card-title')?.textContent.trim() || '',
                href: c.getAttribute('href') || ''
            }));
        }""")
        record("I-Links", f"Index has 15 category cards", len(cat_links) == 15, f"found {len(cat_links)}")
        page.close()

        browser.close()

    # =====================================================
    # Generate Report
    # =====================================================
    print("\n" + "=" * 60)
    print("GENERATING REPORT")
    print("=" * 60)

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    total = len(results)

    # Identify issues (FAIL items)
    issues = [r for r in results if r["status"] == "FAIL"]

    report_lines = []
    report_lines.append("# Round 2 UX 審計報告")
    report_lines.append("")
    report_lines.append(f"**生成時間**: 2026-02-22")
    report_lines.append(f"**測試工具**: Playwright (Python sync API, Chromium headless)")
    report_lines.append(f"**測試頁面**:")
    report_lines.append(f"- 首頁: `index.html`")
    report_lines.append(f"- 類科頁面: `行政警察學系/行政警察學系考古題總覽.html`")
    report_lines.append("")
    report_lines.append("**測試視口**:")
    report_lines.append("- 桌面: 1280x800")
    report_lines.append("- 手機: 375x667")
    report_lines.append("- Galaxy Fold: 320x658")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")

    report_lines.append("## 測試總覽")
    report_lines.append("")
    report_lines.append(f"- **總測試數**: {total}")
    report_lines.append(f"- **通過**: {passed}")
    report_lines.append(f"- **失敗**: {failed}")
    report_lines.append("")

    if failed == 0:
        report_lines.append("**Round 2 UX 審計：所有修復驗證通過，無新問題。**")
        report_lines.append("")
    else:
        report_lines.append(f"**發現 {failed} 個問題（詳見下方）**")
        report_lines.append("")

    # Group results by section
    sections = {}
    for r in results:
        sec = r["section"]
        if sec not in sections:
            sections[sec] = []
        sections[sec].append(r)

    section_labels = {
        "A-R1-Fix": "A. Round 1 修復驗證",
        "B-Keyboard": "B. 鍵盤導航測試",
        "C-Mobile": "C. 手機深度測試",
        "D-DarkMode": "D. 深色模式視覺一致性",
        "E-Features": "E. 新功能驗證",
        "F-Position": "F. 按鈕位置一致性",
        "G-Errors": "G. 控制台錯誤檢查",
        "H-A11y": "H. 無障礙 (ARIA/Focus) 檢查",
        "I-Links": "I. 類科連結檢查",
    }

    for sec_key in ["A-R1-Fix", "B-Keyboard", "C-Mobile", "D-DarkMode", "E-Features",
                     "F-Position", "G-Errors", "H-A11y", "I-Links"]:
        if sec_key not in sections:
            continue
        report_lines.append(f"### {section_labels.get(sec_key, sec_key)}")
        report_lines.append("")
        report_lines.append("| 狀態 | 測試項目 | 細節 |")
        report_lines.append("|------|---------|------|")
        for r in sections[sec_key]:
            status_icon = "PASS" if r["status"] == "PASS" else "**FAIL**"
            detail = r["detail"].replace("|", "/") if r["detail"] else ""
            report_lines.append(f"| {status_icon} | {r['name']} | {detail} |")
        report_lines.append("")

    if issues:
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("## 失敗項目詳細")
        report_lines.append("")
        for i, issue in enumerate(issues, 1):
            report_lines.append(f"### #{i} [{issue['section']}] {issue['name']}")
            report_lines.append(f"- **細節**: {issue['detail']}")
            report_lines.append("")

    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## 測試截圖")
    report_lines.append("")
    report_lines.append("| 檔案 | 說明 |")
    report_lines.append("|------|------|")
    report_lines.append("| `r2_keyboard_nav.png` | 鍵盤導航測試 |")
    report_lines.append("| `r2_galaxy_fold_320.png` | Galaxy Fold 320px |")
    report_lines.append("| `r2_mobile_375.png` | 手機 375px |")
    report_lines.append("| `r2_dark_mode.png` | 深色模式 |")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## 測試環境")
    report_lines.append("- **工具**: Playwright (Python sync API)")
    report_lines.append("- **瀏覽器**: Chromium (headless)")
    report_lines.append("- **測試腳本**: `reports/round2_ux_test.py`")
    report_lines.append("- **平台**: Windows 10 / MSYS2")

    report_text = "\n".join(report_lines)

    report_path = REPORT_DIR / "round2_ux_audit.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(f"\nReport written to: {report_path}")
    print(f"\nSummary: {passed}/{total} passed, {failed} failed")

    return failed


if __name__ == "__main__":
    failed = run_all()
    sys.exit(0 if failed == 0 else 1)
