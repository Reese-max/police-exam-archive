"""
UX Audit Test Script - 5 User Roles
Uses Playwright sync API to test the exam archive website.
"""
import os
import json
import time
import traceback
from datetime import datetime
from playwright.sync_api import sync_playwright

BASE = "file:///C:/Users/User/Desktop/考古題下載/考古題網站"
INDEX_URL = f"{BASE}/index.html"
CATEGORY_URL = f"{BASE}/行政警察/行政警察考古題總覽.html"
SCREENSHOT_DIR = "C:/Users/User/Desktop/考古題下載/reports/screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

issues = []

def add_issue(severity, role, title, description, location="", steps="", suggestion=""):
    issues.append({
        "severity": severity,
        "role": role,
        "title": title,
        "description": description,
        "location": location,
        "steps": steps,
        "suggestion": suggestion
    })

def screenshot(page, name):
    path = f"{SCREENSHOT_DIR}/{name}.png"
    page.screenshot(path=path, full_page=False)
    return path


def test_role1_beginner(browser):
    """Role 1: Beginner student - basic navigation"""
    print("\n=== Role 1: Beginner Student ===")
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()

    console_errors = []
    page_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda err: page_errors.append(str(err)))

    # 1. Open index page, check 15 category cards
    print("  [1.1] Opening index page...")
    page.goto(INDEX_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(500)
    screenshot(page, "r1_01_index")

    cards = page.query_selector_all(".category-card")
    card_count = len(cards)
    print(f"  Found {card_count} category cards")
    if card_count != 15:
        add_issue("Critical", "beginner", f"Category card count mismatch: expected 15, got {card_count}",
                  f"Index page shows {card_count} category cards instead of 15.",
                  "index.html .categories-grid",
                  "1. Open index.html\n2. Count .category-card elements",
                  "Ensure all 15 categories are present")

    # Check all cards are visible
    hidden_cards = 0
    for card in cards:
        if not card.is_visible():
            hidden_cards += 1
    if hidden_cards > 0:
        add_issue("Major", "beginner", f"{hidden_cards} category cards not visible",
                  f"{hidden_cards} cards exist in DOM but are not visible.",
                  "index.html", "", "Check CSS display/visibility")

    # 2. Click first category to enter
    print("  [1.2] Clicking first category card...")
    first_card_title = cards[0].query_selector(".card-title").inner_text() if cards else "N/A"
    print(f"  First card: {first_card_title}")
    cards[0].click()
    page.wait_for_timeout(1000)
    screenshot(page, "r1_02_category_page")

    current_url = page.url
    print(f"  Navigated to: {current_url}")
    if "考古題總覽" not in current_url and "index.html" in current_url:
        add_issue("Critical", "beginner", "Category card click does not navigate",
                  "Clicking a category card did not navigate away from index.",
                  "index.html .category-card[href]",
                  "1. Open index\n2. Click first card",
                  "Verify href attribute works")

    # 3. Check page loaded correctly
    page_title_el = page.query_selector(".page-title")
    if page_title_el:
        print(f"  Page title: {page_title_el.inner_text()}")
    else:
        add_issue("Critical", "beginner", "Missing .page-title on category page",
                  "Category page does not have a .page-title element.",
                  "Category page HTML")

    # 4. Expand year -> expand subject card -> view questions
    print("  [1.3] Expanding subject card...")
    subject_cards = page.query_selector_all("#yearView .subject-card")
    print(f"  Found {len(subject_cards)} subject cards")
    if len(subject_cards) > 0:
        first_header = subject_cards[0].query_selector(".subject-header")
        if first_header:
            first_header.click()
            page.wait_for_timeout(300)
            is_open = subject_cards[0].evaluate("el => el.classList.contains('open')")
            print(f"  Card open after click: {is_open}")
            if not is_open:
                add_issue("Major", "beginner", "Subject card does not expand on click",
                          "Clicking subject header does not add .open class to card.",
                          ".subject-header click handler",
                          "1. Click on subject header\n2. Check if card expands",
                          "Verify toggleCard() function in app.js")
            screenshot(page, "r1_03_expanded_card")

            # Check questions are visible
            questions = subject_cards[0].query_selector_all(".mc-question")
            print(f"  Questions visible: {len(questions)}")

    # 5. Search test
    print("  [1.4] Testing search...")
    search_input = page.query_selector("#searchInput")
    if search_input:
        search_input.fill("憲法")
        page.wait_for_timeout(500)
        screenshot(page, "r1_04_search")
        stats_text = page.query_selector("#searchStatsText")
        if stats_text:
            print(f"  Search stats: {stats_text.inner_text()}")

        # Check highlights
        highlights = page.query_selector_all(".highlight")
        print(f"  Highlights found: {len(highlights)}")
        if len(highlights) == 0:
            add_issue("Major", "beginner", "Search does not highlight matching text",
                      "Typing '憲法' in search does not produce .highlight elements.",
                      "#searchInput + doSearch()",
                      "1. Type '憲法' in search\n2. Check for .highlight spans",
                      "Check highlightText() in app.js")

        # Clear search
        search_input.fill("")
        page.wait_for_timeout(300)
    else:
        add_issue("Critical", "beginner", "Search input not found",
                  "#searchInput element missing from page.",
                  "Category page HTML")

    # Check console errors
    if console_errors:
        add_issue("Major", "beginner", f"Console errors ({len(console_errors)})",
                  f"Console errors found:\n" + "\n".join(console_errors[:5]),
                  "Browser console",
                  "Open DevTools console",
                  "Fix JavaScript errors")
    if page_errors:
        add_issue("Critical", "beginner", f"Page errors ({len(page_errors)})",
                  f"Uncaught errors:\n" + "\n".join(page_errors[:5]),
                  "Browser console",
                  "Open DevTools console",
                  "Fix JavaScript errors")

    print(f"  Console errors: {len(console_errors)}, Page errors: {len(page_errors)}")
    context.close()


def test_role2_reviewer(browser):
    """Role 2: Intensive reviewer - practice mode, bookmarks, filters"""
    print("\n=== Role 2: Intensive Reviewer ===")
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()

    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    page.goto(CATEGORY_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(500)

    # 1. Enable practice mode
    print("  [2.1] Enabling practice mode...")
    practice_btn = page.query_selector("#practiceToggle")
    if practice_btn:
        practice_btn.click()
        page.wait_for_timeout(300)
        is_active = practice_btn.evaluate("el => el.classList.contains('practice-active')")
        print(f"  Practice mode active: {is_active}")
        if not is_active:
            add_issue("Major", "reviewer", "Practice mode button does not activate",
                      "Clicking #practiceToggle does not add .practice-active class.",
                      "#practiceToggle in toolbar")

        # Check score panel visible
        score_panel = page.query_selector("#practiceScore")
        if score_panel:
            is_visible = score_panel.evaluate("el => el.classList.contains('visible')")
            print(f"  Score panel visible: {is_visible}")
            if not is_visible:
                add_issue("Major", "reviewer", "Practice score panel not shown",
                          "Score panel not visible after enabling practice mode.",
                          "#practiceScore")
        screenshot(page, "r2_01_practice_mode")
    else:
        add_issue("Critical", "reviewer", "Practice toggle button missing",
                  "#practiceToggle not found.", "toolbar")

    # 2. Expand a card, click 'show answer', click correct/wrong
    print("  [2.2] Testing self-scoring...")
    first_card = page.query_selector("#yearView .subject-card")
    if first_card:
        header = first_card.query_selector(".subject-header")
        if header:
            header.click()
            page.wait_for_timeout(300)

        reveal_btns = page.query_selector_all(".reveal-btn")
        print(f"  Reveal buttons found: {len(reveal_btns)}")
        if len(reveal_btns) > 0:
            reveal_btns[0].click()
            page.wait_for_timeout(300)
            screenshot(page, "r2_02_revealed_answer")

            # Check if score buttons appeared
            correct_btns = page.query_selector_all(".score-btn.btn-correct.visible")
            wrong_btns = page.query_selector_all(".score-btn.btn-wrong.visible")
            # Could be a free-point exam
            score_panels_scored = page.query_selector_all(".self-score-panel.scored")
            if len(correct_btns) > 0:
                correct_btns[0].click()
                page.wait_for_timeout(200)
                screenshot(page, "r2_03_scored")
                score_text = page.query_selector("#scoreCorrect")
                if score_text:
                    val = score_text.inner_text()
                    print(f"  Score after correct: {val}")
                    if val == "0":
                        add_issue("Major", "reviewer", "Score not updated after marking correct",
                                  "Clicking correct button does not update scoreCorrect.",
                                  "#scoreCorrect")
            elif len(score_panels_scored) > 0:
                print("  Free-point exam detected, auto-scored.")
            else:
                add_issue("Minor", "reviewer", "Score buttons not visible after reveal",
                          "After clicking reveal, btn-correct/btn-wrong not visible.",
                          ".self-score-panel")
        else:
            add_issue("Major", "reviewer", "No reveal buttons in practice mode",
                      "No .reveal-btn found after enabling practice mode.",
                      ".self-score-panel")

    # 3. Bookmark multiple cards
    print("  [2.3] Testing bookmarks...")
    bookmark_btns = page.query_selector_all("#yearView .bookmark-btn")
    print(f"  Bookmark buttons found: {len(bookmark_btns)}")
    bookmarked = 0
    for i, btn in enumerate(bookmark_btns[:3]):
        btn.click()
        page.wait_for_timeout(100)
        is_active = btn.evaluate("el => el.classList.contains('active')")
        if is_active:
            bookmarked += 1
    print(f"  Bookmarked: {bookmarked}/3")
    if bookmarked == 0:
        add_issue("Major", "reviewer", "Bookmarking does not work",
                  "Clicking bookmark buttons does not activate them.",
                  ".bookmark-btn")

    # 4. Toggle bookmark filter
    print("  [2.4] Testing bookmark filter...")
    bm_filter = page.query_selector("#bookmarkFilter")
    if bm_filter:
        bm_filter.click()
        page.wait_for_timeout(300)
        screenshot(page, "r2_04_bookmark_filter")
        visible_cards = page.query_selector_all("#yearView .subject-card:not([style*='display: none'])")
        print(f"  Visible cards after bookmark filter: {len(visible_cards)}")
        if len(visible_cards) > bookmarked + 1:
            add_issue("Minor", "reviewer", "Bookmark filter may not hide unbookmarked cards correctly",
                      f"Expected ~{bookmarked} cards, found {len(visible_cards)}.",
                      "#bookmarkFilter")
        # Toggle back
        bm_filter.click()
        page.wait_for_timeout(200)

    # 5. Year filter
    print("  [2.5] Testing year filter...")
    filter_chips = page.query_selector_all(".filter-chip[data-year]")
    year_chip_with_data = [c for c in filter_chips if c.get_attribute("data-year")]
    if len(year_chip_with_data) > 0:
        year_chip_with_data[0].click()
        page.wait_for_timeout(300)
        screenshot(page, "r2_05_year_filter")
        stats_el = page.query_selector("#searchStatsText")
        if stats_el:
            print(f"  Year filter stats: {stats_el.inner_text()}")

    # 6. Subject browse mode
    print("  [2.6] Testing subject view...")
    view_subject = page.query_selector("#viewSubject")
    if view_subject:
        view_subject.click()
        page.wait_for_timeout(500)
        screenshot(page, "r2_06_subject_view")
        sv_sections = page.query_selector_all("#subjectView .subject-view-section")
        print(f"  Subject view sections: {len(sv_sections)}")
        if len(sv_sections) == 0:
            add_issue("Major", "reviewer", "Subject view not populated",
                      "Switching to subject view does not create sections.",
                      "#subjectView, buildSubjectView()")

    # Disable practice mode
    if practice_btn:
        practice_btn.click()
        page.wait_for_timeout(200)

    if console_errors:
        add_issue("Major", "reviewer", f"Console errors in reviewer flow ({len(console_errors)})",
                  "\n".join(console_errors[:5]),
                  "Console")

    context.close()


def test_role3_mobile(browser):
    """Role 3: Mobile user - viewport 375x667"""
    print("\n=== Role 3: Mobile User (375x667) ===")
    context = browser.new_context(
        viewport={"width": 375, "height": 667},
        is_mobile=True,
        has_touch=True
    )
    page = context.new_page()
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    # 1. Open category page
    print("  [3.1] Opening category page on mobile...")
    page.goto(CATEGORY_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(500)
    screenshot(page, "r3_01_mobile_initial")

    # 2. Check hamburger menu visibility
    print("  [3.2] Checking hamburger menu...")
    hamburger = page.query_selector("#hamburgerBtn")
    if hamburger:
        is_visible = hamburger.is_visible()
        print(f"  Hamburger visible: {is_visible}")
        if not is_visible:
            add_issue("Critical", "mobile", "Hamburger menu not visible on mobile",
                      "The #hamburgerBtn is not visible at 375px viewport.",
                      "#hamburgerBtn, @media(max-width:768px)")
    else:
        add_issue("Critical", "mobile", "Hamburger menu element missing",
                  "#hamburgerBtn not found in DOM.", "HTML structure")

    # 3. Check sidebar is hidden initially
    sidebar = page.query_selector("#sidebar")
    if sidebar:
        sidebar_visible = sidebar.evaluate(
            "el => window.getComputedStyle(el).transform !== 'none' || el.classList.contains('open')")
        # On mobile, sidebar should be hidden (transform: translateX(-100%))
        sidebar_box = sidebar.bounding_box()
        if sidebar_box and sidebar_box["x"] >= 0:
            add_issue("Major", "mobile", "Sidebar visible on mobile initial load",
                      "Sidebar should be hidden (off-screen) on mobile by default.",
                      ".sidebar @media(max-width:768px)")

    # 4. Open sidebar via hamburger
    print("  [3.3] Opening sidebar...")
    if hamburger and hamburger.is_visible():
        hamburger.click()
        page.wait_for_timeout(500)
        screenshot(page, "r3_02_sidebar_open")

        sidebar_open = sidebar.evaluate("el => el.classList.contains('open')") if sidebar else False
        print(f"  Sidebar opened: {sidebar_open}")
        if not sidebar_open:
            add_issue("Critical", "mobile", "Hamburger click does not open sidebar",
                      "Clicking hamburger does not add .open to sidebar.",
                      "hamburger click handler in app.js")

        # 5. Click a sidebar year to expand, then click link, check auto-close
        print("  [3.4] Clicking sidebar link...")
        sidebar_years = page.query_selector_all(".sidebar-year")
        if len(sidebar_years) > 0:
            # First expand a year to make its links visible
            sidebar_years[0].click()
            page.wait_for_timeout(300)
            sidebar_links = page.query_selector_all(".sidebar-link")
            visible_links = [l for l in sidebar_links if l.is_visible()]
            print(f"  Visible sidebar links: {len(visible_links)}")
            if len(visible_links) > 0:
                visible_links[0].click(timeout=5000)
                page.wait_for_timeout(500)
                sidebar_still_open = sidebar.evaluate("el => el.classList.contains('open')") if sidebar else True
                print(f"  Sidebar after link click: {sidebar_still_open}")
                if sidebar_still_open:
                    add_issue("Minor", "mobile", "Sidebar does not auto-close after navigation",
                              "After clicking a sidebar link on mobile, sidebar remains open.",
                              "closeMobileSidebar() in app.js",
                              "1. Open hamburger\n2. Click sidebar link\n3. Sidebar stays open",
                              "Ensure closeMobileSidebar is called after link click")
            else:
                add_issue("Minor", "mobile", "Sidebar links not visible after expanding year",
                          "After clicking a sidebar-year on mobile, nested links are not visible.",
                          ".sidebar-subjects display logic")

    # Close sidebar if still open (it's blocking the page)
    if sidebar and sidebar.evaluate("el => el.classList.contains('open')"):
        # This is a real UX bug - sidebar stays open after link click,
        # and its z-index blocks all interactions with main content.
        # The overlay also doesn't properly receive clicks because sidebar elements intercept them.
        add_issue("Major", "mobile", "Sidebar blocks page interaction after staying open",
                  "When the sidebar remains open after clicking a sidebar link, it blocks pointer events on the main content area. The overlay click also fails because sidebar elements intercept the clicks. Users cannot interact with search, cards, or any content while sidebar is open.",
                  ".sidebar z-index:100, .sidebar-overlay z-index:90",
                  "1. Open hamburger\n2. Expand a year\n3. Click sidebar link (sidebar stays open)\n4. Try to click search input -- blocked by sidebar",
                  "Ensure closeMobileSidebar() is called after sidebar link click; also consider raising overlay z-index above sidebar")
        # Force close via JS to continue testing
        page.evaluate("() => { document.getElementById('sidebar').classList.remove('open'); document.getElementById('sidebarOverlay').classList.remove('active'); document.getElementById('hamburgerBtn').textContent = '\u2630'; }")
        page.wait_for_timeout(200)

    # 6. Search input test
    print("  [3.5] Testing search on mobile...")
    search_input = page.query_selector("#searchInput")
    if search_input:
        search_input.click(timeout=5000)
        page.wait_for_timeout(200)
        search_input.fill("警察")
        page.wait_for_timeout(500)
        screenshot(page, "r3_03_mobile_search")
        highlights = page.query_selector_all(".highlight")
        print(f"  Mobile search highlights: {len(highlights)}")

    # 7. Check touch targets >= 44px
    print("  [3.6] Checking touch target sizes...")
    interactive_selectors = [
        ".hamburger", ".dark-toggle", ".back-to-top",
        ".toolbar-btn", ".filter-chip", ".bookmark-btn",
        ".sidebar-year", ".sidebar-link", ".sidebar-home"
    ]
    small_targets = []
    for selector in interactive_selectors:
        elements = page.query_selector_all(selector)
        for el in elements:
            if el.is_visible():
                box = el.bounding_box()
                if box and (box["width"] < 44 or box["height"] < 44):
                    small_targets.append(f"{selector}: {box['width']:.0f}x{box['height']:.0f}px")
                    break  # Report once per selector
    if small_targets:
        add_issue("Major", "mobile", f"Touch targets too small ({len(small_targets)} types)",
                  "The following touch targets are smaller than 44x44px:\n" + "\n".join(small_targets),
                  "CSS min-height/min-width",
                  "Inspect element sizes on mobile viewport",
                  "Set min-width: 44px; min-height: 44px on interactive elements")
    print(f"  Small touch targets: {len(small_targets)}")

    # 8. Check content not overflowing
    print("  [3.7] Checking horizontal overflow...")
    has_overflow = page.evaluate("""() => {
        return document.documentElement.scrollWidth > document.documentElement.clientWidth;
    }""")
    if has_overflow:
        scroll_width = page.evaluate("() => document.documentElement.scrollWidth")
        client_width = page.evaluate("() => document.documentElement.clientWidth")
        add_issue("Major", "mobile", "Horizontal overflow on mobile",
                  f"Page scrollWidth ({scroll_width}px) > clientWidth ({client_width}px). Content overflows horizontally.",
                  "CSS layout",
                  "View page at 375px width",
                  "Check for elements with fixed widths > viewport")

    if console_errors:
        add_issue("Minor", "mobile", f"Console errors on mobile ({len(console_errors)})",
                  "\n".join(console_errors[:5]), "Console")

    context.close()


def test_role4_darkmode(browser):
    """Role 4: Dark mode enthusiast"""
    print("\n=== Role 4: Dark Mode User ===")
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    # 1. Open index page first (for dark toggle on index)
    print("  [4.1] Testing dark mode on index page...")
    page.goto(INDEX_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(500)
    screenshot(page, "r4_01_index_light")

    # Click dark toggle
    dark_toggle = page.query_selector("#darkToggle")
    if dark_toggle:
        dark_toggle.click()
        page.wait_for_timeout(500)
        is_dark = page.evaluate("() => document.documentElement.classList.contains('dark')")
        print(f"  Dark mode active: {is_dark}")
        if not is_dark:
            add_issue("Critical", "darkmode", "Dark mode toggle does not work on index",
                      "Clicking #darkToggle does not add .dark to <html>.",
                      "#darkToggle on index.html")
        screenshot(page, "r4_02_index_dark")

        # Check localStorage
        stored = page.evaluate("() => localStorage.getItem('exam-dark')")
        print(f"  localStorage exam-dark: {stored}")
        if stored != "true":
            add_issue("Major", "darkmode", "Dark mode preference not saved",
                      f"localStorage 'exam-dark' = '{stored}', expected 'true'.",
                      "Dark mode script")
    else:
        add_issue("Critical", "darkmode", "Dark mode toggle missing on index",
                  "#darkToggle not found.", "index.html")

    # 2. Navigate to category page, check dark mode persists
    print("  [4.2] Checking dark mode persistence...")
    page.goto(CATEGORY_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(500)
    is_dark_on_category = page.evaluate("() => document.documentElement.classList.contains('dark')")
    print(f"  Dark on category page: {is_dark_on_category}")
    if not is_dark_on_category:
        add_issue("Major", "darkmode", "Dark mode does not persist across pages",
                  "Navigating from index to category page loses dark mode.",
                  "initDarkMode() in app.js")
    screenshot(page, "r4_03_category_dark")

    # 3. Check key elements have correct dark colors
    print("  [4.3] Checking dark mode element colors...")
    checks = {
        "body background": ("body", "background-color"),
        "sidebar background": ("#sidebar", "background-color"),
        "card background": (".subject-card", "background-color"),
        "search input background": ("#searchInput", "background-color"),
        "search input text": ("#searchInput", "color"),
        "toolbar button": (".toolbar-btn", "background-color"),
    }
    color_issues = []
    for name, (selector, prop) in checks.items():
        el = page.query_selector(selector)
        if el:
            color = el.evaluate(f"el => window.getComputedStyle(el).{prop.replace('-', '')}" if '-' not in prop
                                else f"el => window.getComputedStyle(el).getPropertyValue('{prop}')")
            # Simple check: in dark mode, backgrounds should not be white (#fff / rgb(255,255,255))
            if "255, 255, 255" in str(color) and "background" in name:
                color_issues.append(f"{name}: {color}")
    if color_issues:
        add_issue("Major", "darkmode", f"Elements not properly styled in dark mode ({len(color_issues)})",
                  "The following elements appear to still have light backgrounds:\n" + "\n".join(color_issues),
                  "html.dark CSS overrides",
                  "Enable dark mode, inspect elements",
                  "Add html.dark overrides for missing elements")
    print(f"  Dark color issues: {len(color_issues)}")

    # 4. Test search in dark mode
    print("  [4.4] Testing search in dark mode...")
    search_input = page.query_selector("#searchInput")
    if search_input:
        search_input.fill("警察")
        page.wait_for_timeout(500)
        screenshot(page, "r4_04_dark_search")
        # Check highlight visibility in dark mode
        highlights = page.query_selector_all(".highlight")
        if len(highlights) > 0:
            hl_bg = highlights[0].evaluate("el => window.getComputedStyle(el).backgroundColor")
            print(f"  Dark highlight bg: {hl_bg}")
            # Highlight should not be bright yellow on dark bg
        search_input.fill("")
        page.wait_for_timeout(200)

    # 5. Test practice mode in dark mode
    print("  [4.5] Testing practice mode in dark mode...")
    practice_btn = page.query_selector("#practiceToggle")
    if practice_btn:
        practice_btn.click()
        page.wait_for_timeout(300)
        screenshot(page, "r4_05_dark_practice")
        practice_btn.click()
        page.wait_for_timeout(200)

    # 6. Switch back to light mode
    print("  [4.6] Switching back to light mode...")
    dark_toggle = page.query_selector("#darkToggle")
    if dark_toggle:
        dark_toggle.click()
        page.wait_for_timeout(500)
        is_light = not page.evaluate("() => document.documentElement.classList.contains('dark')")
        print(f"  Light mode restored: {is_light}")
        if not is_light:
            add_issue("Major", "darkmode", "Cannot switch back to light mode",
                      "Clicking dark toggle again does not remove .dark class.",
                      "#darkToggle")
        screenshot(page, "r4_06_back_to_light")

    if console_errors:
        add_issue("Minor", "darkmode", f"Console errors in dark mode ({len(console_errors)})",
                  "\n".join(console_errors[:5]), "Console")

    context.close()


def test_role5_keyboard(browser):
    """Role 5: Keyboard expert - accessibility"""
    print("\n=== Role 5: Keyboard Expert ===")
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    page.goto(CATEGORY_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(500)

    # 1. Check skip-link
    print("  [5.1] Testing skip-link...")
    skip_link = page.query_selector(".skip-link")
    if skip_link:
        # Focus the skip link via Tab
        page.keyboard.press("Tab")
        page.wait_for_timeout(200)
        active = page.evaluate("() => document.activeElement.className")
        print(f"  First Tab focuses: {active}")
        skip_link_focused = "skip-link" in active
        if skip_link_focused:
            print("  Skip-link received first Tab focus")
            # Check it's visible when focused
            skip_box = skip_link.bounding_box()
            if skip_box and skip_box["y"] < 0:
                add_issue("Minor", "keyboard", "Skip-link not visible on focus",
                          "Skip-link has focus but remains off-screen.",
                          ".skip-link:focus CSS")
        else:
            # Check if skip-link exists but isn't first focusable
            add_issue("Minor", "keyboard", "Skip-link not first focusable element",
                      f"First Tab focuses '{active}' instead of .skip-link.",
                      "HTML source order",
                      "1. Load page\n2. Press Tab",
                      "Ensure skip-link is the first focusable element in DOM")
    else:
        add_issue("Major", "keyboard", "Skip-link not found",
                  "No .skip-link element in the page.",
                  "Category page HTML",
                  "", "Add <a href='#main' class='skip-link'>Skip to content</a>")

    # 2. Test Ctrl+K shortcut
    print("  [5.2] Testing Ctrl+K shortcut...")
    page.keyboard.press("Escape")  # Clear any state
    page.wait_for_timeout(200)
    page.keyboard.press("Control+k")
    page.wait_for_timeout(200)
    active_after_ctrlk = page.evaluate("() => document.activeElement.id")
    print(f"  After Ctrl+K, focused: {active_after_ctrlk}")
    if active_after_ctrlk != "searchInput":
        add_issue("Major", "keyboard", "Ctrl+K does not focus search",
                  f"After Ctrl+K, focus is on '{active_after_ctrlk}' not 'searchInput'.",
                  "Keyboard shortcut handler in app.js")

    # 3. Test / shortcut
    print("  [5.3] Testing / shortcut...")
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    page.click("body")
    page.wait_for_timeout(100)
    page.keyboard.press("/")
    page.wait_for_timeout(200)
    active_after_slash = page.evaluate("() => document.activeElement.id")
    print(f"  After /, focused: {active_after_slash}")
    if active_after_slash != "searchInput":
        add_issue("Major", "keyboard", "'/' shortcut does not focus search",
                  f"After pressing '/', focus is on '{active_after_slash}' not 'searchInput'.",
                  "Keyboard shortcut handler in app.js")

    # 4. Test Escape clears search
    print("  [5.4] Testing Escape in search...")
    search_input = page.query_selector("#searchInput")
    if search_input:
        search_input.focus()
        search_input.fill("test query")
        page.wait_for_timeout(200)
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        val = search_input.input_value()
        is_focused = page.evaluate("() => document.activeElement.id === 'searchInput'")
        print(f"  After Escape: value='{val}', still focused={is_focused}")
        if val != "":
            add_issue("Major", "keyboard", "Escape does not clear search input",
                      f"After pressing Escape, search value is '{val}' (expected empty).",
                      "Escape handler in app.js")

    # 5. Test Enter/Space on subject header
    print("  [5.5] Testing Enter/Space on subject card...")
    first_card = page.query_selector("#yearView .subject-card")
    if first_card:
        header = first_card.query_selector(".subject-header")
        if header:
            # Close it first if open
            if first_card.evaluate("el => el.classList.contains('open')"):
                header.click()
                page.wait_for_timeout(200)

            header.focus()
            page.wait_for_timeout(100)
            page.keyboard.press("Enter")
            page.wait_for_timeout(300)
            is_open = first_card.evaluate("el => el.classList.contains('open')")
            print(f"  After Enter on header, card open: {is_open}")
            if not is_open:
                add_issue("Major", "keyboard", "Enter does not expand subject card",
                          "Pressing Enter on focused .subject-header does not toggle .open.",
                          "subject-header keydown handler",
                          "1. Focus subject header\n2. Press Enter",
                          "Ensure keydown handler for Enter is present")

            # Close and test Space
            if is_open:
                page.keyboard.press("Space")
                page.wait_for_timeout(300)
                is_closed = not first_card.evaluate("el => el.classList.contains('open')")
                print(f"  After Space, card closed: {is_closed}")
                if not is_closed:
                    add_issue("Minor", "keyboard", "Space does not toggle subject card",
                              "Pressing Space on focused header does not toggle card.",
                              "subject-header keydown handler")

    # 6. Test Enter/Space on sidebar year
    print("  [5.6] Testing Enter/Space on sidebar year...")
    sidebar_year = page.query_selector(".sidebar-year")
    if sidebar_year:
        sidebar_year.focus()
        page.wait_for_timeout(100)
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        year_active = sidebar_year.evaluate("el => el.classList.contains('active')")
        print(f"  After Enter on sidebar year, active: {year_active}")
        if not year_active:
            add_issue("Major", "keyboard", "Enter does not expand sidebar year",
                      "Pressing Enter on focused .sidebar-year does not toggle .active.",
                      "sidebar-year keydown handler in app.js")

    # 7. Check focus-visible styles
    print("  [5.7] Checking focus-visible styles...")
    focus_elements_to_check = [
        ("#searchInput", "search input"),
        (".toolbar-btn", "toolbar button"),
        (".filter-chip", "filter chip"),
        (".subject-header", "subject header"),
        (".dark-toggle", "dark toggle"),
        (".back-to-top", "back to top"),
    ]
    missing_focus = []
    for selector, name in focus_elements_to_check:
        el = page.query_selector(selector)
        if el:
            # Focus the element and check for outline
            el.focus()
            page.wait_for_timeout(50)
            outline = el.evaluate("el => window.getComputedStyle(el).outlineStyle")
            outline_w = el.evaluate("el => window.getComputedStyle(el).outlineWidth")
            if outline == "none" or outline_w == "0px":
                # Check for box-shadow or border as alternative focus indicator
                box_shadow = el.evaluate("el => window.getComputedStyle(el).boxShadow")
                if box_shadow == "none":
                    missing_focus.append(f"{name} ({selector})")

    if missing_focus:
        add_issue("Major", "keyboard", f"Missing focus-visible styles ({len(missing_focus)} elements)",
                  "The following elements lack visible focus indicators:\n" + "\n".join(missing_focus),
                  ":focus-visible CSS rules",
                  "Tab through page, observe focus rings",
                  "Add :focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }")
    print(f"  Elements missing focus style: {len(missing_focus)}")

    # 8. Full Tab navigation test
    print("  [5.8] Tab navigation count...")
    page.keyboard.press("Escape")
    page.wait_for_timeout(100)
    page.evaluate("() => document.activeElement.blur()")
    tab_count = 0
    seen_ids = set()
    max_tabs = 50
    for _ in range(max_tabs):
        page.keyboard.press("Tab")
        page.wait_for_timeout(30)
        active_id = page.evaluate("() => document.activeElement.id || document.activeElement.className || document.activeElement.tagName")
        if active_id in seen_ids and tab_count > 5:
            break
        seen_ids.add(active_id)
        tab_count += 1
    print(f"  Tab stops: {tab_count}")

    screenshot(page, "r5_01_keyboard_test")

    if console_errors:
        add_issue("Minor", "keyboard", f"Console errors ({len(console_errors)})",
                  "\n".join(console_errors[:5]), "Console")

    context.close()


def test_extra_checks(browser):
    """Additional checks: console errors, network failures, index page dark mode"""
    print("\n=== Extra Checks ===")
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()

    console_errors = []
    page_errors = []
    failed_requests = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda err: page_errors.append(str(err)))
    page.on("requestfailed", lambda req: failed_requests.append(f"{req.method} {req.url}: {req.failure}"))

    # Check index page
    print("  [E.1] Index page checks...")
    page.goto(INDEX_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    # Check index page has no skip-link
    index_skip = page.query_selector(".skip-link")
    if not index_skip:
        add_issue("Minor", "general", "Index page missing skip-link",
                  "index.html has no .skip-link for keyboard navigation.",
                  "index.html HTML")

    # Check index page dark toggle position (should be bottom-right per index CSS)
    dark_toggle = page.query_selector("#darkToggle")
    if dark_toggle:
        dt_box = dark_toggle.bounding_box()
        viewport_width = 1280
        if dt_box and dt_box["x"] < viewport_width / 2:
            # On index, dark toggle CSS says bottom:2rem; right:2rem but category CSS overrides to left:2rem
            print(f"  Index dark toggle position: x={dt_box['x']:.0f}, y={dt_box['y']:.0f}")

    # Check links
    print("  [E.2] Checking category links...")
    links = page.query_selector_all(".category-card")
    for link in links:
        href = link.get_attribute("href")
        if href and not href.startswith("http"):
            # Relative URL check
            title = link.query_selector(".card-title")
            title_text = title.inner_text() if title else "Unknown"
            # Try navigating
            full_url = f"{BASE}/{href}"
            # We'll check just the href format
            if not href.endswith(".html"):
                add_issue("Minor", "general", f"Unusual href for {title_text}",
                          f"href='{href}' does not end with .html",
                          "index.html links")

    # Check category page
    print("  [E.3] Category page detailed checks...")
    page.goto(CATEGORY_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    # Check ARIA attributes
    subject_headers = page.query_selector_all(".subject-header")
    headers_without_aria = 0
    for h in subject_headers[:5]:
        role = h.get_attribute("role")
        tabindex = h.get_attribute("tabindex")
        aria_expanded = h.get_attribute("aria-expanded")
        if not role or not tabindex:
            headers_without_aria += 1
    if headers_without_aria > 0:
        add_issue("Minor", "general", f"Subject headers missing ARIA attrs ({headers_without_aria})",
                  "Some .subject-header elements lack role='button' or tabindex.",
                  ".subject-header ARIA attributes")

    # Check back-to-top button
    btt = page.query_selector("#backToTop")
    if btt:
        btt_visible = btt.evaluate("el => el.classList.contains('visible')")
        print(f"  Back-to-top initially visible: {btt_visible}")
        # Scroll down
        page.evaluate("window.scrollTo(0, 1000)")
        page.wait_for_timeout(500)
        btt_visible_after = btt.evaluate("el => el.classList.contains('visible')")
        print(f"  Back-to-top after scroll: {btt_visible_after}")
        if not btt_visible_after:
            add_issue("Minor", "general", "Back-to-top not visible after scroll",
                      "After scrolling 1000px, #backToTop does not become .visible.",
                      "#backToTop scroll handler")

    # Check font loading
    print("  [E.4] Checking external resources...")
    if failed_requests:
        add_issue("Major", "general", f"Failed network requests ({len(failed_requests)})",
                  "\n".join(failed_requests[:10]),
                  "Network requests",
                  "Open Network tab in DevTools",
                  "Fix broken URLs or add fallback fonts")
    print(f"  Failed requests: {len(failed_requests)}")
    print(f"  Console errors: {len(console_errors)}")
    print(f"  Page errors: {len(page_errors)}")

    if page_errors:
        add_issue("Critical", "general", f"Uncaught JavaScript errors ({len(page_errors)})",
                  "\n".join(page_errors[:5]),
                  "JavaScript runtime")
    if console_errors:
        for err in console_errors[:5]:
            if "favicon" not in err.lower():
                add_issue("Minor", "general", "Console error",
                          err, "Console")

    context.close()


def generate_report():
    """Generate the markdown report"""
    severity_order = {"Critical": 0, "Major": 1, "Minor": 2, "Info": 3}
    sorted_issues = sorted(issues, key=lambda x: severity_order.get(x["severity"], 9))

    report = f"""# Round 1 UX 審計報告

**生成時間**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**測試工具**: Playwright {os.popen('pip show playwright 2>/dev/null').read().split("Version: ")[1].split()[0] if False else '1.58.0'}
**測試頁面**:
- 首頁: `index.html`
- 類科頁面: `行政警察/行政警察考古題總覽.html`

## 問題總覽

共發現 **{len(issues)}** 個問題：
- Critical: {sum(1 for i in issues if i['severity'] == 'Critical')}
- Major: {sum(1 for i in issues if i['severity'] == 'Major')}
- Minor: {sum(1 for i in issues if i['severity'] == 'Minor')}

| # | 嚴重度 | 角色 | 問題描述 | 位置 |
|---|--------|------|---------|------|
"""
    for idx, issue in enumerate(sorted_issues, 1):
        role_map = {
            "beginner": "新手考生",
            "reviewer": "密集複習者",
            "mobile": "手機用戶",
            "darkmode": "深色模式",
            "keyboard": "鍵盤專家",
            "general": "通用",
        }
        role_zh = role_map.get(issue["role"], issue["role"])
        report += f"| {idx} | {issue['severity']} | {role_zh} | {issue['title']} | {issue['location']} |\n"

    report += "\n## 詳細問題\n\n"

    for idx, issue in enumerate(sorted_issues, 1):
        role_map = {
            "beginner": "新手考生",
            "reviewer": "密集複習者",
            "mobile": "手機用戶",
            "darkmode": "深色模式",
            "keyboard": "鍵盤專家",
            "general": "通用",
        }
        role_zh = role_map.get(issue["role"], issue["role"])
        report += f"### #{idx} [{issue['severity']}] {issue['title']}\n"
        report += f"- **角色**: {role_zh}\n"
        report += f"- **描述**: {issue['description']}\n"
        if issue.get("location"):
            report += f"- **位置**: `{issue['location']}`\n"
        if issue.get("steps"):
            report += f"- **重現步驟**:\n"
            for step in issue["steps"].split("\n"):
                report += f"  {step}\n"
        if issue.get("suggestion"):
            report += f"- **建議修復**: {issue['suggestion']}\n"
        report += "\n"

    report += """## 測試截圖

截圖存放於 `reports/screenshots/` 目錄：
- `r1_*.png` - 角色 1 (新手考生)
- `r2_*.png` - 角色 2 (密集複習者)
- `r3_*.png` - 角色 3 (手機用戶)
- `r4_*.png` - 角色 4 (深色模式)
- `r5_*.png` - 角色 5 (鍵盤專家)

## 測試環境
- Playwright Python (sync API)
- Chromium browser
- Desktop viewport: 1280x800
- Mobile viewport: 375x667
"""
    return report


def main():
    print("=" * 60)
    print("UX Audit Test - 5 User Roles")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            test_role1_beginner(browser)
        except Exception as e:
            print(f"  ERROR in Role 1: {e}")
            traceback.print_exc()
            add_issue("Critical", "beginner", f"Test crash: {str(e)[:100]}", traceback.format_exc()[:500], "test script")

        try:
            test_role2_reviewer(browser)
        except Exception as e:
            print(f"  ERROR in Role 2: {e}")
            traceback.print_exc()
            add_issue("Critical", "reviewer", f"Test crash: {str(e)[:100]}", traceback.format_exc()[:500], "test script")

        try:
            test_role3_mobile(browser)
        except Exception as e:
            print(f"  ERROR in Role 3: {e}")
            traceback.print_exc()
            add_issue("Critical", "mobile", f"Test crash: {str(e)[:100]}", traceback.format_exc()[:500], "test script")

        try:
            test_role4_darkmode(browser)
        except Exception as e:
            print(f"  ERROR in Role 4: {e}")
            traceback.print_exc()
            add_issue("Critical", "darkmode", f"Test crash: {str(e)[:100]}", traceback.format_exc()[:500], "test script")

        try:
            test_role5_keyboard(browser)
        except Exception as e:
            print(f"  ERROR in Role 5: {e}")
            traceback.print_exc()
            add_issue("Critical", "keyboard", f"Test crash: {str(e)[:100]}", traceback.format_exc()[:500], "test script")

        try:
            test_extra_checks(browser)
        except Exception as e:
            print(f"  ERROR in Extra: {e}")
            traceback.print_exc()
            add_issue("Critical", "general", f"Test crash: {str(e)[:100]}", traceback.format_exc()[:500], "test script")

        browser.close()

    report = generate_report()
    report_path = "C:/Users/User/Desktop/考古題下載/reports/round1_ux_audit.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n{'=' * 60}")
    print(f"Report written to: {report_path}")
    print(f"Total issues found: {len(issues)}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
