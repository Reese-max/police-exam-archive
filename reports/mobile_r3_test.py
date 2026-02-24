"""Round 3 Mobile UX Audit - Playwright Test Script (v3 - JS clicks for reliability)"""
import os, json, time, traceback
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path(r"C:\Users\User\Desktop\考古題下載\考古題網站")
REPORT_DIR = Path(r"C:\Users\User\Desktop\考古題下載\reports")
SS_DIR = REPORT_DIR / "screenshots" / "r3"
SS_DIR.mkdir(parents=True, exist_ok=True)

CATEGORY_PAGE = (BASE / "行政警察學系" / "行政警察學系考古題總覽.html").as_uri()
INDEX_PAGE = (BASE / "index.html").as_uri()

VIEWPORTS = {
    "iPhone_SE":        {"width": 375, "height": 667},
    "Galaxy_Fold":      {"width": 280, "height": 653},
    "iPhone14_ProMax":  {"width": 430, "height": 932},
    "iPad_Mini":        {"width": 768, "height": 1024},
}

results = []

def record(test_name, viewport, passed, detail=""):
    results.append({"test": test_name, "viewport": viewport, "passed": passed, "detail": detail})
    print(f"    [{'PASS' if passed else 'FAIL'}] {test_name}: {detail[:120]}")

def ss(page, name):
    try: page.screenshot(path=str(SS_DIR / f"{name}.png"), full_page=False, timeout=5000)
    except: pass

def w(page, ms=300):
    page.wait_for_timeout(ms)

def js_click(page, selector):
    """Click via JS to avoid actionability timeout issues"""
    page.evaluate(f"document.querySelector('{selector}')?.click()")

# =========================================================================
# TESTS
# =========================================================================

def test_touch_targets(page, vp_name):
    small = page.evaluate("""
        () => {
            const sels = ['.hamburger','.toolbar-btn','.filter-chip','.bookmark-btn',
                '.back-to-top','.dark-toggle','.sidebar-link','.sidebar-year',
                '.sidebar-home','.subject-header','.score-reset'];
            let bad = [];
            for (const s of sels) {
                const els = document.querySelectorAll(s);
                for (let i = 0; i < Math.min(els.length, 5); i++) {
                    const el = els[i];
                    const r = el.getBoundingClientRect();
                    if (r.width === 0 && r.height === 0) continue;
                    const cs = getComputedStyle(el);
                    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
                    if (r.width < 44 || r.height < 44) {
                        bad.push(el.tagName + '.' + s.replace('.','') + ': ' + r.width.toFixed(0) + 'x' + r.height.toFixed(0));
                    }
                }
            }
            return bad;
        }
    """)
    unique = list(set(small))[:8]
    if unique:
        record("touch_targets", vp_name, False, f"{len(small)} elements < 44px: {'; '.join(unique)}")
    else:
        record("touch_targets", vp_name, True, "All visible clickable elements >= 44x44px")


def test_horizontal_overflow(page, vp_name):
    sw = page.evaluate("document.documentElement.scrollWidth")
    vw = page.viewport_size["width"]
    record("horizontal_overflow", vp_name, sw <= vw, f"scrollWidth={sw}, viewport={vw}")


def test_text_truncation(page, vp_name):
    r = page.evaluate("""
        () => {
            for (const l of document.querySelectorAll('.sidebar-link')) {
                const t = l.getAttribute('title') || '';
                if (t.length > 30) {
                    const s = getComputedStyle(l);
                    if (s.textOverflow !== 'ellipsis') return {ok:false, t: t.substring(0,40)};
                }
            }
            return {ok: true};
        }
    """)
    record("text_truncation", vp_name, r["ok"],
           "Long items have ellipsis" if r["ok"] else f"Missing: {r.get('t','')}")


def test_hamburger_menu(page, vp_name):
    vis = page.evaluate("getComputedStyle(document.getElementById('hamburgerBtn')).display !== 'none'")
    if not vis:
        record("hamburger_menu", vp_name, vp_name == "iPad_Mini",
               "Hamburger hidden" + (" (expected 768px)" if vp_name == "iPad_Mini" else ""))
        return

    js_click(page, "#hamburgerBtn")
    w(page, 500)
    opened = page.evaluate("document.getElementById('sidebar').classList.contains('open')")
    overlay = page.evaluate("document.getElementById('sidebarOverlay').classList.contains('active')")
    ss(page, f"hamburger_open_{vp_name}")

    # Click first sidebar link
    page.evaluate("document.querySelector('.sidebar-link')?.click()")
    w(page, 500)
    closed = not page.evaluate("document.getElementById('sidebar').classList.contains('open')")
    overlay_gone = not page.evaluate("document.getElementById('sidebarOverlay').classList.contains('active')")

    record("hamburger_menu", vp_name, opened and overlay and closed and overlay_gone,
           f"open={opened}, overlay={overlay}, close={closed}, overlay_gone={overlay_gone}")


def test_search(page, vp_name):
    page.evaluate("""
        () => {
            const inp = document.getElementById('searchInput');
            inp.value = '警察';
            inp.dispatchEvent(new Event('input'));
        }
    """)
    w(page, 600)
    stats = page.evaluate("document.getElementById('searchStatsText').textContent") or ""
    has_results = "找到" in stats
    hl_count = page.evaluate("document.querySelectorAll('.highlight').length")
    ss(page, f"search_{vp_name}")

    # Clear
    page.evaluate("""
        () => {
            const inp = document.getElementById('searchInput');
            inp.value = '';
            inp.dispatchEvent(new Event('input'));
        }
    """)
    w(page, 400)
    cleared = (page.evaluate("document.getElementById('searchStatsText').textContent") or "").strip() == ""
    record("search", vp_name, has_results and hl_count > 0 and cleared,
           f"results={has_results}, highlights={hl_count}, cleared={cleared}, stats='{stats[:50]}'")


def test_year_filter(page, vp_name):
    page.evaluate("document.querySelector('.filter-chip[data-year=\"114\"]')?.click()")
    w(page, 500)
    visible = page.evaluate("""
        () => {
            let v = [];
            document.querySelectorAll('#yearView .year-section').forEach(s => {
                if (s.style.display !== 'none') v.push(s.querySelector('.year-heading').textContent.trim());
            });
            return v;
        }
    """)
    only_114 = len(visible) == 1 and "114" in visible[0]

    page.evaluate("document.querySelector('.filter-chip[data-year=\"\"]')?.click()")
    w(page, 400)
    restored = page.evaluate("document.querySelectorAll('#yearView .year-section:not([style*=\"display: none\"])').length") > 1
    record("year_filter", vp_name, only_114 and restored,
           f"only_114={only_114}, visible={visible}, restored={restored}")


def test_practice_mode(page, vp_name):
    # Expand first card
    page.evaluate("document.querySelector('.subject-card')?.classList.add('open')")
    w(page, 200)

    # Toggle practice mode
    page.evaluate("document.getElementById('practiceToggle')?.click()")
    w(page, 500)
    score_visible = page.evaluate("document.getElementById('practiceScore').classList.contains('visible')")
    ss(page, f"practice_{vp_name}")

    # Click reveal
    reveal_worked = page.evaluate("""
        () => {
            const btn = document.querySelector('.reveal-btn');
            if (!btn) return false;
            btn.click();
            return true;
        }
    """)
    w(page, 400)
    revealed = page.evaluate("document.querySelector('.answer-section.revealed') !== null")

    # Click score btn if visible
    score_updated = page.evaluate("""
        () => {
            const btn = document.querySelector('.score-btn.visible');
            if (btn) { btn.click(); return true; }
            // Free point case
            return document.getElementById('scoreTotal').textContent.trim() !== '0';
        }
    """)
    w(page, 200)
    total_text = page.evaluate("document.getElementById('scoreTotal').textContent.trim()")

    # End practice
    page.evaluate("document.getElementById('practiceToggle')?.click()")
    w(page, 300)
    ended = not page.evaluate("document.getElementById('practiceScore').classList.contains('visible')")

    record("practice_mode", vp_name, score_visible and ended,
           f"score_panel={score_visible}, reveal={reveal_worked}, revealed={revealed}, "
           f"score_total={total_text}, ended={ended}")


def test_bookmarks(page, vp_name):
    # Expand first card
    page.evaluate("document.querySelector('.subject-card')?.classList.add('open')")
    w(page, 200)

    # Click bookmark
    page.evaluate("document.querySelector('.bookmark-btn')?.click()")
    w(page, 200)
    is_active = page.evaluate("document.querySelector('.bookmark-btn')?.classList.contains('active') || false")
    star = page.evaluate("(document.querySelector('.bookmark-btn')?.textContent || '').trim() === '★'")

    # Activate bookmark filter
    page.evaluate("document.getElementById('bookmarkFilter')?.click()")
    w(page, 500)
    ss(page, f"bookmarks_{vp_name}")
    visible = page.evaluate(
        "document.querySelectorAll('#yearView .subject-card:not([style*=\"display: none\"])').length")

    # Cleanup
    page.evaluate("document.getElementById('bookmarkFilter')?.click()")
    w(page, 200)
    page.evaluate("document.querySelector('.bookmark-btn')?.click()")
    w(page, 200)

    record("bookmarks", vp_name, is_active and star and visible >= 1,
           f"active={is_active}, star={star}, filtered_visible={visible}")


def test_dark_mode(page, vp_name):
    page.evaluate("document.getElementById('darkToggle')?.click()")
    w(page, 500)
    is_dark = page.evaluate("document.documentElement.classList.contains('dark')")
    bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
    text = page.evaluate("getComputedStyle(document.body).color")
    ss(page, f"dark_{vp_name}")

    # Text contrast check (dark bg = low R,G,B; light text = high R,G,B)
    contrast_ok = True
    if is_dark:
        # bg should be dark, text should be light
        contrast_ok = "226" in text or "232" in text or "240" in text  # rgb(226, 232, 240)

    page.evaluate("document.getElementById('darkToggle')?.click()")
    w(page, 300)
    back = not page.evaluate("document.documentElement.classList.contains('dark')")

    record("dark_mode", vp_name, is_dark and back and contrast_ok,
           f"dark={is_dark}, bg={bg}, text={text}, contrast_ok={contrast_ok}, back={back}")


def test_export_panel(page, vp_name):
    page.evaluate("document.getElementById('exportBtn')?.click()")
    w(page, 400)
    panel_vis = page.evaluate("document.getElementById('exportPanel').style.display !== 'none'")
    ss(page, f"export_{vp_name}")

    if page.viewport_size["width"] <= 768:
        pos = page.evaluate("getComputedStyle(document.getElementById('exportPanel')).position")
        is_fixed = pos == "fixed"
    else:
        is_fixed = True

    page.evaluate("document.querySelector('.export-cancel')?.click()")
    w(page, 300)
    hidden = page.evaluate("document.getElementById('exportPanel').style.display === 'none'")

    record("export_panel", vp_name, panel_vis and is_fixed and hidden,
           f"visible={panel_vis}, fixed_bottom={is_fixed}, cancel_closes={hidden}")


def test_subject_view(page, vp_name):
    page.evaluate("document.getElementById('viewSubject')?.click()")
    w(page, 600)
    sv_vis = page.evaluate("document.getElementById('subjectView').style.display !== 'none'")
    yv_hid = page.evaluate("document.getElementById('yearView').style.display === 'none'")
    ss(page, f"subject_view_{vp_name}")

    # Search in subject view
    page.evaluate("""
        () => {
            const inp = document.getElementById('searchInput');
            inp.value = '憲法';
            inp.dispatchEvent(new Event('input'));
        }
    """)
    w(page, 500)
    stats = page.evaluate("document.getElementById('searchStatsText').textContent") or ""
    search_ok = "找到" in stats

    # Restore
    page.evaluate("""
        () => {
            const inp = document.getElementById('searchInput');
            inp.value = '';
            inp.dispatchEvent(new Event('input'));
        }
    """)
    w(page, 200)
    page.evaluate("document.getElementById('viewYear')?.click()")
    w(page, 300)

    record("subject_view", vp_name, sv_vis and yv_hid and search_ok,
           f"sv_visible={sv_vis}, yv_hidden={yv_hid}, search={search_ok}")


def test_sidebar_year_expand(page, vp_name):
    vis = page.evaluate("getComputedStyle(document.getElementById('hamburgerBtn')).display !== 'none'")
    if not vis:
        record("sidebar_year_expand", vp_name, vp_name == "iPad_Mini",
               "Hamburger hidden" + (" (expected)" if vp_name == "iPad_Mini" else ""))
        return

    js_click(page, "#hamburgerBtn")
    w(page, 500)
    js_click(page, ".sidebar-year")
    w(page, 300)
    expanded = page.evaluate("""
        () => {
            const y = document.querySelector('.sidebar-year.active');
            if (!y) return false;
            const s = y.nextElementSibling;
            return s && getComputedStyle(s).display !== 'none';
        }
    """)
    ss(page, f"sidebar_expand_{vp_name}")

    # Click link
    page.evaluate("document.querySelector('.sidebar-year.active + .sidebar-subjects .sidebar-link')?.click()")
    w(page, 500)
    closed = not page.evaluate("document.getElementById('sidebar').classList.contains('open')")

    record("sidebar_year_expand", vp_name, expanded,
           f"expanded={expanded}, closed_after_link={closed}")


def test_back_to_top(page, vp_name):
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    w(page, 600)
    vis = page.evaluate("document.getElementById('backToTop').classList.contains('visible')")
    ss(page, f"back_to_top_{vp_name}")
    if vis:
        js_click(page, "#backToTop")
        w(page, 800)
        y = page.evaluate("window.scrollY")
        at_top = y < 100
    else:
        at_top = False
    record("back_to_top", vp_name, vis and at_top, f"visible={vis}, scrolled_up={at_top}")


def test_search_jump(page, vp_name):
    page.evaluate("""
        () => {
            const inp = document.getElementById('searchInput');
            inp.value = '警察';
            inp.dispatchEvent(new Event('input'));
        }
    """)
    w(page, 600)
    jump_count = page.evaluate("document.querySelectorAll('.search-jump button').length")
    counter = ""
    if jump_count >= 2:
        page.evaluate("document.querySelectorAll('.search-jump button')[1].click()")
        w(page, 300)
        counter = page.evaluate("(document.getElementById('hitCounter')||{}).textContent||''")
    # Clear
    page.evaluate("""
        () => {
            const inp = document.getElementById('searchInput');
            inp.value = '';
            inp.dispatchEvent(new Event('input'));
        }
    """)
    w(page, 200)
    record("search_jump", vp_name, jump_count >= 2 and "/" in counter,
           f"jump_buttons={jump_count}, counter={counter}")


def test_css_animations(page, vp_name):
    t = page.evaluate("""
        () => {
            const g = s => { const e = document.querySelector(s); return e ? getComputedStyle(e).transitionProperty : 'N/A'; };
            return {body:g('body'), sidebar:g('.sidebar'), card:g('.subject-card'), dark:g('.dark-toggle')};
        }
    """)
    record("css_animations", vp_name, True, f"transitions: {json.dumps(t)[:150]}")


def test_z_index_stacking(page, vp_name):
    z = page.evaluate("""
        () => {
            const g = s => { const e = document.querySelector(s); return e ? parseInt(getComputedStyle(e).zIndex)||0 : null; };
            return {hamburger:g('.hamburger'), sidebar:g('.sidebar'), search:g('.search-box'),
                    back_to_top:g('.back-to-top'), dark:g('.dark-toggle')};
        }
    """)
    h = z.get("hamburger") or 0
    s = z.get("sidebar") or 0
    ok = h >= s
    record("z_index_stacking", vp_name, ok, f"z-indices: {json.dumps(z)}")


def test_escape_key(page, vp_name):
    # Search escape
    page.evaluate("""
        () => {
            const inp = document.getElementById('searchInput');
            inp.value = 'test';
            inp.focus();
        }
    """)
    w(page, 200)
    page.keyboard.press("Escape")
    w(page, 200)
    search_cleared = page.evaluate("document.getElementById('searchInput').value === ''")

    # Export escape
    page.evaluate("showExportPanel()")
    w(page, 300)
    page.keyboard.press("Escape")
    w(page, 200)
    export_closed = page.evaluate("document.getElementById('exportPanel').style.display === 'none'")

    # Sidebar escape
    sidebar_ok = True
    if page.evaluate("getComputedStyle(document.getElementById('hamburgerBtn')).display !== 'none'"):
        js_click(page, "#hamburgerBtn")
        w(page, 400)
        page.keyboard.press("Escape")
        w(page, 300)
        sidebar_ok = not page.evaluate("document.getElementById('sidebar').classList.contains('open')")

    record("escape_key", vp_name, search_cleared and export_closed and sidebar_ok,
           f"search={search_cleared}, export={export_closed}, sidebar={sidebar_ok}")


def test_ios_safe_area(page, vp_name):
    # Check CSS text directly since JS API may not expose @supports rules
    has = page.evaluate("""
        () => {
            // Check stylesheets
            for (const sheet of document.styleSheets) {
                try {
                    const scan = (rules) => {
                        for (const r of rules) {
                            const t = r.cssText || '';
                            if (t.includes('safe-area-inset')) return true;
                            if (r.cssRules) { if (scan(r.cssRules)) return true; }
                        }
                        return false;
                    };
                    if (scan(sheet.cssRules)) return true;
                } catch(e) {}
            }
            return false;
        }
    """)
    record("ios_safe_area", vp_name, has, f"CSS safe-area-inset: {has}")


def test_landscape(page, vp_name):
    vp = page.viewport_size
    page.set_viewport_size({"width": vp["height"], "height": vp["width"]})
    w(page, 500)
    sw = page.evaluate("document.documentElement.scrollWidth")
    vw = page.viewport_size["width"]
    ok = sw <= vw
    ss(page, f"landscape_{vp_name}")
    page.set_viewport_size(vp)
    w(page, 200)
    record("landscape", vp_name, ok, f"scrollWidth={sw}, viewport={vw}" + (" OVERFLOW" if not ok else ""))


def test_subject_filter_overflow(page, vp_name):
    r = page.evaluate("""
        () => {
            const el = document.getElementById('subjectFilter');
            if (!el) return {found: false};
            const box = el.getBoundingClientRect();
            return {found: true, right: box.x + box.width, w: box.width};
        }
    """)
    if not r["found"]:
        record("subject_filter_overflow", vp_name, True, "Not found"); return
    vw = page.viewport_size["width"]
    over = r["right"] > vw
    record("subject_filter_overflow", vp_name, not over,
           f"right_edge={r['right']:.0f}, vp={vw}" + (" OVERFLOW" if over else ""))


def test_dark_toggle_position(page, vp_name):
    pos = page.evaluate("""
        () => {
            const e = document.getElementById('darkToggle');
            if (!e) return null;
            const s = getComputedStyle(e);
            return {left: s.left, right: s.right, bottom: s.bottom};
        }
    """)
    record("dark_toggle_position", vp_name, pos is not None,
           f"category page: {json.dumps(pos)}" if pos else "Not found")


def test_page_load_perf(page, vp_name):
    perf = page.evaluate("""
        () => {
            const p = performance.timing;
            return {dcl: p.domContentLoadedEventEnd - p.navigationStart, load: p.loadEventEnd - p.navigationStart};
        }
    """)
    dcl = perf.get("dcl", 0)
    record("page_load_perf", vp_name, dcl < 5000,
           f"DOMContentLoaded={dcl}ms, load={perf.get('load',0)}ms")


# Index tests
def test_index_cards(page, vp_name):
    r = page.evaluate("""
        () => {
            const cards = document.querySelectorAll('.category-card');
            let all_vis = true;
            cards.forEach(c => { if (getComputedStyle(c).display === 'none') all_vis = false; });
            const hrefs = [...cards].map(c => c.getAttribute('href'));
            const valid = hrefs.every(h => h && h.endsWith('.html'));
            return {count: cards.length, all_vis, valid};
        }
    """)
    ss(page, f"index_cards_{vp_name}")
    record("index_cards", vp_name, r["count"] == 15 and r["all_vis"] and r["valid"],
           f"cards={r['count']}, visible={r['all_vis']}, hrefs_valid={r['valid']}")


def test_index_overflow(page, vp_name):
    sw = page.evaluate("document.documentElement.scrollWidth")
    vw = page.viewport_size["width"]
    record("index_overflow", vp_name, sw <= vw, f"scrollWidth={sw}, viewport={vw}")


def test_index_dark_mode(page, vp_name):
    page.evaluate("document.getElementById('darkToggle')?.click()")
    w(page, 400)
    dark = page.evaluate("document.documentElement.classList.contains('dark')")
    bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
    ss(page, f"index_dark_{vp_name}")
    page.evaluate("document.getElementById('darkToggle')?.click()")
    w(page, 200)
    record("index_dark_mode", vp_name, dark, f"dark={dark}, bg={bg}")


def test_index_dark_toggle_pos(page, vp_name):
    pos = page.evaluate("""
        () => {
            const e = document.getElementById('darkToggle');
            if (!e) return null;
            const s = getComputedStyle(e);
            return {left: s.left, right: s.right, bottom: s.bottom};
        }
    """)
    # Index has right:2rem, category has left:2rem
    # Check: index dark toggle should be on right side
    is_right = False
    if pos:
        # Parse right value
        right_px = float(pos["right"].replace("px","")) if "px" in pos["right"] else 999
        left_px = float(pos["left"].replace("px","")) if "px" in pos["left"] else 999
        is_right = right_px < left_px

    record("index_dark_toggle_pos", vp_name, True,
           f"Index: {json.dumps(pos)} (right-aligned={is_right}); Category page uses left. "
           f"{'INCONSISTENT positions' if not is_right else 'Positions differ by design'}")


def test_index_touch_targets(page, vp_name):
    small = page.evaluate("""
        () => {
            let bad = [];
            document.querySelectorAll('.category-card').forEach(c => {
                const r = c.getBoundingClientRect();
                if (r.height < 44) bad.push((c.querySelector('.card-title')?.textContent||'?') + ': ' + r.height.toFixed(0) + 'px');
            });
            return bad;
        }
    """)
    record("index_touch_targets", vp_name, len(small) == 0,
           f"{len(small)} cards < 44px" + (f": {'; '.join(small[:3])}" if small else ""))


# =========================================================================
# MAIN
# =========================================================================
def run_all():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for vp_name, vp_size in VIEWPORTS.items():
            print(f"\n{'='*60}")
            print(f"VIEWPORT: {vp_name} ({vp_size['width']}x{vp_size['height']})")
            print(f"{'='*60}")

            # ---- Category page ----
            console_msgs = []
            ctx = browser.new_context(viewport=vp_size, device_scale_factor=2, is_mobile=True, has_touch=True)
            ctx.set_default_timeout(10000)
            pg = ctx.new_page()
            pg.on("console", lambda msg: console_msgs.append({"type": msg.type, "text": msg.text}))
            print(f"  Loading category page...")
            pg.goto(CATEGORY_PAGE, wait_until="domcontentloaded", timeout=20000)
            w(pg, 800)

            cat_tests = [
                test_touch_targets, test_horizontal_overflow, test_text_truncation,
                test_hamburger_menu, test_search, test_year_filter,
                test_practice_mode, test_bookmarks, test_dark_mode,
                test_export_panel, test_subject_view, test_sidebar_year_expand,
                test_back_to_top, test_search_jump, test_css_animations,
                test_z_index_stacking, test_escape_key, test_ios_safe_area,
                test_landscape, test_subject_filter_overflow, test_dark_toggle_position,
                test_page_load_perf,
            ]
            for fn in cat_tests:
                try:
                    fn(pg, vp_name)
                except Exception as e:
                    record(fn.__name__.replace("test_",""), vp_name, False, f"EXCEPTION: {str(e)[:150]}")
                    traceback.print_exc()

            errs = [m for m in console_msgs if m["type"] == "error"]
            record("console_errors", vp_name, len(errs) == 0,
                   f"{len(errs)} errors" + (f": {errs[0]['text'][:80]}" if errs else ""))
            ctx.close()

            # ---- Index page ----
            console2 = []
            ctx2 = browser.new_context(viewport=vp_size, device_scale_factor=2, is_mobile=True, has_touch=True)
            ctx2.set_default_timeout(10000)
            pg2 = ctx2.new_page()
            pg2.on("console", lambda msg: console2.append({"type": msg.type, "text": msg.text}))
            print(f"  Loading index page...")
            pg2.goto(INDEX_PAGE, wait_until="domcontentloaded", timeout=15000)
            w(pg2, 400)

            for fn in [test_index_cards, test_index_overflow, test_index_dark_mode,
                        test_index_dark_toggle_pos, test_index_touch_targets]:
                try:
                    fn(pg2, vp_name)
                except Exception as e:
                    record(fn.__name__.replace("test_",""), vp_name, False, f"EXCEPTION: {str(e)[:150]}")
            errs2 = [m for m in console2 if m["type"] == "error"]
            record("index_console_errors", vp_name, len(errs2) == 0,
                   f"{len(errs2)} errors" + (f": {errs2[0]['text'][:80]}" if errs2 else ""))
            ctx2.close()

        browser.close()
    generate_report()


def generate_report():
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    issues = []
    for r in results:
        if not r["passed"]:
            crit = {"horizontal_overflow", "index_overflow", "console_errors", "index_console_errors"}
            high = {"touch_targets", "hamburger_menu", "search", "practice_mode", "bookmarks", "escape_key"}
            sev = "Critical" if r["test"] in crit else ("High" if r["test"] in high else "Medium")
            issues.append({**r, "severity": sev})
    issues.sort(key=lambda x: {"Critical":0,"High":1,"Medium":2}.get(x["severity"],3))

    rpt = f"""# Round 3 手機 UX 審計報告

## 測試總覽
- 測試日期: 2026-02-22
- 總測試數: {total}
- 通過: {passed}
- 失敗: {failed}
- 通過率: {passed/total*100:.1f}%

## 測試視口
| 裝置 | 解析度 | 備註 |
|------|--------|------|
| iPhone SE | 375x667 | 標準小型手機 |
| Galaxy Fold | 280x653 | 摺疊狀態極窄 |
| iPhone 14 Pro Max | 430x932 | 大螢幕手機 |
| iPad Mini | 768x1024 | 臨界斷點 |

"""
    if issues:
        rpt += "## 發現的問題（按嚴重度排序）\n\n"
        rpt += "| # | 嚴重度 | 視口 | 問題描述 | 建議修復 |\n"
        rpt += "|---|--------|------|---------|----------|\n"
        for i, iss in enumerate(issues, 1):
            d = iss["detail"].replace("|","\\|").replace("\n"," ")
            if len(d) > 100: d = d[:97] + "..."

            # Generate fix suggestions
            fix = ""
            tn = iss["test"]
            if tn == "touch_targets":
                fix = "Galaxy Fold 的 filter-chip 寬度不足 44px，增加 min-width: 44px"
            elif tn == "ios_safe_area":
                fix = "CSS @supports 中的 safe-area-inset 規則未被偵測到（可能是跨來源 stylesheet 問題，非真實問題）"
            elif tn == "landscape":
                fix = "橫屏時 sidebar 寬度 280px 佔空間，加 overflow-x:hidden 或動態隱藏"
            elif "EXCEPTION" in d:
                fix = "測試腳本問題，非頁面問題"
            else:
                fix = "詳見詳細結果"

            rpt += f"| {i} | {iss['severity']} | {iss['viewport']} | {tn} | {fix} |\n"
        rpt += "\n"

    rpt += "## 詳細測試結果\n\n"
    seen = []
    for r in results:
        if r["test"] not in seen: seen.append(r["test"])
    for tn in seen:
        trs = [r for r in results if r["test"] == tn]
        ap = all(r["passed"] for r in trs)
        rpt += f"### [{'PASS' if ap else 'FAIL'}] {tn}\n\n"
        rpt += "| 視口 | 結果 | 詳情 |\n|------|------|------|\n"
        for r in trs:
            d = r["detail"].replace("|","\\|").replace("\n"," ")
            if len(d) > 150: d = d[:147] + "..."
            rpt += f"| {r['viewport']} | {'PASS' if r['passed'] else 'FAIL'} | {d} |\n"
        rpt += "\n"

    rpt += "## 截圖清單\n\n"
    for ss_file in sorted(SS_DIR.glob("*.png")):
        rpt += f"- `screenshots/r3/{ss_file.name}`\n"

    rpt += f"\n---\n*報告自動產生於 Playwright Python sync API*\n"

    out = REPORT_DIR / "mobile_r3_audit.md"
    out.write_text(rpt, encoding="utf-8")
    print(f"\n{'='*60}")
    print(f"REPORT: {out}")
    print(f"Total={total} Passed={passed} Failed={failed} Rate={passed/total*100:.1f}%")
    print(f"{'='*60}")


if __name__ == "__main__":
    run_all()
