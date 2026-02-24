#!/usr/bin/env python3
"""
Part B: Cross-validation regression script for Round 1+2 fixes.
Verifies that all previously fixed items remain intact.
"""
import re
import os
import sys

BASE = r"C:\Users\User\Desktop\考古題下載\考古題網站"
CSS_PATH = os.path.join(BASE, "css", "style.css")
SAMPLE_HTML = os.path.join(BASE, "行政警察學系", "行政警察學系考古題總覽.html")

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    mark = "\u2713" if condition else "\u2717"
    print(f"  [{status}] {mark} {name}" + (f"  ({detail})" if detail else ""))
    return condition

def main():
    # Read files
    with open(CSS_PATH, "r", encoding="utf-8") as f:
        css = f.read()
    with open(SAMPLE_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    print("=" * 60)
    print("  Part B: Cross-validation of Round 1+2 fixes")
    print("=" * 60)
    print()

    # ====== 1. Touch targets ======
    print("--- 1. Touch targets (min-height) ---")
    check("sidebar-home min-height: 44px",
          "sidebar-home" in css and re.search(r'\.sidebar-home\s*\{[^}]*min-height:\s*44px', css) is not None)
    check("sidebar-year min-height: 44px",
          re.search(r'\.sidebar-year\s*\{[^}]*min-height:\s*44px', css) is not None)
    check("sidebar-link min-height: 40px",
          re.search(r'\.sidebar-link\s*\{[^}]*min-height:\s*40px', css) is not None)
    check("search-jump button min-height: 44px",
          re.search(r'\.search-jump\s+button\s*\{[^}]*min-height:\s*44px', css) is not None)
    check("sidebar-reopen 44px",
          re.search(r'\.sidebar-reopen\s*\{[^}]*height:\s*44px', css) is not None)
    check("sidebar-toggle 36px",
          re.search(r'\.sidebar-toggle\s*\{[^}]*height:\s*36px', css) is not None)
    print()

    # ====== 2. ARIA attributes ======
    print("--- 2. ARIA attributes ---")
    check("subject-header has role='button'",
          'class="subject-header" role="button"' in html)
    check("subject-header has tabindex='0'",
          'role="button" tabindex="0"' in html)
    check("subject-header has aria-expanded='false'",
          'tabindex="0" aria-expanded="false"' in html)
    # Check export panel in another HTML that has it
    export_html_path = os.path.join(BASE, "刑事警察學系", "刑事警察學系考古題總覽.html")
    with open(export_html_path, "r", encoding="utf-8") as f:
        export_html = f.read()
    check("export panel has role='dialog'",
          'role="dialog"' in export_html)
    check("export panel has aria-label",
          'role="dialog" aria-label=' in export_html)
    print()

    # ====== 3. Print CSS ======
    print("--- 3. Print CSS ---")
    # Use simple string search - the CSS has @media print blocks with these rules
    check("@media print contains body { background: white",
          "@media print" in css and "background: white" in css)
    check("@media print contains .subject-card { overflow: visible",
          "overflow: visible" in css and ".subject-card" in css)
    print()

    # ====== 4. Dark mode meta-tag color ======
    print("--- 4. Dark mode meta-tag color ---")
    # html.dark .meta-tag should have color: #cbd5e0 (not #a0aec0)
    dark_meta_match = re.search(r'html\.dark\s+\.meta-tag\s*\{[^}]*color:\s*([^;}\s]+)', css)
    if dark_meta_match:
        color = dark_meta_match.group(1).strip()
        check("html.dark .meta-tag color is #cbd5e0",
              color == "#cbd5e0",
              f"actual: {color}")
    else:
        check("html.dark .meta-tag rule exists", False, "rule not found")
    print()

    # ====== 5. Google Fonts escaping ======
    print("--- 5. Google Fonts escaping ---")
    check("&amp;display=swap present",
          "&amp;display=swap" in html)
    check("&display=swap NOT present (raw unescaped)",
          "&display=swap" not in html or "&amp;display=swap" in html)
    # More precise check: ensure no raw &display= without &amp;
    raw_unescaped = re.findall(r'&display=swap', html)
    amp_escaped = re.findall(r'&amp;display=swap', html)
    check("All occurrences properly escaped",
          len(raw_unescaped) == 0,
          f"escaped={len(amp_escaped)}, raw={len(raw_unescaped)}")
    print()

    # ====== 6. focus-visible ======
    print("--- 6. focus-visible styles ---")
    check("export-option:focus-visible exists",
          "export-option:focus-visible" in css)
    check("export-cancel:focus-visible exists",
          "export-cancel:focus-visible" in css)
    check("sidebar-home:focus-visible exists",
          "sidebar-home:focus-visible" in css)
    print()

    # ====== 7. Dark mode export panel ======
    print("--- 7. Dark mode export panel ---")
    check("html.dark .export-panel exists",
          "html.dark .export-panel" in css)
    check("html.dark .export-option exists",
          "html.dark .export-option" in css)
    check("html.dark .export-cancel exists",
          "html.dark .export-cancel" in css)
    print()

    # ====== 8. Galaxy Fold support ======
    print("--- 8. Galaxy Fold support (max-width: 320px) ---")
    check("@media (max-width: 320px) exists",
          "@media (max-width: 320px)" in css)
    # Check it has meaningful content
    fold_match = re.search(r'@media\s*\(max-width:\s*320px\)\s*\{(.+?)(?=\n/\*|\n@media|\Z)', css, re.DOTALL)
    if fold_match:
        fold_content = fold_match.group(1)
        check("Galaxy Fold has .page-title rule",
              ".page-title" in fold_content)
        check("Galaxy Fold has .toolbar-btn rule",
              ".toolbar-btn" in fold_content)
    else:
        check("Galaxy Fold media query has content", False, "no content found")
    print()

    # ====== Summary ======
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    total = len(results)

    print("=" * 60)
    print(f"  Part B Summary: {passed}/{total} PASS, {failed}/{total} FAIL")
    if failed == 0:
        print("  ALL ROUND 1+2 FIXES VERIFIED!")
    else:
        print("  FAILED items:")
        for name, status, detail in results:
            if status == "FAIL":
                print(f"    - {name}: {detail}")
    print("=" * 60)

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
