# Round 1 程式碼審查報告

**審查日期**: 2026-02-22
**審查範圍**: style.css (233 行), app.js (641 行), index.html (283 行), 類科頁面 HTML (行政警察, 3326 行)
**生成器**: generate_html.py

---

## 問題總覽

| # | 嚴重度 | 類別 | 問題描述 | 檔案:行號 |
|---|--------|------|---------|-----------|
| 1 | Critical | 效能 | 搜尋使用 `card.textContent` 全文比對，18569 題時可能嚴重卡頓 | app.js:112 |
| 2 | Critical | 效能 | `buildSubjectView()` 用 `cloneNode(true)` 複製全部卡片，DOM 節點倍增 | app.js:342-403 |
| 3 | High | 安全 | Google Fonts 外部資源無 `integrity` / `crossorigin` 屬性 | 類科 HTML:11 |
| 4 | High | 效能 | Google Fonts 為 render-blocking 資源，延遲首屏渲染 | 類科 HTML:9-11 |
| 5 | High | CSS | `--accent` 在 style.css 和 index.html 定義值不同（`#2b6cb0` vs `#3182ce`） | style.css:4 / index.html:13 |
| 6 | High | 效能 | 深色模式過渡 transition 套用在大量元素上，切換時可能觸發大規模重繪 | style.css:205 |
| 7 | Medium | JS | 7 個全域變數暴露在 window 下，可能與其他腳本衝突 | app.js:35,45-47,300,324,422-424 |
| 8 | Medium | CSS | `.sidebar-home` 重複宣告 `display` 屬性（`block` 後又 `flex`） | style.css:22 |
| 9 | Medium | HTML | `filter-chip` 按鈕使用 inline `onclick`，與 JS 中 addEventListener 風格不一致 | 類科 HTML:130-139 |
| 10 | Medium | 無障礙 | 書籤按鈕缺少 `aria-label`，螢幕閱讀器只會讀到星號字元 | app.js:282-284 |
| 11 | Medium | 無障礙 | 搜尋跳轉按鈕 (`prevBtn`, `nextBtn`) 缺少 `aria-label` | app.js:145-155 |
| 12 | Medium | CSS | 色彩對比度不足：`--text-light: #5a6a7e` 在白色背景上約 4.2:1，未達 WCAG AA 4.5:1 | style.css:9 |
| 13 | Medium | 效能 | `highlightText` 遞迴走訪 DOM 只標記首次匹配，非全部匹配 | app.js:16-33 |
| 14 | Medium | JS | `exportPDF` 的 cleanup 靠 `setTimeout(5000)` 保底，不可靠 | app.js:640 |
| 15 | Low | CSS | 命名不一致：混用 BEM 片段（`btn-correct`）和功能命名（`practice-active`） | style.css 多處 |
| 16 | Low | HTML | index.html 首頁缺少 `<main>` 的 skip-link | index.html |
| 17 | Low | HTML | 首頁 `<footer>` 使用全形中間點 `・` 但未標記 `lang` 屬性 | index.html:263 |
| 18 | Low | JS | `toggleCard` 函式已定義但未被呼叫（死碼） | app.js:7 |
| 19 | Low | CSS | 列印 CSS 有兩個 `@media print` 區塊，可合併 | style.css:81,232 |
| 20 | Low | 邊界 | sidebar-link 文字被 `text-overflow: ellipsis` 截斷但無 `title` 提示完整名稱 | 類科 HTML:28 |
| 21 | Info | CSS | CSS/JS 未 minify，可壓縮約 30-40% 體積 | style.css, app.js |
| 22 | Info | 效能 | scroll 事件監聽未做節流（back-to-top 按鈕） | app.js:208 |

---

## 詳細問題

### [Critical] #1 — 搜尋效能：全文 textContent 比對

- **類別**: 效能 / JS
- **檔案**: `app.js:112`
- **問題**: `doSearch()` 對每張卡片執行 `card.textContent.toLowerCase()`，這會遍歷整個 DOM 子樹產生字串。以行政警察 63 份試卷、1825 題為例，每次按鍵都要遍歷大量 DOM 節點。18569 題的完整網站若全放一頁，效能將非常差。加上 `highlightText()` 遞迴走訪 DOM，搜尋時的計算量是 O(n*m)，n 為卡片數，m 為平均 DOM 深度。
- **影響**: 使用者輸入搜尋時可能出現明顯延遲（>200ms），尤其在低階裝置上。
- **建議修復**:
```javascript
// 在 DOMContentLoaded 時預建搜尋索引
const searchIndex = [];
document.querySelectorAll('.subject-card').forEach(card => {
  searchIndex.push({
    el: card,
    text: card.textContent.toLowerCase()
  });
});

// doSearch 中使用索引
searchIndex.forEach(item => {
  const match = !query || item.text.includes(queryLower);
  // ...
});
```

---

### [Critical] #2 — buildSubjectView 複製全部 DOM 導致節點倍增

- **類別**: 效能 / JS
- **檔案**: `app.js:342-403`
- **問題**: `buildSubjectView()` 使用 `cloneNode(true)` 深拷貝每張 subject-card，包含所有題目、選項、答案格。以行政警察 63 份卡片為例，切換到「科目瀏覽」後 DOM 節點數直接翻倍。如果每張卡片平均有 ~200 個 DOM 節點，63 張就多出 ~12,600 個節點。對有 910 份試卷的完整資料集而言更為嚴重。
- **影響**: 記憶體使用量大幅增加；切換瀏覽模式時可能有明顯延遲。
- **建議修復**:
```javascript
// 方案 A: 延遲載入 — 僅在卡片展開時才複製內容
// 方案 B: 共享 DOM — 切換瀏覽時移動而非複製卡片
// 方案 C: 虛擬列表 — 只渲染視窗範圍內的卡片
```

---

### [High] #3 — Google Fonts 外部資源缺少完整性驗證

- **類別**: 安全
- **檔案**: 類科 HTML:11, index.html:11
- **問題**: 載入 Google Fonts 的 `<link>` 標籤缺少 `integrity`（SRI）屬性。雖然 Google Fonts 是可信來源，但若 CDN 被入侵或 DNS 劫持，可注入惡意 CSS。同時 `<link>` 元素缺少 `crossorigin` 屬性（只有 preconnect 有）。
- **注意**: Google Fonts 目前不支援 SRI（因為 CSS 回應依 User-Agent 動態生成），所以這是已知限制而非程式碼缺陷。
- **建議修復**:
```html
<!-- 最安全做法：自行託管字型檔案 -->
<!-- 或至少加上 crossorigin="anonymous" -->
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC..."
      rel="stylesheet" crossorigin="anonymous">
```

---

### [High] #4 — Google Fonts render-blocking

- **類別**: 效能
- **檔案**: 類科 HTML:9-11, index.html:9-11
- **問題**: `<link rel="stylesheet" href="...fonts.googleapis.com...">` 是 render-blocking 資源。字型 CSS 下載完成前，瀏覽器不會渲染頁面。雖然已有 `preconnect`，但在低速網路下仍會導致白屏。
- **建議修復**:
```html
<!-- 方案 A: media="print" hack + onload swap -->
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;600;700;800&display=swap"
      media="print" onload="this.media='all'">
<noscript><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;600;700;800&display=swap"></noscript>

<!-- 方案 B: 自行託管字型，使用 font-display: swap -->
```

---

### [High] #5 — CSS 變數 `--accent` 定義值不一致

- **類別**: CSS
- **檔案**: `style.css:4` / `index.html:13`
- **問題**: style.css 中 `:root` 定義 `--accent: #2b6cb0`（與 `--primary-light` 相同），而 index.html 行內 CSS 定義 `--accent: #3182ce`。兩者色值不同，導致首頁和類科頁面的 accent 色存在差異。
- **建議修復**: 統一為同一個色值（建議 `#3182ce`，它在可辨識性上稍優）。

---

### [High] #6 — 深色模式過渡 transition 作用在大量元素上

- **類別**: 效能 / CSS
- **檔案**: `style.css:203-205`
- **問題**: 三行 CSS 對 `body`, `.sidebar`, 以及大量元素（`.subject-card, .stats-bar, .exam-metadata, .answer-section, .answer-cell, .search-input, .toolbar-btn, .filter-chip, .dark-toggle, .back-to-top, .toolbar-select, .practice-score, .self-score-panel`）全部套用 `transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease`。
- **影響**: 每次深色模式切換時，瀏覽器需要對數百個 `.answer-cell` 和 `.subject-card` 計算過渡動畫，可能造成卡頓。尤其在 63 份卷 * 平均 30 個 answer-cell = ~1890 個元素同時執行 transition。
- **建議修復**:
```css
/* 移除 .answer-cell 的 transition（數量最多、視覺效果最不明顯） */
.subject-card, .stats-bar, .exam-metadata, .answer-section, .search-input,
.toolbar-btn, .filter-chip, .dark-toggle, .back-to-top, .toolbar-select,
.practice-score, .self-score-panel {
  transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease;
}
/* answer-cell 不需要過渡，數量太多 */
```

---

### [Medium] #7 — 全域變數污染

- **類別**: JS
- **檔案**: `app.js:35,45-47,300,324,422-424`
- **問題**: 以下變數直接宣告在全域作用域：
  - `activeYearFilter` (L35)
  - `searchHits`, `currentHitIdx`, `currentView` (L45-47)
  - `bookmarkFilterActive` (L300)
  - `subjectViewBuilt` (L324)
  - `practiceMode`, `practiceCorrect`, `practiceTotal` (L422-424)

  此外 `debounce`, `debouncedSearch`, `toggleYear`, `toggleCard`, `doSearch` 等函式也全部掛在 `window` 上。
- **影響**: 若頁面引入其他第三方腳本，可能產生命名衝突。
- **建議修復**:
```javascript
// 包裝在 IIFE 或模組中
(function() {
  'use strict';
  let activeYearFilter = '';
  // ... 所有變數和函式
  // 只暴露 HTML onclick 需要的函式
  window.toggleFilter = toggleFilter;
  window.switchView = switchView;
  // ...
})();
```

---

### [Medium] #8 — CSS `display` 重複宣告

- **類別**: CSS
- **檔案**: `style.css:22`
- **問題**: `.sidebar-home` 先宣告 `display: block`，後又宣告 `display: flex`。後者覆蓋前者，`display: block` 無效。
- **建議修復**:
```css
.sidebar-home {
  display: flex; /* 直接用 flex，移除多餘的 display: block */
  align-items: center;
  padding: 0.5rem 1.25rem;
  /* ... */
}
```

---

### [Medium] #9 — Inline onclick 與 addEventListener 混用

- **類別**: HTML / JS
- **檔案**: 類科 HTML:128-139 (filter-chip), :147 (resetScore), :150-160 (toolbar buttons)
- **問題**: 大部分互動元素使用 `addEventListener` 綁定事件（sidebar, hamburger, subject-header 等），但 `filter-chip`, `toolbar-btn`, `resetScore`, `export-*` 等按鈕使用 inline `onclick`。風格不一致。
- **影響**: 維護困難，且 inline handlers 運行在全域作用域中。
- **建議修復**: 統一使用 `addEventListener`，在 `DOMContentLoaded` 中綁定事件。

---

### [Medium] #10 — 書籤按鈕缺少 `aria-label`

- **類別**: 無障礙
- **檔案**: `app.js:282-284`
- **問題**: 動態建立的書籤按鈕只設定了 `title='書籤'`，缺少 `aria-label`。按鈕文字內容是 `★` 或 `☆`，螢幕閱讀器會讀出「黑色星號」或「白色星號」，而非「書籤」。
- **建議修復**:
```javascript
bmBtn.setAttribute('aria-label', '切換書籤');
bmBtn.setAttribute('aria-pressed', bookmarks[id] ? 'true' : 'false');
```

---

### [Medium] #11 — 搜尋跳轉按鈕缺少 `aria-label`

- **類別**: 無障礙
- **檔案**: `app.js:145-155`
- **問題**: 上一個/下一個搜尋結果按鈕文字為 `◀` / `▶` 三角形符號，有 `title` 但無 `aria-label`。
- **建議修復**:
```javascript
prevBtn.setAttribute('aria-label', '上一個匹配');
nextBtn.setAttribute('aria-label', '下一個匹配');
```

---

### [Medium] #12 — 淺色模式 `--text-light` 對比度不足

- **類別**: CSS / 無障礙
- **檔案**: `style.css:9`
- **問題**: `--text-light: #5a6a7e` 在白色背景 (`#ffffff`) 上的對比度約 **4.2:1**，未達 WCAG AA 要求的 **4.5:1**（正文文字）。此變數被大量使用於 `page-subtitle`, `meta-tag`, `search-stats`, `stat-label`, `exam-note` 等元素。
- **建議修復**:
```css
/* 略微加深以達到 4.5:1 */
--text-light: #4a5a6e; /* 對比度 ~5.0:1 */
```

---

### [Medium] #13 — `highlightText` 每個文字節點只標記首次匹配

- **類別**: JS
- **檔案**: `app.js:16-33`
- **問題**: `highlightText` 在找到第一個匹配後 `return 1`，不會繼續搜尋同一文字節點中的後續匹配。例如搜尋「警察」時，若一個題目文字中出現三次「警察」，只有第一次會被高亮。
- **影響**: 搜尋結果高亮不完整，影響使用者判斷。
- **建議修復**:
```javascript
// 匹配後繼續搜尋剩餘文字
if (node.nodeType === 3) {
  let count = 0;
  let current = node;
  while (current) {
    const idx = current.textContent.toLowerCase().indexOf(query.toLowerCase());
    if (idx === -1) break;
    const span = document.createElement('span');
    span.className = 'highlight';
    const matched = current.splitText(idx);
    current = matched.splitText(query.length);
    span.appendChild(matched.cloneNode(true));
    matched.parentNode.replaceChild(span, matched);
    count++;
  }
  return count;
}
```

---

### [Medium] #14 — `exportPDF` cleanup 依賴 setTimeout 保底

- **類別**: JS
- **檔案**: `app.js:637-640`
- **問題**: `exportPDF` 在 `window.print()` 後使用 `afterprint` 事件清理，但用 `setTimeout(cleanup, 5000)` 作為備用。5 秒後不管使用者是否還在列印對話框中都會執行清理。此外 `afterprint` 和 `setTimeout` 可能導致 `cleanup` 執行兩次（第二次無害但不優雅）。
- **建議修復**:
```javascript
let cleaned = false;
function cleanup() {
  if (cleaned) return;
  cleaned = true;
  // ... 清理邏輯
}
```

---

### [Low] #15 — CSS 命名不一致

- **類別**: CSS
- **檔案**: style.css 多處
- **問題**: 混用多種命名風格：
  - BEM 片段: `btn-correct`, `btn-wrong`
  - 功能命名: `practice-active`, `bookmark-filter`
  - 狀態命名: `.active`, `.open`, `.visible`, `.scored`
  - 元件命名: `.subject-card`, `.answer-cell`

  沒有嚴格遵循任何一種命名規範，但整體命名仍具描述性且可讀。
- **影響**: 低，因為此專案為靜態生成站點，CSS 由單一生成器產生，不太會有團隊協作命名衝突問題。

---

### [Low] #16 — 首頁缺少 skip-link

- **類別**: HTML / 無障礙
- **檔案**: `index.html`
- **問題**: 類科頁面有 `<a href="#searchInput" class="skip-link">跳至搜尋</a>`，但首頁 index.html 沒有 skip-link。雖然首頁結構簡單（無 sidebar），但鍵盤使用者仍需 Tab 過 15 張類科卡片。
- **建議修復**:
```html
<a href="#categories" class="skip-link">跳至類科列表</a>
<!-- 並給 .categories-grid 加上 id="categories" -->
```

---

### [Low] #17 — 首頁 footer 使用全形中間點

- **類別**: HTML
- **檔案**: `index.html:263`
- **問題**: `資料來源：考選部考畢試題查詢平臺 ・ 生成時間：2026-02-22` 中的 `・` 是全形中間點 (U+30FB)。在某些字型下可能顯示為方塊或不正常。建議使用 `&middot;` (U+00B7) 或 `|` 分隔。
- **影響**: 極低，純視覺一致性問題。

---

### [Low] #18 — `toggleCard` 為死碼

- **類別**: JS
- **檔案**: `app.js:7`
- **問題**: `toggleCard(header)` 函式在 JS 中定義，但在 HTML 中未被引用。`subject-header` 的 click 事件在 `initBookmarks()` 中直接用 `addEventListener` 處理（L296），不經過 `toggleCard`。
- **建議修復**: 移除 `toggleCard` 函式。

---

### [Low] #19 — 兩個 `@media print` 區塊

- **類別**: CSS
- **檔案**: `style.css:81, style.css:232`
- **問題**: 有兩個獨立的 `@media print` 區塊。第一個（L81）定義隱藏元素和分頁規則，第二個（L232）補充了背景色重設和答案格樣式。可以合併為一個。
- **影響**: 不影響功能，僅影響可維護性。

---

### [Low] #20 — Sidebar 連結截斷但無完整標題提示

- **類別**: HTML / UX
- **檔案**: 類科 HTML:28-29 (`.sidebar-link`)
- **問題**: `.sidebar-link` 設定了 `text-overflow: ellipsis`，長科目名稱會被截斷（如「警察情境實務(包括警察法規、實」）。但連結缺少 `title` 屬性，使用者無法看到完整名稱。
- **建議修復**: 在 `generate_html.py` 中為 sidebar-link 加上 `title` 屬性。
```python
# generate_html.py 中
f'<a class="sidebar-link" href="#{card_id}" title="{escape_html(subj_name)}">{display_name}</a>'
```

---

### [Info] #21 — CSS/JS 未 minify

- **類別**: 效能
- **檔案**: `style.css` (233 行), `app.js` (641 行)
- **問題**: CSS 和 JS 均為未壓縮狀態。style.css 約 13KB，app.js 約 18KB。minify 後可減少 30-40% 體積。
- **影響**: 此為本地靜態站點，不經網路傳輸時影響極低。若部署至網路則建議壓縮。

---

### [Info] #22 — scroll 事件未節流

- **類別**: 效能 / JS
- **檔案**: `app.js:208`
- **問題**: `window.addEventListener('scroll', ...)` 監聽 scroll 事件以控制 back-to-top 按鈕的顯示。scroll 事件在捲動時每秒觸發數十次，但處理函式只做一次 `classList.toggle`，開銷極小。
- **影響**: 實際影響極低，因為 `classList.toggle` 操作非常輕量。但若未來加入更多 scroll 邏輯，建議加上節流。

---

## 未發現問題的審查項目（通過）

### XSS 防護 -- PASS
`generate_html.py` 使用 `html_module.escape()` (L66-67) 對所有題目文字進行 HTML 跳脫。JS 中使用 `document.createElement` + `textContent` 進行 DOM 操作，不使用 `innerHTML`。靜態站點中所有資料來自本地 JSON 檔案，無使用者輸入。XSS 風險極低。

### localStorage try-catch 保護 -- PASS
`getStore()` (L271) 和 `setStore()` (L272) 均使用 try-catch 保護 localStorage 操作。

### ARIA 屬性 -- 大部分 PASS
- sidebar-year 有 `role="button"`, `tabindex="0"`, `aria-expanded`
- subject-header 有 `role="button"`, `tabindex="0"`, `aria-expanded`
- 搜尋框有 `aria-label`, `aria-describedby`
- search-stats 有 `aria-live="polite"`, `role="status"`
- 工具列有 `role="toolbar"`, `aria-label`
- 匯出面板有 `role="dialog"`, `aria-label`
- 書籤按鈕有 `aria-pressed`
- skip-link 存在且正常

### 語意化 HTML -- PASS
- 使用 `<nav>` 包裝 sidebar 和首頁類科導航
- 使用 `<main>` 包裝主內容
- 使用 `<header>` 和 `<footer>`
- 標題層級正確 (`h1` > `h2` > `h3` > `h4`)

### 空資料處理 -- PASS
`buildSelfScorePanels()` (L453-454) 檢查答案格為空的情況。搜尋無結果時正確顯示 0 匹配。

### 響應式設計 -- PASS
有三個斷點：768px（手機）、320px（Galaxy Fold）、print。手機版有 hamburger 選單、overlay、自適應排版。

### `prefers-reduced-motion` -- PASS
L18 正確停用動畫和過渡效果。

### 鍵盤支援 -- PASS
sidebar-year 和 subject-header 支援 Enter/Space 操作。搜尋框支援 Ctrl+K 和 `/` 快捷鍵，Escape 清空。

---

## 修復優先順序建議

1. **高優先**: #1 搜尋索引（效能影響最大）、#2 科目瀏覽 DOM 倍增
2. **中優先**: #5 --accent 色值統一、#6 移除 answer-cell transition、#12 對比度修正
3. **低優先**: #8 display 重複、#10-11 aria-label 補齊、#18 死碼清理
4. **可選**: #4 字型非阻塞載入、#7 全域變數封裝、#21 minify

---

*報告由 code-reviewer agent 自動產生*
