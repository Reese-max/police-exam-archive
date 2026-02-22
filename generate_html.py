# -*- coding: utf-8 -*-
"""
HTML 生成器 — 從 JSON 題目資料生成靜態 HTML 考古題網站
以現有「資管系考古題總覽.html」為模板，抽出共用 CSS/JS，
為每個類科生成獨立的 HTML 頁面。

用法:
  python generate_html.py                              # 從 考古題庫/ 生成到 考古題網站/
  python generate_html.py --input 考古題庫 --output 考古題網站
  python generate_html.py --category 行政警察          # 只生成一個類科
"""

import os
import re
import json
import argparse
import hashlib
import html as html_module
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ===== 類科定義 =====
CATEGORIES_ORDER = [
    '行政警察', '外事警察', '刑事警察', '公共安全',
    '犯罪防治預防組', '犯罪防治矯治組',
    '消防警察', '交通警察交通組', '交通警察電訊組', '資訊管理',
    '鑑識科學', '國境警察', '水上警察', '警察法制', '行政管理',
]

CATEGORIES_INFO = {
    '行政警察': {'code': 501, 'icon': '&#128110;', 'color': '#2563eb'},
    '外事警察': {'code': 502, 'icon': '&#127760;', 'color': '#0d9488'},
    '刑事警察': {'code': 503, 'icon': '&#128269;', 'color': '#d97706'},
    '公共安全': {'code': 504, 'icon': '&#128737;', 'color': '#7c3aed'},
    '犯罪防治預防組': {'code': 505, 'icon': '&#129309;', 'color': '#e11d48'},
    '犯罪防治矯治組': {'code': '505b', 'icon': '&#128274;', 'color': '#ea580c'},
    '消防警察': {'code': 506, 'icon': '&#128658;', 'color': '#dc2626'},
    '交通警察交通組': {'code': 507, 'icon': '&#128678;', 'color': '#475569'},
    '交通警察電訊組': {'code': '507b', 'icon': '&#128225;', 'color': '#0284c7'},
    '資訊管理': {'code': 508, 'icon': '&#128187;', 'color': '#2563eb'},
    '鑑識科學': {'code': 509, 'icon': '&#128300;', 'color': '#059669'},
    '國境警察': {'code': 510, 'icon': '&#128706;', 'color': '#7c3aed'},
    '水上警察': {'code': 511, 'icon': '&#9875;', 'color': '#0369a1'},
    '警察法制': {'code': 512, 'icon': '&#9878;', 'color': '#b45309'},
    '行政管理': {'code': 513, 'icon': '&#128203;', 'color': '#6366f1'},
}

# 圖標對照（純文字版，用於 Python 端）
CATEGORIES_EMOJI = {
    '行政警察': '👮', '外事警察': '🌐', '刑事警察': '🔍',
    '公共安全': '🛡', '犯罪防治預防組': '🤝', '犯罪防治矯治組': '🔒',
    '消防警察': '🚒',
    '交通警察交通組': '🚦', '交通警察電訊組': '📡',
    '資訊管理': '💻', '鑑識科學': '🔬',
    '國境警察': '🛂', '水上警察': '⚓', '警察法制': '⚖',
    '行政管理': '📋',
}


def normalize_parens(text):
    """統一全形括號為半形括號"""
    return str(text).replace('（', '(').replace('）', ')')

def escape_html(text):
    """HTML 跳脫"""
    return html_module.escape(str(text))


def make_card_id(year, subj_name):
    """生成唯一且穩定的卡片 ID"""
    cleaned = re.sub(r'[^a-zA-Z0-9_]', '', subj_name.replace(' ', '_'))[:20]
    if not cleaned:
        cleaned = hashlib.md5(subj_name.encode()).hexdigest()[:8]
    return f"y{year}-{cleaned}"


def _read_template(name):
    """讀取內嵌模板"""
    templates_dir = Path(__file__).parent / 'templates'
    path = templates_dir / name
    if path.exists():
        return path.read_text(encoding='utf-8')
    return None


def generate_shared_css():
    """生成共用 CSS（從現有 HTML 模板提取）"""
    cached = _read_template('style.css')
    if cached:
        return cached

    # 內嵌完整 CSS（精簡版，複用資管系模板風格）
    return """:root {
  --primary: #2563eb;
  --primary-light: #3b82f6;
  --accent: #6366f1;
  --bg: #f8fafc;
  --card-bg: #ffffff;
  --border: #e2e8f0;
  --text: #1e293b;
  --text-light: #64748b;
  --text-muted: #94a3b8;
  --success: #10b981;
  --warning: #f59e0b;
  --danger: #ef4444;
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -2px rgba(0,0,0,0.05);
  --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.08), 0 4px 6px -4px rgba(0,0,0,0.05);
  --radius: 12px;
  --sidebar-w: 280px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
a, button, input, select, [role="button"] { touch-action: manipulation; -webkit-tap-highlight-color: transparent; }
html { scroll-behavior: smooth; scroll-padding-top: 140px; }
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; } }
body { font-family: "Noto Sans TC", "Microsoft JhengHei", -apple-system, sans-serif; background: var(--bg); color: var(--text); line-height: 1.7; overflow-x: hidden; -webkit-font-smoothing: antialiased; }
/* === Sidebar === */
.sidebar { position: fixed; top: 0; left: 0; width: var(--sidebar-w); height: 100vh; background: #0f172a; color: #fff; overflow-y: auto; z-index: 100; padding: 1.5rem 0; }
.sidebar::-webkit-scrollbar { width: 6px; }
.sidebar::-webkit-scrollbar-track { background: transparent; }
.sidebar::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 3px; }
.sidebar::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.25); }
.sidebar-title { font-size: 1.1rem; font-weight: 700; padding: 0 1.25rem 1rem; border-bottom: 1px solid rgba(255,255,255,0.1); margin-bottom: 0.75rem; display: flex; align-items: center; justify-content: space-between; letter-spacing: 0.02em; }
.sidebar-home { padding: 0.5rem 1.25rem; font-size: 0.85rem; color: rgba(255,255,255,0.6); text-decoration: none; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); border-bottom: 1px solid rgba(255,255,255,0.06); margin-bottom: 0.5rem; min-height: 44px; display: flex; align-items: center; }
.sidebar-home:hover { color: #fff; background: rgba(255,255,255,0.08); }
.sidebar-year { padding: 0.4rem 1.25rem; font-size: 0.95rem; font-weight: 600; color: rgba(255,255,255,0.6); cursor: pointer; user-select: none; min-height: 44px; display: flex; align-items: center; border-left: 3px solid transparent; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); }
.sidebar-year:hover { color: #fff; background: rgba(255,255,255,0.06); }
.sidebar-year.active { color: #fff; border-left-color: var(--accent); }
.sidebar-subjects { display: none; padding: 0.25rem 0; }
.sidebar-year.active + .sidebar-subjects { display: block; }
.sidebar-link { display: flex; align-items: center; padding: 0.3rem 1.25rem 0.3rem 2rem; font-size: 0.82rem; color: rgba(255,255,255,0.5); text-decoration: none; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-height: 44px; }
.sidebar-link:hover { color: #fff; background: rgba(255,255,255,0.08); padding-left: 2.25rem; }
.sidebar-toggle { width: 36px; height: 36px; border-radius: 50%; background: rgba(255,255,255,0.1); color: rgba(255,255,255,0.6); border: none; cursor: pointer; font-size: 0.75rem; display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); }
.sidebar-toggle:hover { background: rgba(255,255,255,0.2); color: #fff; }
body.sidebar-collapsed .sidebar { transform: translateX(-100%); }
body.sidebar-collapsed .main { margin-left: 0; }
.sidebar-reopen { display: none; position: fixed; top: 1rem; left: 0.75rem; z-index: 101; width: 44px; height: 44px; border-radius: var(--radius); background: var(--primary); color: #fff; border: none; cursor: pointer; font-size: 0.85rem; align-items: center; justify-content: center; box-shadow: var(--shadow-md); transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); }
.sidebar-reopen:hover { background: var(--primary-light); transform: scale(1.05); }
body.sidebar-collapsed .sidebar-reopen { display: flex; }
/* === Main === */
.main { margin-left: var(--sidebar-w); padding: 2rem 2.5rem; max-width: 960px; transition: margin-left 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
.page-title { font-size: 1.8rem; font-weight: 800; color: var(--primary); margin-bottom: 0.5rem; letter-spacing: -0.01em; }
.page-subtitle { color: var(--text-light); font-size: 0.95rem; margin-bottom: 2rem; }
.year-section { margin-bottom: 3rem; }
.year-heading { font-size: 1.4rem; font-weight: 700; color: var(--primary); border-bottom: 3px solid var(--accent); padding-bottom: 0.5rem; margin-bottom: 1.5rem; }
/* === Subject Card === */
.subject-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 16px; margin-bottom: 1.5rem; overflow: hidden; box-shadow: var(--shadow-sm); transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); }
.subject-card:hover { box-shadow: var(--shadow-md); transform: translateY(-2px); }
.subject-header { background: linear-gradient(135deg, var(--primary), var(--accent)); color: #fff; padding: 1rem 1.5rem; cursor: pointer; user-select: none; display: flex; justify-content: space-between; align-items: center; }
.subject-header h3 { font-size: 1rem; font-weight: 600; flex: 1; min-width: 0; }
.subject-toggle { font-size: 1.2rem; transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1); flex-shrink: 0; margin-left: 0.75rem; }
.subject-card.open .subject-toggle { transform: rotate(180deg); }
.subject-body { display: none; padding: 1.5rem; }
.subject-card.open .subject-body { display: block; animation: slideDown 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
@keyframes slideDown { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }
/* === Exam Content === */
.exam-meta-bar { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1rem; }
.meta-tag { font-size: 0.78rem; padding: 0.2rem 0.6rem; border-radius: 6px; background: #f1f5f9; color: var(--text-light); }
.exam-content-v2 { padding: 0.5rem 0; }
.exam-metadata { background: #f8fafc; border: 1px solid var(--border); border-radius: 10px; padding: 0.75rem 1rem; margin-bottom: 1rem; font-size: 0.82rem; color: var(--text-light); line-height: 1.6; }
.exam-note { font-size: 0.82rem; color: var(--text-light); padding: 0.2rem 0 0.2rem 1rem; border-left: 3px solid var(--border); margin-bottom: 0.25rem; }
.reading-passage { font-size: 0.88rem; line-height: 1.8; color: var(--text); background: #f8fafc; border-left: 3px solid var(--primary); padding: 0.75rem 1rem; margin: 0.75rem 0 0.25rem; border-radius: 0 8px 8px 0; overflow-wrap: break-word; word-break: break-word; }
.exam-section-marker { font-size: 0.95rem; font-weight: 700; color: var(--primary); padding: 0.75rem 0 0.4rem; margin-top: 0.5rem; border-top: 1px solid var(--border); }
.essay-question { font-size: 0.92rem; line-height: 1.85; padding: 0.75rem 0 0.5rem; border-bottom: 1px dashed #e2e8f0; margin-bottom: 0.5rem; text-indent: -1.5em; padding-left: 1.5em; overflow-wrap: break-word; word-break: break-word; }
.mc-question { padding: 0.6rem 0 0.25rem; border-top: 1px solid #f1f5f9; margin-top: 0.4rem; display: flex; gap: 0.5rem; align-items: baseline; overflow-wrap: break-word; word-break: break-word; }
.mc-question:first-child, .exam-section-marker + .mc-question, .exam-note + .mc-question { border-top: none; margin-top: 0; }
.q-number { display: inline-flex; align-items: center; justify-content: center; min-width: 28px; height: 28px; border-radius: 50%; background: var(--primary); color: #fff; font-size: 0.78rem; font-weight: 700; flex-shrink: 0; }
.q-text { font-size: 0.92rem; line-height: 1.75; overflow-wrap: break-word; word-break: break-word; }
.mc-option { display: flex; gap: 0.4rem; padding: 0.2rem 0 0.2rem 2.2rem; align-items: baseline; }
.opt-label { font-weight: 700; color: var(--accent); flex-shrink: 0; font-size: 0.88rem; }
.opt-text { font-size: 0.9rem; line-height: 1.7; overflow-wrap: break-word; word-break: break-word; }
/* === Search === */
.search-box { position: sticky; top: 0; background: var(--bg); padding: 1rem 0; z-index: 50; margin-bottom: 1rem; }
.search-input { width: 100%; padding: 0.75rem 1rem 0.75rem 2.75rem; border: 2px solid var(--border); border-radius: var(--radius); font-size: 1rem; font-family: inherit; outline: none; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cline x1='21' y1='21' x2='16.65' y2='16.65'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: 0.85rem center; background-size: 18px; }
.search-input:focus { border-color: var(--primary); box-shadow: 0 0 0 4px rgba(37,99,235,0.12); }
.search-filters { display: flex; gap: 0.4rem; flex-wrap: wrap; margin-top: 0.5rem; }
.filter-chip { padding: 0.5rem 0.75rem; border: 1.5px solid var(--border); border-radius: 999px; background: var(--card-bg); color: var(--text-light); font-size: 0.78rem; min-height: 44px; display: inline-flex; align-items: center; font-family: inherit; cursor: pointer; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); user-select: none; }
.filter-chip:hover { border-color: var(--primary); color: var(--primary); }
.filter-chip.active { background: var(--primary); color: #fff; border-color: var(--primary); }
.search-stats { font-size: 0.82rem; color: var(--text-light); margin-top: 0.4rem; }
/* === Stats Bar === */
.stats-bar { display: flex; gap: 1rem; padding: 1rem 1.5rem; background: var(--card-bg); border: 1px solid var(--border); border-radius: var(--radius); margin-bottom: 2rem; box-shadow: var(--shadow-sm); }
.stat-item { text-align: center; background: var(--card-bg); border-radius: 10px; padding: 0.75rem 1.25rem; flex: 1; }
.stat-value { font-size: 1.5rem; font-weight: 800; background: linear-gradient(135deg, var(--primary), var(--accent)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.stat-label { font-size: 0.78rem; color: var(--text-light); }
/* === A11y === */
:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; border-radius: 4px; }
.skip-link { position: absolute; top: -100%; left: 1rem; background: var(--primary); color: #fff; padding: 0.5rem 1rem; border-radius: 0 0 6px 6px; z-index: 999; text-decoration: none; font-size: 0.9rem; }
.skip-link:focus { top: 0; }
/* === Print === */
@media print { .sidebar, .search-box, .toolbar, .dark-toggle, .back-to-top, .hamburger, .sidebar-reopen, .sidebar-overlay, .practice-score, .skip-link, .self-score-panel, .export-panel { display: none !important; } .main { margin-left: 0; max-width: 100%; } .subject-body { display: block !important; } .answer-section { display: block !important; } .print-hidden { display: none !important; } .print-header { display: block !important; } .print-no-answers .answer-section { display: none !important; } @page { margin: 1.5cm; } .subject-card { page-break-inside: avoid; break-inside: avoid; overflow: visible !important; } .subject-card + .subject-card { margin-top: 1rem; } .year-heading { page-break-after: avoid; break-after: avoid; } body { background: white !important; color: #000 !important; } .year-section + .year-section { page-break-before: auto; } .exam-content-v2 { page-break-inside: avoid; } h2.year-heading { page-break-after: avoid; } .answer-grid { grid-template-columns: repeat(auto-fill, minmax(50px, 1fr)); } .answer-cell { border: 1px solid #ccc; } .answer-cell .q-ans { color: #2563eb; } }
/* === Toolbar === */
.toolbar { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1.5rem; align-items: center; background: var(--card-bg); border-radius: var(--radius); padding: 0.75rem; box-shadow: var(--shadow-sm); }
.toolbar-btn { padding: 0.55rem 1rem; border: 1.5px solid transparent; border-radius: 8px; background: transparent; color: var(--text); font-size: 0.85rem; min-height: 44px; display: inline-flex; align-items: center; font-family: inherit; cursor: pointer; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); user-select: none; }
.toolbar-btn:hover { background: #f1f5f9; color: var(--primary); }
.toolbar-btn.active { background: var(--primary); color: #fff; border-color: var(--primary); }
.bookmark-btn { background: none; border: none; cursor: pointer; font-size: 1.2rem; padding: 0.5rem; opacity: 0.35; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); line-height: 1; flex-shrink: 0; margin-left: 0.25rem; min-width: 44px; min-height: 44px; display: inline-flex; align-items: center; justify-content: center; }
.bookmark-btn:hover { opacity: 0.7; }
.bookmark-btn.active { opacity: 1; color: #f59e0b; }
.toolbar-btn.bookmark-filter.active { background: #fef3c7; color: #92400e; border-color: #fde68a; }
/* === Dark Toggle === */
.dark-toggle { position: fixed; bottom: 2rem; left: 2rem; z-index: 200; width: 44px; height: 44px; border-radius: 50%; background: var(--card-bg); border: 2px solid var(--border); cursor: pointer; display: flex; align-items: center; justify-content: center; box-shadow: var(--shadow-md); transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); overflow: hidden; }
.dark-toggle:hover { border-color: var(--accent); transform: scale(1.1); }
.dark-toggle svg { width: 22px; height: 22px; transition: transform 0.5s cubic-bezier(0.4, 0, 0.2, 1); }
.dark-toggle:active svg { transform: rotate(360deg); }
.dark-icon-moon, .dark-icon-sun { display: block; }
html.dark .dark-icon-moon { display: none; }
html:not(.dark) .dark-icon-sun { display: none; }
/* === Dark Mode === */
html.dark { --primary: #818cf8; --primary-light: #6366f1; --accent: #a5b4fc; --bg: #0f172a; --card-bg: #1e293b; --border: #334155; --text: #f1f5f9; --text-light: #94a3b8; --text-muted: #64748b; --success: #34d399; --warning: #fbbf24; --danger: #f87171; --shadow-sm: 0 1px 2px rgba(0,0,0,0.2); --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.3), 0 2px 4px -2px rgba(0,0,0,0.2); --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.4), 0 4px 6px -4px rgba(0,0,0,0.3); }
html.dark .sidebar { background: #020617; }
html.dark .subject-header { background: linear-gradient(135deg, #312e81, #4f46e5); }
html.dark .search-input { background: #1e293b; color: #f1f5f9; border-color: #334155; }
html.dark .search-input::placeholder { color: #64748b; }
html.dark .toolbar { background: #1e293b; }
html.dark .toolbar-btn { color: #f1f5f9; }
html.dark .toolbar-btn:hover { background: #334155; }
html.dark .toolbar-btn.active { background: #6366f1; border-color: #6366f1; }
html.dark .filter-chip { background: #1e293b; color: #94a3b8; border-color: #334155; }
html.dark .filter-chip.active { background: #6366f1; color: #fff; border-color: #6366f1; }
html.dark .meta-tag { background: #334155; color: #cbd5e1; }
html.dark .exam-metadata { background: #1e293b; border-color: #334155; }
html.dark .exam-note { border-color: #334155; }
html.dark .reading-passage { background: #1e293b; border-color: #6366f1; }
html.dark .stats-bar { background: var(--card-bg); border-color: var(--border); }
html.dark .stat-item { background: transparent; }
html.dark .stat-value { background: linear-gradient(135deg, #818cf8, #a5b4fc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
html.dark .exam-section-marker { color: var(--primary); border-top-color: var(--border); }
html.dark .essay-question { border-bottom-color: #334155; }
html.dark .mc-question { border-top-color: #334155; }
html.dark .subject-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.4); }
html.dark .toolbar-btn.bookmark-filter.active { background: #92400e; color: #fef3c7; border-color: #b45309; }
html.dark .bookmark-btn.active { color: #fbbf24; }
html.dark .dark-toggle { background: #1e293b; border-color: #334155; }
/* === Highlight === */
.highlight { background: #fefcbf; padding: 1px 3px; border-radius: 3px; }
.highlight.current { background: #fde68a; box-shadow: 0 0 0 3px rgba(253,230,138,0.5); font-weight: 600; }
html.dark .highlight { background: #92400e; color: #fef3c7; }
html.dark .highlight.current { background: #d97706; color: #0f172a; }
/* === Back to Top === */
.back-to-top { position: fixed; bottom: 2rem; right: 2rem; width: 44px; height: 44px; border-radius: 50%; background: var(--primary); color: #fff; border: none; cursor: pointer; font-size: 1.3rem; display: flex; align-items: center; justify-content: center; box-shadow: var(--shadow-md); opacity: 0; visibility: hidden; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); z-index: 200; }
.back-to-top.visible { opacity: 1; visibility: visible; }
.back-to-top:hover { background: var(--accent); transform: translateY(-2px); }
html.dark .back-to-top { background: #6366f1; }
/* === Mobile Nav === */
.hamburger { display: none; position: fixed; top: 1rem; left: 1rem; z-index: 300; width: 44px; height: 44px; border-radius: var(--radius); background: var(--primary); color: #fff; border: none; cursor: pointer; font-size: 1.4rem; align-items: center; justify-content: center; box-shadow: var(--shadow-md); }
.sidebar-overlay { display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.5); z-index: 90; backdrop-filter: blur(2px); }
.sidebar-overlay.active { display: block; }
/* === 768px Mobile === */
@media (max-width: 768px) { .hamburger { display: flex; } .sidebar-toggle { display: none; } .sidebar-reopen { display: none !important; } .sidebar { transform: translateX(-100%); } .sidebar.open, body.sidebar-collapsed .sidebar.open { transform: translateX(0); } .main { margin-left: 0; padding: 1rem; padding-top: 4rem; max-width: 100%; overflow-x: hidden; } .page-title { font-size: 1.4rem; } .stats-bar { gap: 0.5rem; padding: 0.75rem; flex-wrap: wrap; justify-content: center; } .stat-item { padding: 0.5rem 0.75rem; } .stat-value { font-size: 1.2rem; } .search-input { font-size: 16px; padding: 0.6rem 0.75rem 0.6rem 2.5rem; } .search-filters { gap: 0.3rem; overflow-x: auto; flex-wrap: nowrap; padding-bottom: 0.25rem; } .filter-chip { white-space: nowrap; flex-shrink: 0; } .toolbar { gap: 0.4rem; padding: 0.5rem; border-radius: var(--radius); } .year-heading { font-size: 1.15rem; } .subject-header { padding: 0.75rem 1rem; } .subject-header h3 { font-size: 0.88rem; } .subject-body { padding: 1rem; } .subject-card { border-radius: var(--radius); } .essay-question { font-size: 0.85rem; line-height: 1.75; } .q-text { font-size: 0.85rem; } .opt-text { font-size: 0.83rem; } .mc-option { padding-left: 1.5rem; } .back-to-top { bottom: 1.5rem; right: 1.5rem; } .dark-toggle { bottom: 1.5rem; left: 1.5rem; } .toolbar-btn { font-size: 0.82rem; padding: 0.5rem 0.75rem; }
  .answer-section { padding: 0.75rem; border-radius: 10px; } .answer-grid { grid-template-columns: repeat(auto-fill, minmax(50px, 1fr)); gap: 0.3rem; } .answer-cell { padding: 0.3rem 0.2rem; } .q-num { font-size: 0.7rem; } .q-ans { font-size: 0.8rem; }
  .practice-score { padding: 0.5rem 1rem; font-size: 0.85rem; } .self-score-panel { margin: 0.5rem 0; padding: 0.65rem 0.85rem; border-radius: 12px; } .reveal-btn { padding: 0.55rem 1.25rem; font-size: 0.82rem; } .score-btn { padding: 0.55rem 1.15rem; font-size: 0.82rem; } .self-score-panel.scored::after { font-size: 0.9rem; padding: 0.4rem 1rem; }
  .subject-view-section { margin-bottom: 2rem; } .sv-year-tag { font-size: 0.65rem; padding: 0.15rem 0.4rem; }
  .toolbar-select { font-size: 0.82rem; padding: 0.5rem; min-height: 44px; width: 100%; max-width: 100%; overflow: hidden; text-overflow: ellipsis; } .search-jump { gap: 0.3rem; } .search-jump button { font-size: 0.8rem; padding: 0.3rem 0.6rem; min-height: 44px; }
}
/* === Answer Grid === */
.answer-section { margin-top: 1rem; padding: 1.25rem; background: linear-gradient(135deg, #f8fafc, #f1f5f9); border: 1px solid var(--border); border-radius: 16px; border-left: 4px solid var(--primary); }
.answer-title { display: inline-block; font-size: 0.82rem; font-weight: 700; color: #fff; background: linear-gradient(135deg, var(--primary), var(--accent)); padding: 0.35rem 0.85rem; border-radius: 8px; margin-bottom: 0.75rem; letter-spacing: 0.03em; box-shadow: 0 2px 6px rgba(37,99,235,0.25); }
.answer-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(64px, 1fr)); gap: 0.4rem; }
.answer-cell { display: flex; flex-direction: column; align-items: center; padding: 0.55rem 0.4rem; background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); min-height: 48px; }
.answer-cell:hover { transform: translateY(-2px) scale(1.03); box-shadow: var(--shadow-md); }
.answer-cell:active { transform: scale(0.95); transition-duration: 0.1s; }
.answer-cell .q-num { font-size: 0.7rem; color: var(--text-light); font-weight: 700; background: #e2e8f0; border-radius: 4px; padding: 0.05rem 0.35rem; line-height: 1.4; }
.answer-cell .q-ans { font-size: 0.95rem; font-weight: 800; color: var(--primary); margin-top: 0.1rem; }
.answer-cell.corrected { border-color: var(--danger); background: #fef2f2; }
.answer-cell.corrected .q-ans { color: var(--danger); text-decoration: line-through; }
html.dark .answer-section { background: linear-gradient(135deg, #1e293b, #1a2332); border-color: #334155; border-left-color: var(--primary); }
html.dark .answer-cell { background: #0f172a; border-color: #334155; }
html.dark .answer-cell .q-num { background: #334155; }
html.dark .answer-title { background: linear-gradient(135deg, #4f46e5, #6366f1); }
html.dark .answer-cell.corrected { border-color: var(--danger); background: #450a0a; }
/* === Free Point === */
.answer-cell.free-point { background: linear-gradient(135deg, #fefce8, #fef9c3); border-color: #facc15; animation: freePointPulse 2.5s ease-in-out infinite; }
.answer-cell.free-point .q-ans { color: #b45309; font-size: 0.85rem; font-weight: 700; }
html.dark .answer-cell.free-point { background: linear-gradient(135deg, #422006, #451a03); border-color: #a16207; animation: freePointPulse 2.5s ease-in-out infinite; }
html.dark .answer-cell.free-point .q-ans { color: #fbbf24; }
@keyframes freePointPulse { 0%, 100% { box-shadow: 0 0 6px rgba(250,204,21,0.2); } 50% { box-shadow: 0 0 14px rgba(250,204,21,0.45); } }
/* === Passage Fragment === */
.mc-question[data-subtype="passage_fragment"] { border-left: 3px solid #60a5fa; background: #eff6ff; padding: 0.5rem 0.75rem 0.5rem 1rem; border-radius: 8px; margin-bottom: 0.3rem; position: relative; }
.mc-question[data-subtype="passage_fragment"]::before { content: '\\01F4D6 閱讀段落'; display: inline-block; font-size: 0.75rem; color: #2563eb; background: #dbeafe; padding: 0.1rem 0.5rem; border-radius: 6px; margin-right: 0.5rem; vertical-align: middle; }
html.dark .mc-question[data-subtype="passage_fragment"] { background: #1e293b; border-left-color: #818cf8; }
html.dark .mc-question[data-subtype="passage_fragment"]::before { background: #312e81; color: #a5b4fc; }
/* === Search Jump === */
.search-jump { display: inline-flex; align-items: center; gap: 0.5rem; margin-left: 0.75rem; }
.search-jump button { padding: 0.35rem 0.7rem; border: 1px solid var(--border); border-radius: 8px; background: var(--card-bg); color: var(--text); font-size: 0.82rem; cursor: pointer; font-family: inherit; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); min-height: 44px; min-width: 44px; }
.search-jump button:hover { border-color: var(--primary); color: var(--primary); }
.hit-counter { font-size: 0.82rem; color: var(--text-light); font-weight: 600; min-width: 3em; text-align: center; }
html.dark .search-jump button { background: #1e293b; border-color: #334155; color: #f1f5f9; }
/* === Practice Mode === */
.practice-mode .answer-section { display: none; }
.practice-mode .answer-section.revealed { display: block; animation: answerReveal 0.4s cubic-bezier(0.4, 0, 0.2, 1); }
@keyframes answerReveal { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
.self-score-panel { display: flex; gap: 1rem; align-items: center; justify-content: center; margin: 1rem 0 0.75rem; flex-wrap: wrap; background: linear-gradient(135deg, #f8fafc, #f1f5f9); border: 1px solid var(--border); border-radius: 14px; padding: 0.85rem 1.25rem; box-shadow: var(--shadow-sm); min-height: 52px; }
.self-score-panel.scored.was-correct { background: linear-gradient(135deg, #f0fdf4, #dcfce7); border-color: #86efac; }
.self-score-panel.scored.was-wrong { background: linear-gradient(135deg, #fef2f2, #fee2e2); border-color: #fca5a5; }
.self-score-panel.free-point-scored { background: linear-gradient(135deg, #fffbeb, #fef3c7); border-color: #fcd34d; }
.reveal-btn { display: inline-flex; align-items: center; padding: 0.65rem 1.75rem; border: none; border-radius: 999px; background: linear-gradient(135deg, var(--primary), var(--accent)); color: #fff; font-size: 0.88rem; font-weight: 600; cursor: pointer; font-family: inherit; transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); min-height: 44px; box-shadow: var(--shadow-sm); }
.reveal-btn::before { content: '👁️ '; }
.reveal-btn:hover { box-shadow: var(--shadow-md); transform: translateY(-2px); filter: brightness(1.08); }
.reveal-btn:active { transform: translateY(0) scale(0.97); }
.score-btn { padding: 0.65rem 1.5rem; border-radius: 999px; border: none; font-size: 0.88rem; font-weight: 600; cursor: pointer; font-family: inherit; transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); display: none; min-height: 44px; color: #fff; box-shadow: var(--shadow-sm); }
.score-btn.visible { display: inline-flex; align-items: center; }
.score-btn.btn-correct { background: linear-gradient(135deg, #10b981, #059669); box-shadow: 0 2px 8px rgba(16,185,129,0.25); }
.score-btn.btn-correct:hover { box-shadow: 0 4px 12px rgba(16,185,129,0.4); transform: translateY(-2px); }
.score-btn.btn-wrong { background: linear-gradient(135deg, #f87171, #ef4444); box-shadow: 0 2px 8px rgba(239,68,68,0.25); }
.score-btn.btn-wrong:hover { box-shadow: 0 4px 12px rgba(239,68,68,0.4); transform: translateY(-2px); }
.score-btn:active { transform: translateY(0) scale(0.97); }
.self-score-panel.scored .reveal-btn, .self-score-panel.scored .score-btn { display: none; }
.self-score-panel.scored::after { content: attr(data-result); font-size: 1rem; font-weight: 700; padding: 0.5rem 1.5rem; border-radius: 999px; box-shadow: 0 2px 8px rgba(0,0,0,0.15); animation: badgePop 0.35s cubic-bezier(0.34,1.56,0.64,1); }
.self-score-panel.scored.was-correct::after { background: #15803d; color: #fff; }
.self-score-panel.scored.was-wrong::after { background: #dc2626; color: #fff; }
.self-score-panel.free-point-scored::after { background: #b45309; color: #fff; }
@keyframes badgePop { from { opacity: 0; transform: scale(0.5); } to { opacity: 1; transform: scale(1); } }
html.dark .self-score-panel { background: linear-gradient(135deg, #1e293b, #1a2332); border-color: #334155; }
html.dark .self-score-panel.scored.was-correct { background: linear-gradient(135deg, #052e16, #064e3b); border-color: #065f46; }
html.dark .self-score-panel.scored.was-wrong { background: linear-gradient(135deg, #450a0a, #7f1d1d); border-color: #991b1b; }
html.dark .self-score-panel.free-point-scored { background: linear-gradient(135deg, #422006, #451a03); border-color: #92400e; }
html.dark .self-score-panel.scored.was-correct::after { background: #059669; color: #fff; }
html.dark .self-score-panel.scored.was-wrong::after { background: #ef4444; color: #fff; }
html.dark .self-score-panel.free-point-scored::after { background: #d97706; color: #fff; }
html.dark .score-btn.btn-correct { background: linear-gradient(135deg, #059669, #047857); }
html.dark .score-btn.btn-wrong { background: linear-gradient(135deg, #ef4444, #dc2626); }
/* === Practice Score === */
.practice-score { display: none; position: sticky; top: 0; z-index: 55; background: linear-gradient(135deg, var(--primary), var(--accent), #8b5cf6); color: #fff; padding: 0.75rem 1.5rem; border-radius: var(--radius); margin-bottom: 1rem; font-size: 0.92rem; align-items: center; gap: 0.75rem; box-shadow: var(--shadow-lg); }
.practice-score.visible { display: flex; flex-wrap: wrap; }
.score-text { flex: 1; font-weight: 500; }
.score-pct { font-size: 1.15rem; font-weight: 800; min-width: 3.5em; text-align: center; background: rgba(255,255,255,0.25); padding: 0.25rem 0.75rem; border-radius: 999px; border: 1px solid rgba(255,255,255,0.3); }
.score-reset { padding: 0.4rem 1rem; border: 1.5px solid rgba(255,255,255,0.5); border-radius: 999px; background: transparent; color: #fff; font-size: 0.82rem; font-weight: 600; cursor: pointer; font-family: inherit; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); }
.score-reset:hover { background: rgba(255,255,255,0.2); border-color: #fff; transform: translateY(-1px); }
.score-reset:active { transform: translateY(0) scale(0.97); }
html.dark .practice-score { background: linear-gradient(135deg, #312e81, #4f46e5, #6d28d9); }
/* === Subject View === */
.subject-view-section { margin-bottom: 3rem; }
.subject-view-section .sv-heading { font-size: 1.3rem; font-weight: 700; color: var(--primary); border-bottom: 3px solid var(--accent); padding-bottom: 0.5rem; margin-bottom: 1.5rem; }
.sv-year-tag { display: inline-block; font-size: 0.7rem; padding: 0.15rem 0.5rem; border-radius: 6px; background: var(--accent); color: #fff; margin-left: 0.5rem; vertical-align: middle; font-weight: 600; }
html.dark .sv-year-tag { background: #6366f1; }
/* === Toolbar Extended === */
.toolbar-sep { width: 1px; height: 28px; background: var(--border); margin: 0 0.25rem; flex-shrink: 0; }
.toolbar-select { padding: 0.55rem 0.75rem; border: 1.5px solid var(--border); border-radius: 8px; background: var(--card-bg); color: var(--text); font-size: 0.85rem; font-family: inherit; cursor: pointer; min-height: 44px; outline: none; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); }
.toolbar-select:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(37,99,235,0.1); }
html.dark .toolbar-select { background: #1e293b; color: #f1f5f9; border-color: #334155; }
.toolbar-btn.practice-active { background: #64748b; color: #fff; border-color: #64748b; }
html.dark .toolbar-btn.practice-active { background: #475569; border-color: #475569; }
/* === Smooth Transitions === */
.main { transition: background-color 0.3s ease; }
.sidebar { transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1), background-color 0.3s ease; }
.subject-card, .stats-bar, .exam-metadata, .answer-section, .search-input, .toolbar-btn, .filter-chip, .dark-toggle, .back-to-top, .toolbar-select, .practice-score, .self-score-panel, .answer-cell { transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease; }
/* === Focus States === */
.toolbar-select:hover { border-color: var(--primary); }
.reveal-btn:focus-visible, .score-btn:focus-visible, .search-jump button:focus-visible, .export-option:focus-visible, .export-cancel:focus-visible, .sidebar-home:focus-visible, .sidebar-link:focus-visible, .sidebar-year:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
html.dark .reveal-btn { background: linear-gradient(135deg, #6366f1, #818cf8); color: #fff; }
html.dark .reveal-btn:hover { box-shadow: 0 4px 12px rgba(99,102,241,0.4); }
/* === Export Panel === */
.export-panel { background: var(--card-bg); border: 1px solid var(--border); border-radius: var(--radius); padding: 1rem; margin-bottom: 1rem; box-shadow: var(--shadow-lg); }
.export-title { font-size: 0.9rem; font-weight: 700; color: var(--primary); margin-bottom: 0.75rem; }
.export-option { display: block; width: 100%; padding: 0.6rem 1rem; margin-bottom: 0.5rem; border: 1.5px solid var(--border); border-radius: 10px; background: var(--card-bg); color: var(--text); font-size: 0.88rem; font-family: inherit; cursor: pointer; text-align: left; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); min-height: 44px; }
.export-option:hover { border-color: var(--primary); color: var(--primary); background: rgba(37,99,235,0.04); }
.export-cancel { display: block; margin-top: 0.25rem; padding: 0.5rem 0.75rem; border: none; background: transparent; color: var(--text-muted); font-size: 0.8rem; font-family: inherit; cursor: pointer; min-height: 44px; }
.export-cancel:hover { color: var(--text); }
html.dark .export-panel { background: #1e293b; border-color: #334155; }
html.dark .export-option { background: #0f172a; border-color: #334155; color: #f1f5f9; }
html.dark .export-option:hover { border-color: var(--accent); color: var(--accent); background: rgba(165,180,252,0.06); }
html.dark .export-cancel { color: var(--text-muted); }
html.dark .export-cancel:hover { color: var(--text); }
/* === Print Header === */
.print-header { display: none; text-align: center; padding-bottom: 1rem; margin-bottom: 1.5rem; border-bottom: 2px solid #2563eb; }
.print-header h1 { font-size: 1.5rem; font-weight: 800; color: #2563eb; margin-bottom: 0.3rem; }
.print-header p { font-size: 0.82rem; color: #64748b; }
/* === Galaxy Fold 320px === */
@media (max-width: 320px) { .page-title { font-size: 1.2rem; word-break: keep-all; } .page-subtitle { font-size: 0.82rem; } .stats-bar { gap: 0.4rem; padding: 0.5rem; } .stat-item { padding: 0.4rem 0.5rem; } .stat-value { font-size: 1rem; } .stat-label { font-size: 0.7rem; } .toolbar { gap: 0.3rem; padding: 0.5rem; } .toolbar-btn { font-size: 0.75rem; padding: 0.4rem 0.6rem; min-height: 44px; } .toolbar-sep { display: none; } .toolbar-select { font-size: 0.75rem; padding: 0.4rem; } .subject-header { padding: 0.6rem 0.75rem; } .subject-header h3 { font-size: 0.8rem; } .subject-body { padding: 0.75rem; } .essay-question { font-size: 0.8rem; text-indent: -1.2em; padding-left: 1.2em; line-height: 1.6; } .q-text { font-size: 0.8rem; line-height: 1.6; } .opt-text { font-size: 0.78rem; line-height: 1.6; } .mc-option { padding-left: 1rem; } .filter-chip { font-size: 0.72rem; padding: 0.4rem 0.6rem; min-width: 44px; text-align: center; } .export-panel { padding: 0.75rem; } .export-option { font-size: 0.8rem; padding: 0.5rem 0.75rem; } .answer-grid { grid-template-columns: repeat(auto-fill, minmax(45px, 1fr)); } .self-score-panel { padding: 0.5rem 0.65rem; border-radius: 10px; gap: 0.4rem; } .reveal-btn { padding: 0.5rem 1rem; font-size: 0.78rem; } .score-btn { padding: 0.5rem 0.9rem; font-size: 0.78rem; } .self-score-panel.scored::after { font-size: 0.85rem; padding: 0.35rem 0.85rem; } .practice-score { padding: 0.4rem 0.75rem; font-size: 0.75rem; } .score-text { white-space: nowrap; } .score-pct { font-size: 0.9rem; padding: 0.15rem 0.45rem; min-width: 2.5em; } .score-reset { font-size: 0.7rem; padding: 0.25rem 0.5rem; } }
/* === Performance === */
.subject-card { content-visibility: auto; contain-intrinsic-size: auto 80px; }
.subject-card.open { content-visibility: visible; }
/* === Button Press === */
.toolbar-btn:active, .filter-chip:active { transform: scale(0.97); }
.bookmark-btn:active { transform: scale(0.9); }
/* === 480px Tablet === */
@media (max-width: 480px) { .toolbar-sep { display: none; } .page-title { font-size: 1.25rem; } }
/* === Mid Screen === */
@media (min-width: 769px) and (max-width: 1240px) { .main { max-width: calc(100vw - var(--sidebar-w) - 3rem); } body.sidebar-collapsed .main { max-width: 960px; } }
/* === Large Screen === */
@media (min-width: 1200px) { .main { max-width: 1100px; } }
/* === Mobile Filter Scroll === */
@media (max-width: 768px) { .search-filters { -webkit-overflow-scrolling: touch; scrollbar-width: none; padding-right: 1.5rem; scroll-snap-type: x proximity; } .search-filters::-webkit-scrollbar { display: none; } .filter-chip { scroll-snap-align: start; } }
/* === Mobile Filter Fade === */
@media (max-width: 768px) { .search-box::after { content: ''; position: absolute; right: 0; bottom: 0.25rem; width: 2rem; height: 44px; background: linear-gradient(to right, rgba(248,250,252,0), var(--bg)); pointer-events: none; z-index: 1; } }
html.dark .search-box::after { background: linear-gradient(to right, rgba(15,23,42,0), var(--bg)); }
/* === Mobile Toolbar Grid === */
@media (max-width: 768px) { .toolbar { display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem; } .toolbar-sep { display: none; } .toolbar-select { grid-column: 1 / -1; } #exportBtn { grid-column: 1 / -1; } }
/* === Mobile Export Sheet === */
@media (max-width: 768px) { .export-panel { position: fixed; bottom: 0; left: 0; right: 0; z-index: 250; border-radius: 16px 16px 0 0; padding: 1.25rem 1.25rem calc(1.25rem + env(safe-area-inset-bottom, 0px)); box-shadow: 0 -4px 24px rgba(0,0,0,0.15); margin: 0; max-height: 60vh; overflow-y: auto; } }
/* === Mobile Search Sticky === */
@media (max-width: 768px) { html { scroll-padding-top: 100px; } .search-box { top: 3.5rem; z-index: 49; } .practice-score { top: 7rem; border-radius: 0 0 var(--radius) var(--radius); z-index: 48; } }
/* === iOS Safe Area === */
@supports (padding: env(safe-area-inset-bottom)) { @media (max-width: 768px) { .dark-toggle { bottom: calc(1.5rem + env(safe-area-inset-bottom)); } .back-to-top { bottom: calc(1.5rem + env(safe-area-inset-bottom)); } .hamburger { top: calc(1rem + env(safe-area-inset-top)); } .main { padding-bottom: env(safe-area-inset-bottom); } } }
/* === Landscape === */
@media (max-width: 768px) and (orientation: landscape) { .main { padding-top: 3rem; } .stats-bar { flex-wrap: nowrap; } .page-title { font-size: 1.2rem; margin-bottom: 0.25rem; } .page-subtitle { margin-bottom: 1rem; font-size: 0.85rem; } .year-heading { font-size: 1.05rem; margin-bottom: 1rem; } .year-section { margin-bottom: 2rem; } }
"""


def generate_shared_js():
    """生成共用 JS（使用安全 DOM 方法，避免 innerHTML）"""
    return """/* === 共用功能（靜態網站 — 所有資料來自可信的本地 JSON）=== */
function debounce(fn, ms) {
  let t; return function(...a) { clearTimeout(t); t = setTimeout(() => fn.apply(this, a), ms); };
}
const debouncedSearch = debounce(v => doSearch(v), window.innerWidth <= 768 ? 300 : 180);
function toggleYear(el) { el.classList.toggle('active'); el.setAttribute('aria-expanded', el.classList.contains('active') ? 'true' : 'false'); }

function clearHighlights() {
  document.querySelectorAll('.highlight').forEach(h => {
    const p = h.parentNode;
    p.replaceChild(document.createTextNode(h.textContent), h);
    p.normalize();
  });
}
function highlightText(node, query) {
  if (!query) return 0;
  if (node.nodeType === 3) {
    var count = 0;
    var current = node;
    var lowerQuery = query.toLowerCase();
    while (current) {
      var idx = current.textContent.toLowerCase().indexOf(lowerQuery);
      if (idx === -1) break;
      var span = document.createElement('span');
      span.className = 'highlight';
      var matched = current.splitText(idx);
      current = matched.splitText(query.length);
      span.appendChild(matched.cloneNode(true));
      matched.parentNode.replaceChild(span, matched);
      count++;
    }
    return count;
  } else if (node.nodeType === 1 && node.childNodes.length && !/(script|style)/i.test(node.tagName) && !node.classList.contains('highlight')) {
    let c = 0;
    for (let i = 0; i < node.childNodes.length; i++) c += highlightText(node.childNodes[i], query);
    return c;
  }
  return 0;
}

let activeYearFilter = '';
function toggleFilter(el, type) {
  if (type === 'year') {
    document.querySelectorAll('.filter-chip[data-year]').forEach(c => c.classList.remove('active'));
    el.classList.add('active');
    activeYearFilter = el.dataset.year || '';
    doSearch(document.getElementById('searchInput').value);
  }
}

let searchHits = [];
let currentHitIdx = -1;
let currentView = 'year';

function getActiveViewSelector() { return currentView === 'subject' ? '#subjectView' : '#yearView'; }

function doSearch(query) {
  if (query === undefined || query === null) query = document.getElementById('searchInput').value || '';
  query = query.trim();
  const stats = document.getElementById('searchStatsText');
  const vs = getActiveViewSelector();
  const cards = document.querySelectorAll(vs + ' .subject-card');
  const sections = document.querySelectorAll(vs + ' .year-section, ' + vs + ' .subject-view-section');
  clearHighlights();
  searchHits = [];
  currentHitIdx = -1;
  const bmFilter = bookmarkFilterActive;
  const bmarks = bmFilter ? getStore('exam-bookmarks') : null;

  if (activeYearFilter && !query.trim()) {
    if (currentView === 'subject') {
      cards.forEach(function(c) {
        if (bmFilter) { const cid = c.getAttribute('data-card-id') || c.id; if (!bmarks[cid]) { c.style.display = 'none'; return; } }
        const tag = c.querySelector('.sv-year-tag');
        c.style.display = (tag && tag.textContent.trim().startsWith(activeYearFilter)) ? '' : 'none';
      });
      sections.forEach(function(s) {
        s.style.display = s.querySelectorAll('.subject-card:not([style*="display: none"])').length ? '' : 'none';
      });
    } else {
      sections.forEach(s => {
        const h = s.querySelector('.year-heading');
        const yName = h ? h.textContent.trim() : '';
        s.style.display = yName.startsWith(activeYearFilter) ? '' : 'none';
      });
      cards.forEach(c => {
        if (bmFilter) { const cid = c.getAttribute('data-card-id') || c.id; if (!bmarks[cid]) { c.style.display = 'none'; return; } }
        c.style.display = '';
      });
    }
    stats.textContent = activeYearFilter ? '篩選：' + activeYearFilter + '年' : '';
    updateSearchJump();
    return;
  }
  if (!query.trim() && !activeYearFilter && !bmFilter) {
    cards.forEach(c => { c.style.display = ''; c.classList.remove('open'); });
    sections.forEach(s => s.style.display = '');
    stats.textContent = '';
    updateSearchJump();
    return;
  }
  let matchCount = 0, totalHL = 0;
  cards.forEach(card => {
    if (bmFilter) {
      const cid = card.getAttribute('data-card-id') || card.id;
      if (!bmarks[cid]) { card.style.display = 'none'; return; }
    }
    if (activeYearFilter) {
      if (currentView === 'subject') {
        const tag = card.querySelector('.sv-year-tag');
        if (!tag || !tag.textContent.trim().startsWith(activeYearFilter)) { card.style.display = 'none'; return; }
      } else {
        const yearSection = card.closest('.year-section');
        const yName = yearSection ? yearSection.querySelector('.year-heading').textContent.trim() : '';
        if (!yName.startsWith(activeYearFilter)) { card.style.display = 'none'; return; }
      }
    }
    const text = (window._cardTextCache && window._cardTextCache.has(card)) ? window._cardTextCache.get(card) : card.textContent.toLowerCase();
    const queryLower = query.toLowerCase();
    if (!query.trim() || text.includes(queryLower)) {
      card.style.display = '';
      if (query.trim()) {
        card.classList.add('open');
        const body = card.querySelector('.subject-body');
        if (body) totalHL += highlightText(body, query);
      }
      matchCount++;
    } else {
      card.style.display = 'none'; card.classList.remove('open');
    }
  });
  sections.forEach(s => {
    s.style.display = s.querySelectorAll('.subject-card:not([style*="display: none"])').length ? '' : 'none';
  });
  searchHits = Array.from(document.querySelectorAll(vs + ' .highlight'));
  let txt = '';
  if (query.trim()) txt += '找到 ' + matchCount + ' 份相關試卷，' + totalHL + ' 處匹配';
  else if (activeYearFilter) txt += '篩選：' + activeYearFilter + '年，' + matchCount + ' 份試卷';
  stats.textContent = txt;
  updateSearchJump();
}

/* === 搜尋跳轉 (Phase 4) === */
function updateSearchJump() {
  const jumpEl = document.getElementById('searchJump');
  if (!jumpEl) return;
  while (jumpEl.firstChild) jumpEl.removeChild(jumpEl.firstChild);
  if (searchHits.length > 1) {
    const wrap = document.createElement('span');
    wrap.className = 'search-jump';
    const prevBtn = document.createElement('button');
    prevBtn.textContent = '◀';
    prevBtn.title = '上一個';
    prevBtn.setAttribute('aria-label', '上一個匹配');
    prevBtn.addEventListener('click', function() { jumpHit(-1); });
    const counter = document.createElement('span');
    counter.className = 'hit-counter';
    counter.id = 'hitCounter';
    counter.textContent = '0/' + searchHits.length;
    const nextBtn = document.createElement('button');
    nextBtn.textContent = '▶';
    nextBtn.title = '下一個';
    nextBtn.setAttribute('aria-label', '下一個匹配');
    nextBtn.addEventListener('click', function() { jumpHit(1); });
    wrap.appendChild(prevBtn);
    wrap.appendChild(counter);
    wrap.appendChild(nextBtn);
    jumpEl.appendChild(wrap);
  }
}

function jumpHit(dir) {
  if (!searchHits.length) return;
  if (currentHitIdx >= 0 && currentHitIdx < searchHits.length) searchHits[currentHitIdx].classList.remove('current');
  currentHitIdx += dir;
  if (currentHitIdx >= searchHits.length) currentHitIdx = 0;
  if (currentHitIdx < 0) currentHitIdx = searchHits.length - 1;
  var target = searchHits[currentHitIdx];
  /* 確保 content-visibility 不影響捲動計算 */
  var card = target.closest('.subject-card');
  if (card) card.style.contentVisibility = 'visible';
  target.classList.add('current');
  requestAnimationFrame(function() { scrollToWithOffset(target); });
  const counter = document.getElementById('hitCounter');
  if (counter) counter.textContent = (currentHitIdx + 1) + '/' + searchHits.length;
}

/* === Hamburger === */
document.addEventListener('DOMContentLoaded', function() {
  const hamburger = document.getElementById('hamburgerBtn');
  const sidebar = document.getElementById('sidebar');
  const sidebarOverlay = document.getElementById('sidebarOverlay');
  function closeMobileSidebar() {
    sidebar.classList.remove('open');
    sidebarOverlay.classList.remove('active');
    if (hamburger) { hamburger.textContent = '☰'; hamburger.setAttribute('aria-expanded', 'false'); }
  }
  if (hamburger) {
    hamburger.addEventListener('click', function() {
      const open = sidebar.classList.toggle('open');
      sidebarOverlay.classList.toggle('active');
      hamburger.textContent = open ? '✕' : '☰';
      hamburger.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    sidebarOverlay.addEventListener('click', closeMobileSidebar);
    sidebar.querySelectorAll('.sidebar-link').forEach(function(l) {
      l.addEventListener('click', function() { if (window.innerWidth <= 768) closeMobileSidebar(); });
    });
    /* 滑動關閉 sidebar */
    var touchStartX = 0, touchStartY = 0, swiping = false;
    sidebar.addEventListener('touchstart', function(e) {
      if (e.touches.length > 1) return;
      touchStartX = e.touches[0].clientX; touchStartY = e.touches[0].clientY; swiping = true;
    }, { passive: true });
    sidebar.addEventListener('touchmove', function(e) {
      if (!swiping) return;
      var dy = Math.abs(e.touches[0].clientY - touchStartY);
      if (dy > 30) swiping = false; /* 垂直滾動取消水平判定 */
    }, { passive: true });
    sidebar.addEventListener('touchend', function(e) {
      if (!swiping) return; swiping = false;
      var dx = e.changedTouches[0].clientX - touchStartX;
      if (dx < -60 && sidebar.classList.contains('open')) closeMobileSidebar();
    }, { passive: true });
    sidebar.addEventListener('touchcancel', function() { swiping = false; }, { passive: true });
  }

  /* Sidebar toggle */
  const sidebarToggle = document.getElementById('sidebarToggle');
  const sidebarReopen = document.getElementById('sidebarReopen');
  try { if (localStorage.getItem('sidebar-collapsed') === '1') document.body.classList.add('sidebar-collapsed'); } catch(e) {}
  if (sidebarToggle) sidebarToggle.addEventListener('click', function() { document.body.classList.add('sidebar-collapsed'); try { localStorage.setItem('sidebar-collapsed', '1'); } catch(e) {} });
  if (sidebarReopen) sidebarReopen.addEventListener('click', function() { document.body.classList.remove('sidebar-collapsed'); try { localStorage.setItem('sidebar-collapsed', '0'); } catch(e) {} });

  /* Back to top (throttled scroll) */
  const backToTop = document.getElementById('backToTop');
  var scrollTicking = false;
  window.addEventListener('scroll', function() {
    if (!scrollTicking) { scrollTicking = true; requestAnimationFrame(function() { backToTop.classList.toggle('visible', window.scrollY > 400); scrollTicking = false; }); }
  }, { passive: true });
  backToTop.addEventListener('click', function() { window.scrollTo({ top: 0, behavior: 'smooth' }); });

  /* Sidebar accordion */
  document.querySelectorAll('.sidebar-year').forEach(function(y) {
    y.addEventListener('click', function() {
      toggleYear(y);
      document.querySelectorAll('.sidebar-year.active').forEach(function(ay) { if (ay !== y) { ay.classList.remove('active'); ay.setAttribute('aria-expanded', 'false'); } });
    });
    y.addEventListener('keydown', function(e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); y.click(); } });
  });

  /* ARIA + keyboard for subject headers */
  document.querySelectorAll('.subject-card').forEach(function(card) {
    const header = card.querySelector('.subject-header');
    if (header) {
      header.addEventListener('keydown', function(e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); header.click(); } });
    }
  });

  /* Keyboard shortcuts */
  document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey && e.key === 'k') || (e.key === '/' && !e.target.closest('input,textarea'))) {
      e.preventDefault(); document.getElementById('searchInput').focus();
    }
    if (e.key === 'Escape') {
      /* 搜尋框 Escape */
      if (document.activeElement === document.getElementById('searchInput')) {
        document.getElementById('searchInput').value = ''; doSearch(''); document.getElementById('searchInput').blur();
        return;
      }
      /* 匯出面板 Escape */
      var exportPanel = document.getElementById('exportPanel');
      if (exportPanel && exportPanel.style.display !== 'none') {
        hideExportPanel();
        return;
      }
      /* 手機 sidebar Escape */
      if (sidebar.classList.contains('open')) {
        closeMobileSidebar();
        return;
      }
    }
  });

  /* Populate subject filter */
  if (typeof SUBJECT_KEYS !== 'undefined') {
    const sel = document.getElementById('subjectFilter');
    SUBJECT_KEYS.forEach(function(sk) {
      const opt = document.createElement('option');
      opt.value = sk;
      opt.textContent = sk;
      sel.appendChild(opt);
    });
  }

  initBookmarks();
  initDarkMode();
  handleHash();
  window.addEventListener('hashchange', handleHash);

  /* Pre-build search text cache */
  window._cardTextCache = new Map();
  document.querySelectorAll('#yearView .subject-card').forEach(function(card) {
    window._cardTextCache.set(card, card.textContent.toLowerCase());
  });
});

/* === Bookmarks === */
function getStore(key) { try { return JSON.parse(localStorage.getItem(key)) || {}; } catch(e) { return {}; } }
function setStore(key, val) { try { localStorage.setItem(key, JSON.stringify(val)); } catch(e) {} }

function initBookmarks() {
  const bookmarks = getStore('exam-bookmarks');
  document.querySelectorAll('#yearView .subject-card').forEach(function(card) {
    const id = card.id;
    if (!id) return;
    const header = card.querySelector('.subject-header');
    if (!header) return;
    const bmBtn = document.createElement('button');
    bmBtn.className = 'bookmark-btn' + (bookmarks[id] ? ' active' : '');
    bmBtn.textContent = bookmarks[id] ? '★' : '☆';
    bmBtn.title = '書籤';
    bmBtn.setAttribute('aria-label', '切換書籤');
    bmBtn.setAttribute('aria-pressed', bookmarks[id] ? 'true' : 'false');
    bmBtn.onclick = function(e) {
      e.stopPropagation();
      const bm = getStore('exam-bookmarks');
      if (bm[id]) { delete bm[id]; this.classList.remove('active'); this.textContent = '☆'; }
      else { bm[id] = true; this.classList.add('active'); this.textContent = '★'; }
      this.setAttribute('aria-pressed', bm[id] ? 'true' : 'false');
      setStore('exam-bookmarks', bm);
      const svCard = document.getElementById('sv-' + id);
      if (svCard) { const svBtn = svCard.querySelector('.bookmark-btn'); if (svBtn) { svBtn.classList.toggle('active', !!bm[id]); svBtn.textContent = bm[id] ? '★' : '☆'; } }
    };
    header.appendChild(bmBtn);
    header.removeAttribute('onclick');
    header.addEventListener('click', function(e) { if (e.target.closest('.bookmark-btn')) return; card.classList.toggle('open'); header.setAttribute('aria-expanded', card.classList.contains('open') ? 'true' : 'false'); });
  });
}

let bookmarkFilterActive = false;
function toggleBookmarkFilter() {
  bookmarkFilterActive = !bookmarkFilterActive;
  const btn = document.getElementById('bookmarkFilter');
  btn.classList.toggle('active', bookmarkFilterActive);
  btn.setAttribute('aria-pressed', bookmarkFilterActive ? 'true' : 'false');
  btn.textContent = bookmarkFilterActive ? '顯示全部' : '只看書籤';
  doSearch(document.getElementById('searchInput').value);
}

/* === Dark mode === */
function initDarkMode() {
  const toggle = document.getElementById('darkToggle');
  var saved = null; try { saved = localStorage.getItem('exam-dark'); } catch(e) {}
  if (saved === 'true' || (saved === null && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    document.documentElement.classList.add('dark');
  }
  toggle.addEventListener('click', function() {
    const isDark = document.documentElement.classList.toggle('dark');
    try { localStorage.setItem('exam-dark', isDark); } catch(e) {}
  });
}

/* === 科目瀏覽 (Phase 5) === */
let subjectViewBuilt = false;
function switchView(mode) {
  currentView = mode;
  document.getElementById('yearView').style.display = mode === 'year' ? '' : 'none';
  document.getElementById('subjectView').style.display = mode === 'subject' ? '' : 'none';
  document.getElementById('viewYear').classList.toggle('active', mode === 'year');
  document.getElementById('viewSubject').classList.toggle('active', mode === 'subject');
  if (mode === 'subject' && !subjectViewBuilt) buildSubjectView();
  const q = document.getElementById('searchInput').value;
  if (q.trim() || activeYearFilter) doSearch(q);
  if (bookmarkFilterActive) { bookmarkFilterActive = false; toggleBookmarkFilter(); }
  if (practiceMode) {
    clearAllAnswerState();
    bindOptionClicks();
  }
}

function buildSubjectView() {
  const container = document.getElementById('subjectView');
  const groups = {};
  document.querySelectorAll('#yearView .year-section').forEach(function(ys) {
    const yearText = ys.querySelector('.year-heading').textContent.trim().replace('年', '');
    ys.querySelectorAll('.subject-card').forEach(function(card) {
      const subjectName = card.querySelector('.subject-header h3').textContent.trim();
      if (!groups[subjectName]) groups[subjectName] = [];
      groups[subjectName].push({ year: yearText, card: card });
    });
  });
  const sortedKeys = Object.keys(groups).sort();
  sortedKeys.forEach(function(key) {
    const section = document.createElement('div');
    section.className = 'subject-view-section';
    const heading = document.createElement('h2');
    heading.className = 'sv-heading';
    heading.textContent = key;
    section.appendChild(heading);
    groups[key].forEach(function(item) {
      const clone = item.card.cloneNode(true);
      clone.classList.remove('open');
      const origId = clone.id;
      if (origId) clone.id = 'sv-' + origId;
      clone.setAttribute('data-card-id', origId);
      const header = clone.querySelector('.subject-header h3');
      if (header) {
        const tag = document.createElement('span');
        tag.className = 'sv-year-tag';
        tag.textContent = item.year + '年';
        header.appendChild(tag);
      }
      const hdr = clone.querySelector('.subject-header');
      if (hdr) {
        hdr.removeAttribute('onclick');
        (function(c, h) {
          h.addEventListener('click', function(e) { if (!e.target.closest('.bookmark-btn')) { c.classList.toggle('open'); h.setAttribute('aria-expanded', c.classList.contains('open') ? 'true' : 'false'); } });
        })(clone, hdr);
      }
      const bmBtn = clone.querySelector('.bookmark-btn');
      if (bmBtn) {
        (function(btn, cid) {
          btn.onclick = function(e) {
            e.stopPropagation();
            const bm = getStore('exam-bookmarks');
            if (bm[cid]) { delete bm[cid]; btn.classList.remove('active'); btn.textContent = '☆'; }
            else { bm[cid] = true; btn.classList.add('active'); btn.textContent = '★'; }
            setStore('exam-bookmarks', bm);
            const origCard = document.getElementById(cid);
            if (origCard) {
              const ob = origCard.querySelector('.bookmark-btn');
              if (ob) { ob.classList.toggle('active', !!bm[cid]); ob.textContent = bm[cid] ? '★' : '☆'; }
            }
          };
        })(bmBtn, origId);
      }
      section.appendChild(clone);
    });
    container.appendChild(section);
  });
  subjectViewBuilt = true;
  if (window._cardTextCache) {
    document.querySelectorAll('#subjectView .subject-card').forEach(function(card) {
      window._cardTextCache.set(card, card.textContent.toLowerCase());
    });
  }
}

function filterBySubject(key) {
  const vs = getActiveViewSelector();
  if (!key) {
    document.querySelectorAll(vs + ' .subject-card').forEach(function(c) { c.style.display = ''; });
    document.querySelectorAll(vs + ' .year-section, ' + vs + ' .subject-view-section').forEach(function(s) { s.style.display = ''; });
    return;
  }
  document.querySelectorAll(vs + ' .subject-card').forEach(function(card) {
    const name = card.querySelector('.subject-header h3').textContent.trim();
    card.style.display = name.indexOf(key) !== -1 ? '' : 'none';
  });
  document.querySelectorAll(vs + ' .year-section, ' + vs + ' .subject-view-section').forEach(function(s) {
    s.style.display = s.querySelectorAll('.subject-card:not([style*="display: none"])').length ? '' : 'none';
  });
}

/* === 練習模式 (Phase 6) — 互動式點選 === */
let practiceMode = false;
let practiceCorrect = 0;
let practiceTotal = 0;

function togglePractice() {
  practiceMode = !practiceMode;
  const btn = document.getElementById('practiceToggle');
  const scorePanel = document.getElementById('practiceScore');
  if (practiceMode) {
    document.body.classList.add('practice-mode');
    btn.classList.add('practice-active');
    btn.textContent = '結束練習';
    scorePanel.classList.add('visible');
    var session = getStore('exam-practice-session');
    if (session.url === window.location.pathname && session.ts && Date.now() - session.ts < 3600000) {
      practiceCorrect = session.correct || 0;
      practiceTotal = session.total || 0;
    } else {
      practiceCorrect = 0;
      practiceTotal = 0;
    }
    updateScoreUI();
    bindOptionClicks();
  } else {
    if (practiceTotal > 0) savePracticeScore(practiceCorrect, practiceTotal);
    clearPracticeSession();
    document.body.classList.remove('practice-mode');
    btn.classList.remove('practice-active');
    btn.textContent = '練習模式';
    scorePanel.classList.remove('visible');
    clearAllAnswerState();
  }
}

function bindOptionClicks() {
  document.querySelectorAll('.mc-opt').forEach(function(opt) {
    if (opt._boundClick) return;
    opt._boundClick = true;
    opt.addEventListener('click', function() {
      if (!practiceMode) return;
      var block = opt.closest('.q-block');
      if (!block || block.classList.contains('answered')) return;
      var answer = block.getAttribute('data-answer');
      var chosen = opt.getAttribute('data-val');
      block.classList.add('answered');
      practiceTotal++;
      if (chosen === answer) {
        practiceCorrect++;
        opt.classList.add('correct');
      } else {
        opt.classList.add('wrong');
        block.querySelectorAll('.mc-opt').forEach(function(o) {
          if (o.getAttribute('data-val') === answer) o.classList.add('correct-reveal');
        });
      }
      var ansEl = block.querySelector('.q-answer');
      if (ansEl) ansEl.classList.add('revealed');
      updateScoreUI();
      savePracticeSession();
    });
  });
}

function updateScoreUI() {
  document.getElementById('scoreCorrect').textContent = practiceCorrect;
  document.getElementById('scoreTotal').textContent = practiceTotal;
  var pct = practiceTotal > 0 ? Math.round(practiceCorrect / practiceTotal * 100) : 0;
  document.getElementById('scorePct').textContent = practiceTotal > 0 ? pct + '%' : '--';
}

function clearAllAnswerState() {
  document.querySelectorAll('.q-block').forEach(function(b) {
    b.classList.remove('answered');
  });
  document.querySelectorAll('.mc-opt').forEach(function(o) {
    o.classList.remove('correct', 'wrong', 'correct-reveal', 'selected');
  });
  document.querySelectorAll('.q-answer').forEach(function(a) {
    a.classList.remove('revealed');
  });
}

function resetScore() {
  practiceCorrect = 0;
  practiceTotal = 0;
  updateScoreUI();
  clearPracticeSession();
  clearAllAnswerState();
}

/* === 一般模式：顯示/隱藏全部答案 === */
function toggleAllAnswers(btn) {
  var showing = btn.classList.toggle('active');
  btn.textContent = showing ? '隱藏答案' : '顯示答案';
  document.querySelectorAll('.q-block').forEach(function(b) {
    if (showing) b.classList.add('show-answer');
    else b.classList.remove('show-answer');
  });
}

/* === URL Hash 導航 (Phase 7) === */
function scrollToWithOffset(el) {
  const y = el.getBoundingClientRect().top + window.scrollY - 140;
  window.scrollTo({ top: y, behavior: 'smooth' });
}

function handleHash() {
  const hash = window.location.hash.replace('#', '');
  if (!hash) return;
  if (currentView === 'subject') switchView('year');
  const yearMatch = hash.match(/^year-(\\d+)$/);
  if (yearMatch) {
    const yearEl = document.getElementById('year-' + yearMatch[1]);
    if (yearEl) {
      document.querySelectorAll('.sidebar-year').forEach(function(sy) {
        if (sy.textContent.trim().startsWith(yearMatch[1])) sy.classList.add('active');
      });
      requestAnimationFrame(function() { requestAnimationFrame(function() { scrollToWithOffset(yearEl); }); });
    }
    return;
  }
  const cardEl = document.getElementById(hash);
  if (cardEl && cardEl.classList.contains('subject-card')) {
    cardEl.classList.add('open');
    const hdr = cardEl.querySelector('.subject-header');
    if (hdr) hdr.setAttribute('aria-expanded', 'true');
    const yearSection = cardEl.closest('.year-section');
    if (yearSection) {
      const yNum = yearSection.id.replace('year-', '');
      document.querySelectorAll('.sidebar-year').forEach(function(sy) {
        if (sy.textContent.trim().startsWith(yNum)) sy.classList.add('active');
      });
    }
    requestAnimationFrame(function() { requestAnimationFrame(function() { scrollToWithOffset(cardEl); }); });
  }
}

/* === 練習歷史 (Phase 8) === */
function savePracticeScore(correct, total) {
  const history = getStore('exam-practice-history');
  if (!history.scores) history.scores = [];
  history.scores.unshift({
    correct: correct,
    total: total,
    pct: Math.round(correct / total * 100),
    date: new Date().toISOString()
  });
  if (history.scores.length > 20) history.scores = history.scores.slice(0, 20);
  setStore('exam-practice-history', history);
}

/* === 練習 Session 持久化 === */
function savePracticeSession() {
  if (!practiceMode) return;
  setStore('exam-practice-session', {
    correct: practiceCorrect,
    total: practiceTotal,
    url: window.location.pathname,
    ts: Date.now()
  });
}
function clearPracticeSession() {
  try { localStorage.removeItem('exam-practice-session'); } catch(e) {}
}

/* === 匯出 PDF (Phase 9) === */
function showExportPanel() {
  var panel = document.getElementById('exportPanel');
  var isOpen = panel.style.display !== 'none';
  panel.style.display = isOpen ? 'none' : '';
  /* 手機底部彈出板需要 overlay */
  if (window.innerWidth <= 768) {
    var overlay = document.getElementById('sidebarOverlay');
    if (!isOpen) { overlay.classList.add('active'); overlay.onclick = function() { hideExportPanel(); }; }
    else { overlay.classList.remove('active'); overlay.onclick = function() { var sidebar = document.getElementById('sidebar'); sidebar.classList.remove('open'); overlay.classList.remove('active'); if (document.getElementById('hamburgerBtn')) { document.getElementById('hamburgerBtn').textContent = '\u2630'; document.getElementById('hamburgerBtn').setAttribute('aria-expanded', 'false'); } }; }
  }
}
function hideExportPanel() {
  document.getElementById('exportPanel').style.display = 'none';
  if (window.innerWidth <= 768) { var overlay = document.getElementById('sidebarOverlay'); overlay.classList.remove('active'); }
}
function exportPDF(includeAnswers) {
  hideExportPanel();
  var vs = getActiveViewSelector();
  var cards = document.querySelectorAll(vs + ' .subject-card');
  var otherView = vs === '#yearView' ? '#subjectView' : '#yearView';

  document.querySelector(otherView).classList.add('print-hidden');

  var visibleCount = 0;
  cards.forEach(function(card) {
    if (card.style.display === 'none') {
      card.classList.add('print-hidden');
    } else {
      card.classList.add('open');
      visibleCount++;
    }
  });

  document.querySelectorAll(vs + ' .year-section, ' + vs + ' .subject-view-section').forEach(function(s) {
    if (s.style.display === 'none') s.classList.add('print-hidden');
  });

  if (!includeAnswers) document.body.classList.add('print-no-answers');

  var header = document.createElement('div');
  header.className = 'print-header';
  header.id = 'printHeader';
  var h1 = document.createElement('h1');
  h1.textContent = document.querySelector('.page-title').textContent;
  var info = document.createElement('p');
  var filterInfo = [];
  if (activeYearFilter) filterInfo.push(activeYearFilter + '年');
  var searchVal = document.getElementById('searchInput').value.trim();
  if (searchVal) filterInfo.push('關鍵字: ' + searchVal);
  if (bookmarkFilterActive) filterInfo.push('僅書籤');
  var answerText = includeAnswers ? '含答案' : '不含答案';
  info.textContent = visibleCount + ' 份試卷 \\u00b7 ' + answerText +
    (filterInfo.length ? ' \\u00b7 篩選: ' + filterInfo.join(', ') : '') +
    ' \\u00b7 ' + new Date().toLocaleDateString('zh-TW');
  header.appendChild(h1);
  header.appendChild(info);
  var mainEl = document.querySelector('.main');
  mainEl.insertBefore(header, mainEl.firstChild);

  window.print();

  var _cleaned = false;
  function cleanup() {
    if (_cleaned) return;
    _cleaned = true;
    var h = document.getElementById('printHeader');
    if (h) h.remove();
    document.body.classList.remove('print-no-answers');
    document.querySelectorAll('.print-hidden').forEach(function(el) { el.classList.remove('print-hidden'); });
  }
  if (window.onafterprint !== undefined) {
    window.addEventListener('afterprint', cleanup, { once: true });
  }
  setTimeout(cleanup, 30000);
}
"""


def render_question_html(question):
    """將單一題目渲染為 HTML（含逐題選項與答案）"""
    q = question
    if q['type'] == 'essay':
        stem = escape_html(q['stem']).replace('\n', '<br>')
        return f'<div class="essay-question">{escape_html(q["number"])}、{stem}</div>\n'

    elif q['type'] == 'choice':
        html_parts = []
        answer = q.get('answer', '')
        answer_attr = f' data-answer="{escape_html(answer)}"' if answer else ''

        if q.get('subtype') == 'passage_fragment':
            subtype_attr = f' data-subtype="passage_fragment" role="note" aria-label="閱讀段落"'
        elif q.get('subtype'):
            subtype_attr = f' data-subtype="{q["subtype"]}"'
        else:
            subtype_attr = ''

        # 題目區塊包含題幹、選項、逐題答案
        html_parts.append(
            f'<div class="q-block" data-qnum="{q["number"]}"{answer_attr}>\n'
        )

        # 題幹
        stem_text = escape_html(q.get('stem', ''))
        if stem_text:
            html_parts.append(
                f'<div class="mc-question"{subtype_attr}>'
                f'<span class="q-number">{q["number"]}</span>'
                f'<span class="q-text">{stem_text}</span>'
                f'</div>\n'
            )
        else:
            # 填空題（stem 為空，只有選項）
            html_parts.append(
                f'<div class="mc-question"{subtype_attr}>'
                f'<span class="q-number">{q["number"]}</span>'
                f'</div>\n'
            )

        # 選項（各自一行，可點選）
        if 'options' in q:
            html_parts.append('<div class="mc-options">\n')
            for label in ['A', 'B', 'C', 'D', 'E']:
                if label in q['options']:
                    html_parts.append(
                        f'<div class="mc-opt" data-val="{label}">'
                        f'<span class="opt-label">({label})</span>'
                        f'<span class="opt-text">{escape_html(q["options"][label])}</span>'
                        f'</div>\n'
                    )
            html_parts.append('</div>\n')

        # 逐題答案（預設隱藏）
        if answer:
            if answer == '*':
                ans_display = '送分'
                ans_class = 'q-answer free-point'
            else:
                ans_display = answer
                ans_class = 'q-answer'
            html_parts.append(
                f'<div class="{ans_class}">答案：{escape_html(ans_display)}</div>\n'
            )

        html_parts.append('</div>\n')  # close q-block
        return ''.join(html_parts)

    return ''


def render_subject_card(card_id, subject_name, questions_data, year):
    """渲染一個科目卡片"""
    questions = questions_data.get('questions', [])
    notes = questions_data.get('notes', [])

    choice_count = sum(1 for q in questions if q['type'] == 'choice')
    essay_count = sum(1 for q in questions if q['type'] == 'essay')

    meta_tags = []
    if choice_count:
        meta_tags.append(f'<span class="meta-tag">選擇題 {choice_count} 題</span>')
    if essay_count:
        meta_tags.append(f'<span class="meta-tag">申論題 {essay_count} 題</span>')

    content_html = ''
    if notes:
        for note in notes[:3]:
            content_html += f'<div class="exam-note">{escape_html(note)}</div>\n'

    current_section = None
    rendered_passages = set()
    for q in questions:
        if q.get('section') and q['section'] != current_section:
            current_section = q['section']
            content_html += f'<div class="exam-section-marker">{escape_html(current_section)}</div>\n'
        # 閱讀測驗段落：在題組第一題前顯示段落文字
        passage = q.get('passage', '')
        if passage and passage not in rendered_passages:
            rendered_passages.add(passage)
            content_html += f'<div class="reading-passage">{escape_html(passage)}</div>\n'
        content_html += render_question_html(q)

    # 答案已內嵌在逐題 q-block 中，不再需要底部答案格
    answer_grid_html = ''

    meta_html = '\n'.join(meta_tags)

    return f'''<div class="subject-card" id="{escape_html(card_id)}">
<div class="subject-header" role="button" tabindex="0" aria-expanded="false">
  <h3>{escape_html(subject_name)}</h3>
  <span class="subject-toggle" aria-hidden="true">&#9660;</span>
</div>
<div class="subject-body">
<div class="exam-meta-bar">
{meta_html}
</div>
<div class="exam-content-v2">
{content_html}
</div>
{answer_grid_html}
</div>
</div>
'''


def generate_category_page(category_name, years_data, output_dir):
    """為一個類科生成完整的 HTML 頁面"""
    info = CATEGORIES_INFO.get(category_name, {'code': 0, 'icon': '&#128196;', 'color': '#1a365d'})
    emoji = CATEGORIES_EMOJI.get(category_name, '')
    years = sorted(years_data.keys(), reverse=True)

    total_subjects = sum(len(subjects) for subjects in years_data.values())
    total_questions = 0
    for year_subjects in years_data.values():
        for subj_data in year_subjects.values():
            total_questions += len(subj_data.get('questions', []))

    # Sidebar
    sidebar_html = ''
    for year in years:
        subjects = years_data[year]
        sidebar_html += f'<div class="sidebar-year" role="button" tabindex="0" aria-expanded="false">{year}年</div>\n'
        sidebar_html += '<div class="sidebar-subjects">\n'
        for subj_name in sorted(subjects.keys()):
            card_id = make_card_id(year, subj_name)
            short_name = subj_name[:15]
            sidebar_html += f'<a class="sidebar-link" href="#{card_id}" title="{escape_html(subj_name)}">{escape_html(short_name)}</a>\n'
        sidebar_html += '</div>\n'

    filter_chips = '<button class="filter-chip active" data-year="" onclick="toggleFilter(this,\'year\')">全部年份</button>\n'
    for year in years:
        filter_chips += f'<button class="filter-chip" data-year="{year}" onclick="toggleFilter(this,\'year\')">{year}</button>\n'

    content_html = ''
    for year in years:
        subjects = years_data[year]
        content_html += f'<div class="year-section" id="year-{year}">\n'
        content_html += f'<h2 class="year-heading">{year}年</h2>\n'
        for subj_name in sorted(subjects.keys()):
            card_id = make_card_id(year, subj_name)
            content_html += render_subject_card(card_id, subj_name, subjects[subj_name], year)
        content_html += '</div>\n'

    # 收集科目名稱（跨年份去重）
    subject_keys = sorted(set(
        subj_name for year_subjects in years_data.values()
        for subj_name in year_subjects.keys()
    ))
    subject_keys_json = json.dumps(subject_keys, ensure_ascii=False)
    subject_keys_script = f'<script>const SUBJECT_KEYS={subject_keys_json};</script>'

    page_html = f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>{escape_html(category_name)}考古題總覽 ({years[-1]}-{years[0]}年)</title>
<meta name="description" content="警察特考三等{escape_html(category_name)}考古題總覽，涵蓋{years[-1]}-{years[0]}年共 {total_subjects} 份試卷、{total_questions} 道題目">
<meta name="theme-color" content="{info['color']}">
<meta name="robots" content="index, follow">
<meta property="og:title" content="{escape_html(category_name)}考古題總覽 ({years[-1]}-{years[0]}年)">
<meta property="og:description" content="警察特考三等{escape_html(category_name)}，{years[-1]}-{years[0]}年共 {total_subjects} 份試卷、{total_questions} 道題目">
<meta property="og:type" content="website">
<meta property="og:locale" content="zh_TW">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;600;700;800&amp;display=swap" media="print" onload="this.media='all'">
<noscript><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;600;700;800&amp;display=swap"></noscript>
<link rel="stylesheet" href="../css/style.css">
<script type="application/ld+json">{{
  "@context": "https://schema.org",
  "@type": "CollectionPage",
  "name": "{escape_html(category_name)}考古題總覽",
  "description": "警察特考三等{escape_html(category_name)}考古題，{years[-1]}-{years[0]}年共 {total_subjects} 份試卷",
  "inLanguage": "zh-TW",
  "isPartOf": {{ "@type": "WebSite", "name": "三等警察特考考古題總覽" }}
}}</script>
</head>
<body>
<a href="#searchInput" class="skip-link">跳至搜尋</a>
<button class="hamburger" id="hamburgerBtn" aria-label="開啟導航選單" aria-expanded="false">&#9776;</button>
<div class="sidebar-overlay" id="sidebarOverlay"></div>
<button class="sidebar-reopen" id="sidebarReopen" aria-label="展開導航">&#9776;</button>
<nav class="sidebar" id="sidebar" aria-label="年份導航">
<div class="sidebar-title"><span>{emoji} {escape_html(category_name)}</span><button class="sidebar-toggle" id="sidebarToggle" aria-label="收合導航">&#10005;</button></div>
<a class="sidebar-home" href="../index.html">&#8592; 回到首頁</a>
{sidebar_html}
</nav>
<button class="back-to-top" id="backToTop" aria-label="回到頂部">&#8593;</button>
<button class="dark-toggle" id="darkToggle" aria-label="切換深色模式">
<svg class="dark-icon-moon" viewBox="0 0 24 24" fill="none" stroke="#4a5568" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
<svg class="dark-icon-sun" viewBox="0 0 24 24" fill="none" stroke="#ecc94b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
</button>
<main class="main">
<h1 class="page-title">{escape_html(category_name)}考古題總覽</h1>
<p class="page-subtitle">{years[-1]}年至{years[0]}年 ・ 共 {total_subjects} 份試卷 ・ {total_questions} 題</p>
<div class="stats-bar">
  <div class="stat-item"><div class="stat-value">{len(years)}</div><div class="stat-label">年度</div></div>
  <div class="stat-item"><div class="stat-value">{total_subjects}</div><div class="stat-label">試卷</div></div>
  <div class="stat-item"><div class="stat-value">{total_questions}</div><div class="stat-label">題目</div></div>
</div>
<div class="search-box" role="search" aria-label="考古題內容搜尋">
  <input type="text" class="search-input" id="searchInput" placeholder="搜尋關鍵字..." oninput="debouncedSearch(this.value)" aria-label="搜尋考古題關鍵字" aria-describedby="searchStats">
  <div class="search-filters" id="searchFilters">
{filter_chips}
  </div>
  <div class="search-stats" id="searchStats" aria-live="polite" role="status"><span id="searchStatsText"></span> <span id="searchJump"></span></div>
</div>
<div class="practice-score" id="practiceScore">
  <span class="score-text">答對 <strong id="scoreCorrect">0</strong> / <strong id="scoreTotal">0</strong> 題</span>
  <span class="score-pct" id="scorePct">--</span>
  <button class="score-reset" onclick="resetScore()">重新計分</button>
</div>
<div class="toolbar" id="toolbar" role="toolbar" aria-label="瀏覽工具列">
  <button class="toolbar-btn active" id="viewYear" onclick="switchView('year')">依年份瀏覽</button>
  <button class="toolbar-btn" id="viewSubject" onclick="switchView('subject')">依科目瀏覽</button>
  <span class="toolbar-sep"></span>
  <button class="toolbar-btn" id="practiceToggle" onclick="togglePractice()">練習模式</button>
  <button class="toolbar-btn" id="answerToggle" onclick="toggleAllAnswers(this)">顯示答案</button>
  <button class="toolbar-btn bookmark-filter" id="bookmarkFilter" onclick="toggleBookmarkFilter()" aria-pressed="false">只看書籤</button>
  <span class="toolbar-sep"></span>
  <select class="toolbar-select" id="subjectFilter" aria-label="科目篩選" onchange="filterBySubject(this.value)">
    <option value="">全部科目</option>
  </select>
  <span class="toolbar-sep"></span>
  <button class="toolbar-btn" id="exportBtn" onclick="showExportPanel()" aria-label="匯出 PDF">匯出 PDF</button>
</div>
<div class="export-panel" id="exportPanel" style="display:none" role="dialog" aria-label="匯出設定">
  <p class="export-title">匯出設定</p>
  <button class="export-option" onclick="exportPDF(true)">&#128203; 含答案（複習用）</button>
  <button class="export-option" onclick="exportPDF(false)">&#128221; 不含答案（練習用）</button>
  <button class="export-cancel" onclick="hideExportPanel()">取消</button>
</div>
<div id="yearView">
{content_html}
</div>
<div id="subjectView" style="display:none"></div>
</main>
{subject_keys_script}
<script src="../js/app.js" defer></script>
</body>
</html>'''

    cat_dir = os.path.join(output_dir, category_name)
    os.makedirs(cat_dir, exist_ok=True)
    html_path = os.path.join(cat_dir, f'{category_name}考古題總覽.html')
    try:
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(page_html)
    except OSError as e:
        print(f"  [錯誤] 無法寫入 {html_path}: {e}")
        return None
    return html_path


def generate_index_page(output_dir, categories_stats):
    """生成首頁 index.html"""
    total_papers = sum(s.get('papers', 0) for s in categories_stats.values())
    total_questions = sum(s.get('questions', 0) for s in categories_stats.values())
    total_categories = len(categories_stats)

    # 分組定義
    CATEGORY_GROUPS = [
        ('行政法制', '&#9965;', '#2563eb', ['行政警察', '行政管理', '警察法制', '資訊管理']),
        ('刑事鑑識', '&#128270;', '#d97706', ['刑事警察', '鑑識科學', '公共安全']),
        ('犯罪防治', '&#128275;', '#e11d48', ['犯罪防治預防組', '犯罪防治矯治組']),
        ('交通消防', '&#128678;', '#dc2626', ['交通警察交通組', '交通警察電訊組', '消防警察']),
        ('涉外國境', '&#127760;', '#0d9488', ['外事警察', '國境警察', '水上警察']),
    ]

    groups_html = ''
    for group_name, group_icon, group_color, members in CATEGORY_GROUPS:
        items_html = ''
        for cat_name in members:
            if cat_name not in categories_stats:
                continue
            emoji = CATEGORIES_EMOJI.get(cat_name, '')
            stats = categories_stats[cat_name]
            items_html += f'''
        <li><a href="{cat_name}/{cat_name}考古題總覽.html"><span class="item-icon">{emoji}</span><span class="item-name">{escape_html(cat_name)}</span><span class="item-count">{stats.get('questions', 0)} 題</span><span class="item-arrow">&#8594;</span></a></li>'''
        if items_html:
            groups_html += f'''
    <div class="group-section" style="--group-color: {group_color}">
      <div class="group-header"><span class="group-header-icon">{group_icon}</span> {group_name}</div>
      <ul class="group-list">{items_html}
      </ul>
    </div>'''

    index_html = f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>三等警察特考考古題總覽</title>
<meta name="description" content="三等警察特考（內軌）全部 {total_categories} 個類科考古題總覽，共 {total_papers} 份試卷、{total_questions} 道題目">
<meta name="theme-color" content="#2563eb">
<meta name="robots" content="index, follow">
<meta property="og:title" content="三等警察特考考古題總覽">
<meta property="og:description" content="三等警察特考（內軌）{total_categories} 個類科，{total_papers} 份試卷，{total_questions} 道題目">
<meta property="og:type" content="website">
<meta property="og:locale" content="zh_TW">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;600;700;800&amp;display=swap" media="print" onload="this.media='all'">
<noscript><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;600;700;800&amp;display=swap"></noscript>
<style>
:root {{ --primary: #2563eb; --primary-light: #3b82f6; --accent: #6366f1; --bg: #f8fafc; --card-bg: #ffffff; --border: #e2e8f0; --text: #1e293b; --text-light: #64748b; --gold: #fbbf24; --shadow-sm: 0 1px 2px rgba(0,0,0,0.05); --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -2px rgba(0,0,0,0.05); --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.08), 0 4px 6px -4px rgba(0,0,0,0.05); }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: "Noto Sans TC", "Microsoft JhengHei", -apple-system, sans-serif; background: var(--bg); color: var(--text); line-height: 1.7; min-height: 100vh; -webkit-font-smoothing: antialiased; }}
.site-header {{ background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 50%, #6366f1 100%); color: #fff; padding: 3.5rem 2rem; text-align: center; }}
.site-title {{ font-size: 2.2rem; font-weight: 800; margin-bottom: 0.5rem; text-shadow: 0 2px 4px rgba(0,0,0,0.15); letter-spacing: 0.05em; }}
.site-subtitle {{ font-size: 1rem; opacity: 0.85; margin-bottom: 2rem; }}
.hero-stats {{ display: inline-flex; justify-content: center; gap: 3rem; flex-wrap: wrap; backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); background: rgba(255,255,255,0.1); border-radius: 16px; border: 1px solid rgba(255,255,255,0.2); padding: 1.5rem 2.5rem; }}
.hero-stat {{ text-align: center; }}
.hero-stat-value {{ font-size: 2.5rem; font-weight: 800; color: #fbbf24; text-shadow: 0 1px 3px rgba(0,0,0,0.2); }}
.hero-stat-label {{ font-size: 0.85rem; opacity: 0.85; }}
.container {{ max-width: 960px; margin: 0 auto; padding: 2rem 1.5rem; }}
.section-title {{ font-size: 1.3rem; font-weight: 700; color: var(--primary); border-bottom: 3px solid var(--accent); padding-bottom: 0.5rem; margin-bottom: 1.25rem; }}
.groups-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.25rem; }}
.group-section {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 14px; overflow: hidden; box-shadow: var(--shadow-sm); }}
.group-header {{ display: flex; align-items: center; gap: 0.5rem; padding: 0.75rem 1.25rem; font-size: 0.85rem; font-weight: 700; color: var(--text-light); text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid var(--border); background: color-mix(in srgb, var(--group-color, var(--primary)) 5%, var(--card-bg)); }}
.group-header-icon {{ font-size: 0.9rem; }}
.group-list {{ list-style: none; }}
.group-list li {{ border-bottom: 1px solid var(--border); }}
.group-list li:last-child {{ border-bottom: none; }}
.group-list a {{ display: flex; align-items: center; gap: 0.75rem; padding: 0.7rem 1.25rem; text-decoration: none; color: var(--text); transition: background 0.15s ease, padding-left 0.15s ease; }}
.group-list a:hover {{ background: color-mix(in srgb, var(--group-color, var(--primary)) 6%, transparent); padding-left: 1.5rem; }}
.item-icon {{ font-size: 1.3rem; flex-shrink: 0; width: 28px; text-align: center; }}
.item-name {{ flex: 1; font-size: 0.95rem; font-weight: 600; }}
.item-count {{ font-size: 0.78rem; color: var(--text-light); white-space: nowrap; }}
.item-arrow {{ font-size: 0.9rem; color: var(--border); transition: color 0.15s ease, transform 0.15s ease; }}
.group-list a:hover .item-arrow {{ color: var(--accent); transform: translateX(3px); }}
.site-footer {{ text-align: center; padding: 2rem; font-size: 0.82rem; color: var(--text-light); border-top: 1px solid var(--border); margin-top: 3rem; }}
.dark-toggle {{ position: fixed; bottom: 2rem; left: 2rem; z-index: 200; width: 44px; height: 44px; border-radius: 50%; background: var(--card-bg); border: 2px solid var(--border); cursor: pointer; display: flex; align-items: center; justify-content: center; box-shadow: var(--shadow-md); transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }}
.dark-toggle:hover {{ border-color: var(--accent); transform: scale(1.1); }}
.dark-toggle svg {{ width: 22px; height: 22px; transition: transform 0.5s cubic-bezier(0.4, 0, 0.2, 1); }}
.dark-toggle:active svg {{ transform: rotate(360deg); }}
.dark-icon-moon, .dark-icon-sun {{ display: block; }}
html.dark .dark-icon-moon {{ display: none; }}
html:not(.dark) .dark-icon-sun {{ display: none; }}
html.dark {{ --primary: #818cf8; --primary-light: #6366f1; --accent: #a5b4fc; --bg: #0f172a; --card-bg: #1e293b; --border: #334155; --text: #f1f5f9; --text-light: #94a3b8; --gold: #fbbf24; --shadow-sm: 0 1px 2px rgba(0,0,0,0.2); --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.3), 0 2px 4px -2px rgba(0,0,0,0.2); --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.4), 0 4px 6px -4px rgba(0,0,0,0.3); }}
html.dark .site-header {{ background: linear-gradient(135deg, #020617 0%, #1e1b4b 50%, #312e81 100%); }}
html.dark .group-section {{ background: #1e293b; border-color: #334155; }}
html.dark .group-header {{ background: color-mix(in srgb, var(--group-color, var(--primary)) 8%, #1e293b); border-color: #334155; }}
html.dark .group-list li {{ border-color: #334155; }}
html.dark .group-list a:hover {{ background: color-mix(in srgb, var(--group-color, var(--primary)) 10%, transparent); }}
html.dark .dark-toggle {{ background: #1e293b; border-color: #334155; }}
a, button, input, select, [role="button"] {{ touch-action: manipulation; -webkit-tap-highlight-color: transparent; }}
body {{ overflow-x: hidden; }}
@media (prefers-reduced-motion: reduce) {{ *, *::before, *::after {{ animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }} }}
@media (max-width: 768px) {{ .site-header {{ padding: 2rem 1.5rem; }} .site-title {{ font-size: 1.6rem; letter-spacing: 0.03em; }} .site-subtitle {{ font-size: 0.88rem; margin-bottom: 1.25rem; }} .hero-stats {{ gap: 1.5rem; padding: 1rem 1.5rem; border-radius: 12px; }} .hero-stat-value {{ font-size: 1.8rem; }} .groups-grid {{ grid-template-columns: 1fr; }} .container {{ padding: 1.5rem 1rem; }} .dark-toggle {{ bottom: 1.5rem; left: 1.5rem; }} }}
@supports (padding: env(safe-area-inset-bottom)) {{ @media (max-width: 768px) {{ .dark-toggle {{ bottom: calc(1.5rem + env(safe-area-inset-bottom)); }} .site-footer {{ padding-bottom: calc(2rem + env(safe-area-inset-bottom)); }} }} }}
@media (max-width: 768px) and (orientation: landscape) {{ .site-header {{ padding: 1.5rem; }} .hero-stat-value {{ font-size: 1.5rem; }} .hero-stats {{ gap: 1rem; padding: 0.75rem 1.25rem; }} }}
.skip-link {{ position: absolute; top: -100%; left: 1rem; background: var(--primary); color: #fff; padding: 0.5rem 1rem; border-radius: 0 0 6px 6px; z-index: 999; text-decoration: none; font-size: 0.9rem; }}
.skip-link:focus {{ top: 0; }}
</style>
<script type="application/ld+json">{{
  "@context": "https://schema.org",
  "@type": "WebSite",
  "name": "三等警察特考考古題總覽",
  "description": "三等警察特考（內軌）{total_categories} 個類科考古題總覽",
  "inLanguage": "zh-TW"
}}</script>
</head>
<body>
<a href="#categories" class="skip-link">跳至類科列表</a>
<header class="site-header">
  <h1 class="site-title">三等警察特考考古題總覽</h1>
  <p class="site-subtitle">內軌 {total_categories} 個類科完整試題庫</p>
  <div class="hero-stats">
    <div class="hero-stat"><div class="hero-stat-value">{total_categories}</div><div class="hero-stat-label">類科</div></div>
    <div class="hero-stat"><div class="hero-stat-value">{total_papers}</div><div class="hero-stat-label">試卷</div></div>
    <div class="hero-stat"><div class="hero-stat-value">{total_questions}</div><div class="hero-stat-label">題目</div></div>
  </div>
</header>
<main class="container">
  <h2 class="section-title">選擇類科</h2>
  <nav aria-label="類科導航">
  <div class="groups-grid" id="categories">{groups_html}
  </div>
  </nav>
</main>
<footer class="site-footer">
  資料來源：考選部考畢試題查詢平臺 ・ 生成時間：{datetime.now().strftime('%Y-%m-%d')}
</footer>
<button class="dark-toggle" id="darkToggle" aria-label="切換深色模式">
<svg class="dark-icon-moon" viewBox="0 0 24 24" fill="none" stroke="#4a5568" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
<svg class="dark-icon-sun" viewBox="0 0 24 24" fill="none" stroke="#ecc94b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
</button>
<script>
(function() {{
  const toggle = document.getElementById('darkToggle');
  var saved = null; try {{ saved = localStorage.getItem('exam-dark'); }} catch(e) {{}}
  if (saved === 'true' || (saved === null && window.matchMedia('(prefers-color-scheme: dark)').matches)) {{
    document.documentElement.classList.add('dark');
  }}
  toggle.addEventListener('click', function() {{
    const isDark = document.documentElement.classList.toggle('dark');
    try {{ localStorage.setItem('exam-dark', isDark); }} catch(e) {{}}
  }});
}})();
</script>
</body>
</html>'''

    index_path = os.path.join(output_dir, 'index.html')
    try:
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(index_html)
    except OSError as e:
        print(f"  [錯誤] 無法寫入 {index_path}: {e}")
        return None
    return index_path


def collect_json_data(input_dir):
    """從 JSON 檔案收集所有題目資料"""
    input_dir = Path(input_dir)
    all_data = defaultdict(lambda: defaultdict(dict))
    categories_set = set(CATEGORIES_ORDER)

    json_files = sorted(input_dir.rglob('試題.json'))
    if not json_files:
        json_files = sorted(input_dir.rglob('*.json'))
        json_files = [f for f in json_files if f.name not in
                      ('download_summary.json', 'extraction_stats.json', '失敗清單.json')]

    for json_path in json_files:
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"  [警告] JSON 解析失敗: {json_path}: {e}")
            continue

        if not data.get('questions'):
            continue

        category = ''
        year = 0
        subject = normalize_parens(data.get('subject', json_path.parent.name))

        # 路徑推斷（優先）
        for part in json_path.parts:
            if part in categories_set:
                category = part
            m = re.match(r'(\d{3})年$', part)
            if m:
                year = int(m.group(1))

        # 回退：路徑推斷失敗時，使用 JSON 內的 category / year
        if not category:
            json_cat = data.get('category', '')
            if json_cat in categories_set:
                category = json_cat
        if not year:
            raw_year = data.get('year', 0)
            if isinstance(raw_year, int) and raw_year > 0:
                year = raw_year
            elif isinstance(raw_year, str):
                ym = re.match(r'(\d{2,3})', raw_year)
                if ym:
                    year = int(ym.group(1))

        if category and year:
            all_data[category][year][subject] = data

    return all_data


def main():
    parser = argparse.ArgumentParser(description='HTML 生成器')
    parser.add_argument('--input', '-i', type=str,
                        default=os.path.join(os.path.dirname(__file__), '考古題庫'),
                        help='JSON 資料目錄')
    parser.add_argument('--output', '-o', type=str,
                        default=os.path.join(os.path.dirname(__file__), '考古題網站'),
                        help='HTML 輸出目錄')
    parser.add_argument('--category', '-c', type=str, default=None,
                        help='只生成指定類科')
    args = parser.parse_args()

    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("  HTML 生成器 — 考古題靜態網站")
    print("=" * 60)

    css_dir = os.path.join(output_dir, 'css')
    js_dir = os.path.join(output_dir, 'js')
    os.makedirs(css_dir, exist_ok=True)
    os.makedirs(js_dir, exist_ok=True)

    css_path = os.path.join(css_dir, 'style.css')
    if not os.path.exists(css_path):
        with open(css_path, 'w', encoding='utf-8') as f:
            f.write(generate_shared_css())
        print(f"  CSS: {css_path} (generated)")
    else:
        print(f"  CSS: {css_path} (existing, skipped)")

    js_path = os.path.join(js_dir, 'app.js')
    if not os.path.exists(js_path):
        with open(js_path, 'w', encoding='utf-8') as f:
            f.write(generate_shared_js())
        print(f"  JS:  {js_path} (generated)")
    else:
        print(f"  JS:  {js_path} (existing, skipped)")

    print(f"\n讀取資料: {args.input}")
    all_data = collect_json_data(args.input)

    if not all_data:
        print("  未找到任何 JSON 題目資料！")
        print("  請先執行:")
        print("    1. python download_all_categories.py  # 下載 PDF")
        print("    2. python pdf_to_questions.py          # PDF 轉 JSON")
        return

    print(f"\n生成 HTML 頁面:")
    categories_stats = {}

    for cat_name in CATEGORIES_ORDER:
        if cat_name not in all_data:
            continue
        if args.category and cat_name != args.category:
            continue

        years_data = all_data[cat_name]
        html_path = generate_category_page(cat_name, years_data, output_dir)

        total_papers = sum(len(subjects) for subjects in years_data.values())
        total_questions = sum(
            len(subj.get('questions', []))
            for subjects in years_data.values()
            for subj in subjects.values()
        )
        year_list = sorted(years_data.keys())

        categories_stats[cat_name] = {
            'years': len(year_list),
            'min_year': min(year_list),
            'max_year': max(year_list),
            'papers': total_papers,
            'questions': total_questions,
        }

        print(f"  {cat_name}: {total_papers} 份試卷, {total_questions} 題 -> {html_path}")

    if not args.category:
        index_path = generate_index_page(output_dir, categories_stats)
        print(f"\n首頁: {index_path}")

    print(f"\n完成！網站位於: {os.path.abspath(output_dir)}")
    print(f"在瀏覽器開啟 {os.path.join(output_dir, 'index.html')} 即可瀏覽")


if __name__ == "__main__":
    main()
