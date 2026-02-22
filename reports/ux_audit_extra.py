"""
Additional UX audit checks based on visual inspection and code analysis.
"""
import os
import json
from playwright.sync_api import sync_playwright

BASE = "file:///C:/Users/User/Desktop/考古題下載/考古題網站"
INDEX_URL = f"{BASE}/index.html"
CATEGORY_URL = f"{BASE}/行政警察/行政警察考古題總覽.html"
SCREENSHOT_DIR = "C:/Users/User/Desktop/考古題下載/reports/screenshots"

extra_issues = []

def add_issue(severity, role, title, description, location="", steps="", suggestion=""):
    extra_issues.append({
        "severity": severity,
        "role": role,
        "title": title,
        "description": description,
        "location": location,
        "steps": steps,
        "suggestion": suggestion
    })

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # === Test 1: Mobile sidebar link click behavior deep dive ===
        print("=== Extra Test 1: Mobile sidebar link click auto-close ===")
        ctx = browser.new_context(viewport={"width": 375, "height": 667}, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        # Check the closeMobileSidebar binding
        has_close_binding = page.evaluate("""() => {
            const links = document.querySelectorAll('.sidebar-link');
            // Check if any link has event listener (we can't directly, but test behavior)
            return links.length;
        }""")
        print(f"  Sidebar links: {has_close_binding}")

        # Open hamburger, click sidebar year, then click link
        hamburger = page.query_selector("#hamburgerBtn")
        if hamburger:
            hamburger.click()
            page.wait_for_timeout(300)
            # Expand first year
            year = page.query_selector(".sidebar-year")
            if year:
                year.click()
                page.wait_for_timeout(200)
                # Click first visible link via JS to avoid pointer interception
                result = page.evaluate("""() => {
                    const links = document.querySelectorAll('.sidebar-link');
                    for (const link of links) {
                        if (link.offsetParent !== null) {
                            link.click();
                            return {
                                sidebarOpen: document.getElementById('sidebar').classList.contains('open'),
                                overlayActive: document.getElementById('sidebarOverlay').classList.contains('active'),
                                hamburgerText: document.getElementById('hamburgerBtn').textContent
                            };
                        }
                    }
                    return null;
                }""")
                print(f"  After sidebar link click: {result}")
                if result and result['sidebarOpen']:
                    print("  CONFIRMED: Sidebar stays open after link click on mobile")
                else:
                    print("  Sidebar correctly closes after link click")
        ctx.close()

        # === Test 2: Index page dark mode toggle position ===
        print("\n=== Extra Test 2: Index dark toggle position ===")
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.goto(INDEX_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        dt_box = page.query_selector("#darkToggle").bounding_box()
        vw = 1280
        print(f"  Dark toggle: x={dt_box['x']:.0f}, y={dt_box['y']:.0f}")
        # On index page, dark toggle is in CSS as bottom:2rem right:2rem
        # On category page CSS, it's bottom:2rem left:2rem
        # This means position differs between pages
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(500)
        dt_box2 = page.query_selector("#darkToggle").bounding_box()
        print(f"  Category dark toggle: x={dt_box2['x']:.0f}, y={dt_box2['y']:.0f}")
        if abs(dt_box['x'] - dt_box2['x']) > 100:
            add_issue("Minor", "darkmode", "Dark mode toggle position inconsistent between pages",
                      f"On index page, dark toggle is at x={dt_box['x']:.0f} (right side). On category page, it's at x={dt_box2['x']:.0f} (left side). Users may have difficulty finding it.",
                      "index.html inline CSS vs css/style.css .dark-toggle",
                      "1. Open index.html, note toggle position\n2. Open category page, note toggle position",
                      "Unify position to bottom-left (near sidebar) or bottom-right consistently")
        ctx.close()

        # === Test 3: Index page category cards keyboard accessibility ===
        print("\n=== Extra Test 3: Index card keyboard access ===")
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.goto(INDEX_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        # Category cards are <a> tags so should be keyboard focusable
        card = page.query_selector(".category-card")
        if card:
            tag = card.evaluate("el => el.tagName")
            print(f"  Category card tag: {tag}")
            # Focus and check focus-visible
            card.focus()
            page.wait_for_timeout(100)
            outline = card.evaluate("el => window.getComputedStyle(el).outlineStyle")
            print(f"  Focus outline: {outline}")
            # Check if Enter works
            page.keyboard.press("Enter")
            page.wait_for_timeout(500)
            new_url = page.url
            navigated = "index.html" not in new_url
            print(f"  Enter navigated: {navigated} ({new_url[:80]})")

        # Check index footer
        footer = page.query_selector(".site-footer")
        if footer:
            ft = footer.inner_text()
            print(f"  Footer: {ft}")

        ctx.close()

        # === Test 4: Long question text wrapping on mobile ===
        print("\n=== Extra Test 4: Long question text on mobile ===")
        ctx = browser.new_context(viewport={"width": 375, "height": 667}, is_mobile=True)
        page = ctx.new_page()
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        # Open first card via JS
        page.evaluate("""() => {
            const card = document.querySelector('#yearView .subject-card');
            if (card) card.classList.add('open');
        }""")
        page.wait_for_timeout(200)

        # Check if any mc-question overflows
        overflow = page.evaluate("""() => {
            const qs = document.querySelectorAll('.mc-question');
            let overflows = [];
            const vw = window.innerWidth;
            for (let i = 0; i < Math.min(qs.length, 10); i++) {
                const rect = qs[i].getBoundingClientRect();
                if (rect.right > vw + 5) {
                    overflows.push({
                        idx: i,
                        right: Math.round(rect.right),
                        viewportWidth: vw
                    });
                }
            }
            return overflows;
        }""")
        if overflow:
            add_issue("Major", "mobile", f"Question text overflows viewport ({len(overflow)} questions)",
                      f"Some .mc-question elements extend beyond viewport. Examples: {json.dumps(overflow[:3])}",
                      ".mc-question, .q-text CSS",
                      "View category page on mobile, expand a card, scroll to see long questions",
                      "Add word-break: break-word or overflow-wrap: break-word to .q-text")
        print(f"  Question overflow count: {len(overflow)}")

        # Check overall page overflow again with card open
        scroll_w = page.evaluate("() => document.documentElement.scrollWidth")
        client_w = page.evaluate("() => document.documentElement.clientWidth")
        print(f"  scrollWidth={scroll_w}, clientWidth={client_w}")
        if scroll_w > client_w:
            # Find which elements overflow
            overflowing = page.evaluate("""() => {
                const vw = document.documentElement.clientWidth;
                const results = [];
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    const rect = el.getBoundingClientRect();
                    if (rect.right > vw + 10 && el.offsetParent !== null) {
                        const tag = el.tagName.toLowerCase();
                        const cls = el.className ? '.' + el.className.split(' ')[0] : '';
                        const id = el.id ? '#' + el.id : '';
                        results.push(`${tag}${id}${cls}: right=${Math.round(rect.right)}px, width=${Math.round(rect.width)}px`);
                        if (results.length >= 5) break;
                    }
                }
                return results;
            }""")
            print(f"  Overflowing elements: {overflowing}")
            if overflowing:
                add_issue("Major", "mobile", "Elements causing horizontal overflow on mobile",
                          "When content is expanded on mobile, these elements overflow:\n" + "\n".join(overflowing),
                          "CSS layout",
                          "Open category page on mobile, expand a subject card",
                          "Add overflow-wrap: break-word to container or max-width: 100% to overflowing elements")

        page.screenshot(path=f"{SCREENSHOT_DIR}/extra_mobile_overflow.png", full_page=False)
        ctx.close()

        # === Test 5: Export panel behavior ===
        print("\n=== Extra Test 5: Export panel ===")
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        export_btn = page.query_selector("#exportBtn")
        if export_btn:
            export_btn.click()
            page.wait_for_timeout(300)
            export_panel = page.query_selector("#exportPanel")
            panel_visible = export_panel.evaluate("el => el.style.display !== 'none'") if export_panel else False
            print(f"  Export panel visible after click: {panel_visible}")

            if panel_visible:
                # Test Escape closes it
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)
                panel_after_esc = export_panel.evaluate("el => el.style.display !== 'none'") if export_panel else True
                print(f"  Export panel after Escape: {panel_after_esc}")
                if panel_after_esc:
                    add_issue("Minor", "keyboard", "Escape does not close export panel",
                              "Pressing Escape while export panel is visible does not close it.",
                              "Escape handler in app.js",
                              "1. Click 'Export PDF'\n2. Press Escape\n3. Panel stays open",
                              "Add export panel check in Escape handler")

                # Re-open and test cancel
                export_btn.click()
                page.wait_for_timeout(200)
                cancel = page.query_selector(".export-cancel")
                if cancel:
                    cancel.click()
                    page.wait_for_timeout(200)
                    panel_after_cancel = export_panel.evaluate("el => el.style.display !== 'none'") if export_panel else True
                    print(f"  Export panel after cancel: {panel_after_cancel}")

        # Test export panel ARIA role
        export_panel = page.query_selector("#exportPanel")
        if export_panel:
            role = export_panel.get_attribute("role")
            aria_label = export_panel.get_attribute("aria-label")
            print(f"  Export panel role={role}, aria-label={aria_label}")

        ctx.close()

        # === Test 6: Search highlight contrast in dark mode ===
        print("\n=== Extra Test 6: Dark mode search highlights ===")
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        # Enable dark mode
        page.evaluate("() => document.documentElement.classList.add('dark')")
        page.wait_for_timeout(200)

        # Search for something
        page.fill("#searchInput", "憲法")
        page.wait_for_timeout(500)

        # Check highlight contrast
        hl = page.query_selector(".highlight")
        if hl:
            bg = hl.evaluate("el => window.getComputedStyle(el).backgroundColor")
            color = hl.evaluate("el => window.getComputedStyle(el).color")
            print(f"  Dark highlight: bg={bg}, color={color}")
            page.screenshot(path=f"{SCREENSHOT_DIR}/extra_dark_highlight.png", full_page=False)

        ctx.close()

        # === Test 7: Sidebar collapsed state persistence ===
        print("\n=== Extra Test 7: Sidebar collapse persistence ===")
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        # Click sidebar toggle to collapse
        sidebar_toggle = page.query_selector("#sidebarToggle")
        if sidebar_toggle:
            sidebar_toggle.click()
            page.wait_for_timeout(300)
            is_collapsed = page.evaluate("() => document.body.classList.contains('sidebar-collapsed')")
            stored = page.evaluate("() => localStorage.getItem('sidebar-collapsed')")
            print(f"  Collapsed: {is_collapsed}, stored: {stored}")

            # Check reopen button
            reopen = page.query_selector("#sidebarReopen")
            if reopen:
                is_visible = reopen.is_visible()
                print(f"  Reopen button visible: {is_visible}")
                if is_visible:
                    reopen.click()
                    page.wait_for_timeout(300)
                    is_uncollapsed = not page.evaluate("() => document.body.classList.contains('sidebar-collapsed')")
                    print(f"  Uncollapsed after reopen: {is_uncollapsed}")

        ctx.close()

        # === Test 8: Print mode check ===
        print("\n=== Extra Test 8: Print styles ===")
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        # Emulate print media
        page.emulate_media(media="print")
        page.wait_for_timeout(300)

        # Check sidebar hidden
        sidebar_display = page.evaluate("() => window.getComputedStyle(document.getElementById('sidebar')).display")
        search_display = page.evaluate("() => window.getComputedStyle(document.querySelector('.search-box')).display")
        toolbar_display = page.evaluate("() => window.getComputedStyle(document.querySelector('.toolbar')).display")
        print(f"  Print: sidebar={sidebar_display}, search={search_display}, toolbar={toolbar_display}")

        if sidebar_display != "none":
            add_issue("Minor", "general", "Sidebar visible in print mode",
                      "The sidebar is not hidden when printing.",
                      "@media print CSS rules",
                      "Print the page or emulate print media",
                      "Add .sidebar { display: none !important; } to @media print")

        page.emulate_media(media="screen")
        ctx.close()

        # === Test 9: Check all 15 category links resolve ===
        print("\n=== Extra Test 9: Category link validation ===")
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.goto(INDEX_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        links = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('.category-card')).map(a => ({
                href: a.getAttribute('href'),
                title: a.querySelector('.card-title').textContent
            }));
        }""")
        print(f"  Category links: {len(links)}")
        broken = []
        for link in links:
            full_url = f"{BASE}/{link['href']}"
            try:
                resp = page.goto(full_url, wait_until="domcontentloaded", timeout=5000)
                if resp and resp.status >= 400:
                    broken.append(f"{link['title']}: HTTP {resp.status}")
                else:
                    # Check page has content
                    has_content = page.query_selector(".page-title") is not None
                    if not has_content:
                        broken.append(f"{link['title']}: No .page-title found")
            except Exception as e:
                broken.append(f"{link['title']}: {str(e)[:60]}")

        if broken:
            add_issue("Critical", "beginner", f"Broken category links ({len(broken)})",
                      "The following category links do not work:\n" + "\n".join(broken),
                      "index.html .category-card[href]",
                      "Click each category card on index page",
                      "Fix broken href attributes")
        print(f"  Broken links: {len(broken)}")
        ctx.close()

        # === Test 10: Galaxy Fold extreme width ===
        print("\n=== Extra Test 10: Galaxy Fold (280px) ===")
        ctx = browser.new_context(viewport={"width": 280, "height": 653}, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        page.goto(CATEGORY_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(500)
        page.screenshot(path=f"{SCREENSHOT_DIR}/extra_galaxy_fold.png", full_page=False)

        scroll_w = page.evaluate("() => document.documentElement.scrollWidth")
        client_w = page.evaluate("() => document.documentElement.clientWidth")
        print(f"  Galaxy Fold: scrollW={scroll_w}, clientW={client_w}")
        if scroll_w > client_w + 5:
            add_issue("Minor", "mobile", f"Horizontal overflow on Galaxy Fold (280px)",
                      f"scrollWidth={scroll_w}px vs clientWidth={client_w}px at 280px viewport.",
                      "@media (max-width: 320px) CSS",
                      "View on Galaxy Fold (280px viewport)",
                      "Check Galaxy Fold media query coverage")

        # Check touch targets at this size
        small = page.evaluate("""() => {
            const selectors = ['.hamburger', '.toolbar-btn', '.filter-chip'];
            const results = [];
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                for (const el of els) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0 && (rect.width < 44 || rect.height < 44)) {
                        results.push(`${sel}: ${Math.round(rect.width)}x${Math.round(rect.height)}px`);
                        break;
                    }
                }
            }
            return results;
        }""")
        print(f"  Small touch targets at 280px: {small}")

        ctx.close()

        browser.close()

    # Print summary
    print(f"\n{'='*60}")
    print(f"Extra issues found: {len(extra_issues)}")
    for i, issue in enumerate(extra_issues, 1):
        print(f"  [{issue['severity']}] {issue['title']}")
    print(f"{'='*60}")

    # Save as JSON for merging
    with open("C:/Users/User/Desktop/考古題下載/reports/extra_issues.json", "w", encoding="utf-8") as f:
        json.dump(extra_issues, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
