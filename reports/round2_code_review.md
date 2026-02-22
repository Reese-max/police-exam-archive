# Round 2 程式碼驗證審查報告

**審查日期**: 2026-02-22
**審查範圍**: style.css, app.js, index.html, 行政警察考古題總覽.html, generate_html.py
**審查目標**: 驗證 Round 1 的 17 項修復是否正確實施，並找出新引入問題與遺漏

---

## A. Round 1 修復驗證（17 項）

### 通過 (PASS) - 17/17

| # | 修復項目 | 驗證結果 | 證據 |
|---|---------|---------|------|
| 1 | `--text-light: #4a5a6e`（>=4.5:1 對比度） | PASS | style.css:9 確認 `--text-light: #4a5a6e`；generate_html.py:102 也同步為 `#4a5a6e` |
| 2 | `--accent: #3182ce`（統一） | PASS | style.css:4 確認 `--accent: #3182ce`；generate_html.py:97 同步 |
| 3 | `.sidebar-home` 無重複 `display` | PASS | style.css:22 只有一個 `display: flex`，無重複宣告 |
| 4 | `.sidebar-link min-height: 44px` | PASS | style.css:29 確認 `min-height: 44px`；generate_html.py:122 同步 |
| 5 | `.answer-cell` 不在深色模式 transition 列表中 | PASS | style.css:205 的過渡列表不含 `.answer-cell`；line 138 的 `transition: all 0.15s` 是用於 hover 效果，屬正常 |
| 6 | `body overflow-x: hidden` | PASS | style.css:19 確認 `overflow-x: hidden`；generate_html.py:112 同步 |
| 7 | search-jump button `min-height: 44px`（手機版） | PASS | style.css:132 手機版 `.search-jump button { min-height: 44px; }`；style.css:158 桌面版也有 `min-height: 44px; min-width: 44px` |
| 8 | 搜尋索引 `_cardTextCache`（Map） | PASS | app.js:277-280 在 DOMContentLoaded 中建立 `window._cardTextCache = new Map()`，遍歷 `#yearView .subject-card` 填充快取 |
| 9 | `highlightText` 全匹配（loop） | PASS | app.js:15-38 使用 while 迴圈找出所有匹配，而非只處理第一個 |
| 10 | 書籤 `aria-label` + `aria-pressed` | PASS | app.js:298-299 設定 `aria-label='切換書籤'` 和 `aria-pressed`；app.js:305 更新 `aria-pressed` |
| 11 | 搜尋跳轉 `aria-label` | PASS | app.js:153 `prevBtn.setAttribute('aria-label', '上一個匹配')`；app.js:162 `nextBtn.setAttribute('aria-label', '下一個匹配')` |
| 12 | `toggleCard` 死碼移除 | PASS | app.js 中搜尋 `toggleCard` 無結果，已完全移除 |
| 13 | `exportPDF` cleanup 防重複（`_cleaned`） | PASS | app.js:647-650 使用 `_cleaned` 旗標防止 cleanup 重複執行 |
| 14 | `sidebar-link` 有 `title` 屬性 | PASS | generate_html.py:1108 確認 `title="{escape_html(subj_name)}"`；行政警察頁面 line 25-31 每個 sidebar-link 都有 title |
| 15 | 首頁 `skip-link` + `id="categories"` | PASS | index.html:54 `<a href="#categories" class="skip-link">跳至類科列表</a>`；index.html:67 `id="categories"`；generate_html.py:1305 同步 |
| 16 | Google Fonts 非阻塞（`media="print" onload`） | PASS | index.html:11 `media="print" onload="this.media='all'"`；index.html:12 有 `<noscript>` 回退；generate_html.py:1143-1144、1262-1263 同步 |
| 17 | `@media print` 合併 | PASS | style.css:81 只有一個 `@media print` 區塊，所有列印規則合併在一起；generate_html.py:174 同步 |

---

## B. 新引入問題分析

### B1. `_cardTextCache` 在科目瀏覽模式下的行為

**嚴重度**: 低（效能退化，非功能錯誤）

`_cardTextCache` 只在 DOMContentLoaded 時快取 `#yearView .subject-card`（app.js:278）。科目瀏覽模式的卡片是 `buildSubjectView()` 透過 `cloneNode(true)` 建立的（app.js:379），這些 clone 不在 Map 中。

**影響**: 科目瀏覽模式下搜尋時，`doSearch()` 中的快取查詢會 miss（app.js:117），退回到 `card.textContent.toLowerCase()` 即時計算。功能正確，只是少了快取加速。

**建議**: 可在 `buildSubjectView()` 結束後，將 clone 卡片也加入 `_cardTextCache`。但考慮到科目瀏覽模式只在使用者點擊後才建立，且只建立一次，影響有限。**不阻塞發布**。

### B2. `highlightText` 空字串風險

**嚴重度**: 無風險

分析 app.js 的呼叫鏈：
1. `doSearch()` 在 app.js:121 有 `if (query.trim())` 守衛，只有非空 query 才會呼叫 `highlightText`
2. `highlightText()` 內部 app.js:21 `indexOf(lowerQuery)` 對空字串會回傳 0，理論上可能無限迴圈
3. 但由於外部守衛存在，空字串不會傳入，**無實際風險**

**建議**: 可在 `highlightText` 入口加防禦性檢查 `if (!query) return 0;` 作為深度防禦，但非必要。

### B3. Google Fonts onload handler 瀏覽器相容性

**嚴重度**: 無風險

`media="print" onload="this.media='all'"` 配合 `<noscript>` 回退是業界標準做法（CSS-Tricks / web.dev 推薦）。所有現代瀏覽器（Chrome 50+, Firefox 55+, Safari 11+, Edge 79+）都支援。有 `<noscript>` 回退確保 JS 禁用時字體仍能載入。**無問題**。

### B4. 首頁 skip-link CSS 是否在行內 style 中正確加入

**嚴重度**: 無問題

index.html:49-50 在 `<style>` 區塊中正確定義了 `.skip-link` 和 `.skip-link:focus` 規則。類科頁面使用外部 style.css:79-80 的相同規則。generate_html.py:1300-1301 也同步。**三處一致，無遺漏**。

---

## C. 遺漏的改進空間

### C1. inline onclick 使用情況

**嚴重度**: 低（程式碼風格，非功能問題）

類科頁面 HTML 中仍有大量 inline onclick：
- `toggleFilter(this,'year')` — 年份篩選按鈕（每個類科 ~10 個）
- `switchView('year')` / `switchView('subject')` — 瀏覽模式切換
- `togglePractice()` — 練習模式
- `toggleBookmarkFilter()` — 書籤篩選
- `resetScore()` — 重新計分
- `showExportPanel()` / `exportPDF()` / `hideExportPanel()` — 匯出功能
- `filterBySubject(this.value)` — onchange 事件
- `debouncedSearch(this.value)` — oninput 事件

Round 1 已將 subject-header 的 onclick 移至 addEventListener（app.js:311-312），但工具列按鈕等仍使用 inline onclick。

**評估**: 這些 inline onclick 都呼叫全域函式，且參數明確，CSP 環境下不存在注入風險（靜態網站無使用者輸入拼接）。完全移除 inline onclick 是大規模重構，投入產出比低。**不建議在本輪處理**。

### C2. 全域變數封裝

**現況**: app.js 使用以下全域變數：
- `activeYearFilter`、`searchHits`、`currentHitIdx`、`currentView` — 搜尋狀態
- `bookmarkFilterActive` — 書籤篩選
- `practiceMode`、`practiceCorrect`、`practiceTotal` — 練習模式
- `subjectViewBuilt` — 科目瀏覽
- `window._cardTextCache` — 搜尋快取

**評估**: 靜態網站單一 JS 檔案，無第三方庫衝突風險。使用 IIFE 或 ES module 封裝是好的實踐，但對此專案而言收益有限。**不建議在本輪處理**。

### C3. 其他效能優化機會

1. **科目瀏覽快取補充**（同 B1）：在 `buildSubjectView()` 結尾補充 `_cardTextCache`
2. **`sections.forEach` 可見性檢查**：`doSearch()` 中每次都用 `querySelectorAll(':not([style*="display: none"])')` 做可見性檢查，可考慮改用計數器，但實際 DOM 數量有限（~70 張卡片），效能已足夠
3. **`make_card_id` 中文科目名**：`re.sub(r'[^a-zA-Z0-9_]', '', ...)` 會移除所有中文字元，導致大部分科目名最終走 hashlib 路徑。建議加入中文 Unicode 範圍 `[^a-zA-Z0-9_\u4e00-\u9fff]` 以產生更可讀的 ID。但這不影響功能正確性。

### C4. 小型改進建議（非阻塞）

| 建議 | 影響 | 優先級 |
|------|------|--------|
| `highlightText` 加入空字串防禦 | 深度防禦 | 低 |
| 科目瀏覽卡片加入 `_cardTextCache` | 效能微幅提升 | 低 |
| `make_card_id` 支援中文字元 | 可讀性提升 | 低 |
| 書籤按鈕的 `aria-pressed` 在科目瀏覽 clone 中保持同步 | 無障礙完整性 | 低 |

---

## D. 結論

**Round 1 的 17 項修復全數通過驗證**，實施品質良好，CSS / JS / HTML / generate_html.py 四處保持一致。

**未發現嚴重的新引入問題**。B1（科目瀏覽快取 miss）和 B2（空字串理論風險）都有外部守衛保護，不影響功能正確性。

**遺漏項目**（inline onclick、全域變數封裝）屬於程式碼風格層級，對靜態考古題網站的實際影響極低，不建議在本輪重構。

**審查結論: PASS — 可以發布。**
