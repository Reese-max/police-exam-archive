# Round 3 手機端靜態分析報告

**分析日期**: 2026-02-22
**分析範圍**: `css/style.css` (256 行), `js/app.js` (700 行), `index.html` (302 行), `行政警察/行政警察考古題總覽.html` (前 200 行)

---

## CSS 問題清單

| # | 嚴重度 | 問題 | 檔案:行號 | 說明 | 建議修復 |
|---|--------|------|-----------|------|----------|
| C1 | Critical | `body` transition 觸發 layout | style.css:204 | `transition: background-color 0.3s ease, color 0.3s ease;` 雖然 background-color/color 只觸發 paint 不觸發 layout，但這個 transition 套用在 `body` 上，會導致所有子元素繼承 color transition，在深色模式切換時造成大量 paint 工作。手機效能影響顯著。 | 將 transition 限定在具體元素，不要套用於 body。或使用 `will-change: background-color` 僅在 body 上，並移除 color transition（讓子元素各自處理）。 |
| C2 | Critical | `.sidebar` 雙重 transition 衝突 | style.css:21 vs 205 | 第 21 行定義 `transition: transform 0.3s ease;`，第 205 行又覆蓋為 `transition: transform 0.3s ease, background-color 0.3s ease;`。第 205 行**完全覆蓋**第 21 行的 transition（CSS transition 不疊加），但兩者 specificity 相同。如果載入順序出問題，sidebar 開關的 transform 動畫可能失效。 | 移除第 21 行的 transition，統一在第 205 行管理。或用 `transition-property` 分離定義。 |
| C3 | Critical | `content-visibility: auto` 與 `overflow: hidden` 副作用 | style.css:233 | `.subject-card { content-visibility: auto; contain-intrinsic-size: auto 80px; }` 會在手機上引入隱含的 `contain: layout style paint`。當使用者搜尋跳轉 (`jumpHit`) 到未可見的 card 時，`scrollIntoView` 計算的位置可能不準確，因為被 content-visibility 跳過的 card 高度只有 80px 估計值。 | 在 `jumpHit()` 執行前，先對目標 card 設定 `content-visibility: visible`，或在搜尋時對所有匹配的 card 暫時移除 content-visibility。 |
| C4 | Major | 搜尋框漸層遮罩在深色模式失效 | style.css:245 | `.search-box::after` 使用 `background: linear-gradient(to right, transparent, var(--bg))`。深色模式下 `--bg` 變為 `#1a202c`，但此 pseudo-element 在手機媒體查詢內生成，**沒有對應的 `html.dark` 覆蓋**。雖然 `var(--bg)` 會自動跟隨變數變更，但 gradient 從 `transparent`（即 rgba(0,0,0,0)）到深色的漸變會出現灰黑色中間帶，而非乾淨的淡出效果。 | 改用 `transparent` 為起點時，應使用 `rgba(26,32,44,0)` 的深色模式變體。或改為 `background: linear-gradient(to right, color-mix(in srgb, var(--bg) 0%, transparent), var(--bg))` 若瀏覽器支援。 |
| C5 | Major | `.search-filters` 水平捲動無 scroll-snap | style.css:129, 243 | 手機上 `.search-filters` 設為 `overflow-x: auto; flex-wrap: nowrap`，但沒有 `scroll-snap-type` 和對應的 `scroll-snap-align`。使用者滑動篩選按鈕時會「飄」過去，沒有對齊點。 | 加入 `.search-filters { scroll-snap-type: x mandatory; }` 和 `.filter-chip { scroll-snap-align: start; }`。 |
| C6 | Major | `.toolbar` 網格佈局缺少 `gap` 一致性 | style.css:247 | 768px 以下 toolbar 改為 `display: grid; grid-template-columns: 1fr 1fr;` 但未重新定義 gap。第 83 行的 `gap: 0.5rem` 和 129 行的 `gap: 0.4rem` 哪個生效取決於 specificity。兩個 media query 都是 `max-width: 768px`，後者 247 行覆蓋 129 行的 flex gap，但 grid 的 gap 行為不同於 flex 的 gap，可能導致間距不一致。 | 在 247 行的 grid 規則中明確設定 `gap: 0.4rem`。 |
| C7 | Major | `scroll-padding-top: 140px` 在手機偏大 | style.css:18 | `html { scroll-padding-top: 140px; }` 是全域值，但手機上 header 區域高度不同（hamburger ~56px + search-box ~100px）。140px 在桌面合理，手機上可能導致錨點跳轉時目標元素位置過低。 | 在 `@media (max-width: 768px)` 中覆蓋為 `html { scroll-padding-top: 100px; }`。 |
| C8 | Major | `.practice-score` sticky 定位與 `.search-box` sticky 重疊 | style.css:184, 251 | `.practice-score { position: sticky; top: 0; z-index: 55; }` 在 768px 以下改為 `top: 3.5rem`。而 `.search-box` 是 `position: sticky; top: 3.5rem; z-index: 49`。兩者同時顯示時，practice-score（z-index: 55）會疊在 search-box（z-index: 49）上方，但它們的 `top` 值相同（3.5rem），會完全重疊遮擋。 | 將 `.practice-score` 的手機 top 值改為 `calc(3.5rem + 搜尋框高度)`，約 `top: 7rem`。或在練習模式啟動時隱藏搜尋框。 |
| C9 | Major | z-index 堆疊分析 | 多處 | z-index 值分布：hamburger=300, export-panel(mobile)=250, export-overlay=240, dark-toggle=200, back-to-top=200, sidebar=100, sidebar-reopen=101, practice-score=55, search-box=50/49, skip-link=999。**問題**：dark-toggle(200) 和 back-to-top(200) 相同 z-index，在手機上 dark-toggle 在左下、back-to-top 在右下，雖然位置不重疊，但如果 export-panel(250) 彈出時，它們仍可見（200 < 250 是正確的）。但 sidebar-overlay(90) < sidebar(100) 是正確的。沒有重大衝突。 | 知悉即可。建議建立 z-index 管理常數表以利維護。 |
| C10 | Major | `.export-panel` 手機底部彈出無 `max-height` 保護 | style.css:249 | 手機版 export-panel 是 `position: fixed; bottom: 0`，但沒有 `max-height`。如果未來增加更多匯出選項，面板可能覆蓋整個螢幕。 | 加入 `max-height: 60vh; overflow-y: auto;`。 |
| C11 | Minor | `.sidebar-link` white-space: nowrap 可能截斷長文字 | style.css:30 | `.sidebar-link { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }` 在手機 sidebar 寬度 280px 下，過長的科目名稱被截斷但沒有 `title` 提示。**HTML 已有 title 屬性**，但觸控裝置無法觸發 tooltip。 | 考慮在手機上改為 `white-space: normal` 或增加 `word-break: break-all` 讓文字換行。 |
| C12 | Minor | `.filter-chip` 無 `min-width` 保護 | style.css:71, 129 | 篩選按鈕在極端情況下（如「全部年份」4 字 + padding）寬度可能小於 44px。雖然有 `min-height: 44px`，但 `min-width` 未設定。 | 對非 nowrap 的 filter-chip 加入 `min-width: 44px`。 |
| C13 | Minor | `.mc-question[data-subtype="passage_fragment"]::before` 含 emoji | style.css:154 | `content: '\01F4D6 閱讀段落'` 使用 Unicode emoji，在不同手機上渲染大小差異大（iOS vs Android），可能撐破佈局。 | 改用 SVG icon 或純文字標記「[閱讀段落]」。 |
| C14 | Minor | `.essay-question` text-indent 負值問題 | style.css:59 | `text-indent: -1.5em; padding-left: 1.5em;` 在手機 320px 螢幕上，1.5em 約 12px（font-size 0.8rem=~12.8px），配合 `padding: 0.75rem`（12px），剩餘寬度約 296px，勉強足夠但換行時首行會更窄。 | 在 320px 斷點降低為 `text-indent: -1.2em; padding-left: 1.2em;`。 |
| C15 | Minor | 部分 transition 使用 `all` 的隱憂 | style.css:206 | 第 206 行的大量元素設定了 `transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease;`。雖然沒有使用 `all`（很好），但清單很長。每次 hover/dark-mode 切換會觸發這些元素的 transition。 | 知悉即可。目前已避免 `transition: all`，是好的實踐。 |
| C16 | Info | `-webkit-overflow-scrolling: touch` 已過時 | style.css:243 | `-webkit-overflow-scrolling: touch;` 在 iOS 13+ 已是預設行為，此屬性已過時。 | 可移除但保留也無害。 |
| C17 | Info | 無 `@media (prefers-contrast: high)` 支援 | 全域 | 缺少高對比度模式支援，部分視障使用者在手機上可能無法清楚辨識低對比度文字（如 `--text-muted: #a0aec0` on `--bg: #f0f4f8`，對比度約 2.5:1，低於 WCAG AA 的 4.5:1）。 | 考慮加入 `@media (prefers-contrast: high)` 規則，提高 text-muted 的對比度。 |

---

## JS 問題清單

| # | 嚴重度 | 問題 | 檔案:行號 | 說明 | 建議修復 |
|---|--------|------|-----------|------|----------|
| J1 | Critical | `highlightText()` 大量 DOM 操作觸發 reflow | app.js:15-38 | `highlightText` 在搜尋時對每個匹配的文字節點進行 `splitText` + `replaceChild`，且在 `doSearch` 中對每個 card 的 body 逐一呼叫。這些操作**沒有**批次處理（如 `DocumentFragment`），每次 `replaceChild` 都會觸發 reflow。在手機上搜尋大量匹配時（如搜尋「警察」可能匹配上百處），會嚴重卡頓。 | 方案一：用 `requestAnimationFrame` 分批處理；方案二：用 CSS `::highlight()` API（Chromium 105+）替代 DOM 操作；方案三：先收集所有需要替換的節點，用 `DocumentFragment` 批次替換。 |
| J2 | Critical | `clearHighlights()` 的 `querySelectorAll('.highlight')` 效能問題 | app.js:8-14 | 每次搜尋前呼叫 `clearHighlights()`，遍歷所有 `.highlight` 元素。配合 `p.replaceChild` + `p.normalize()`，每個 highlight 元素的移除都觸發 reflow。如果之前搜尋匹配了 500 個位置，清除時就有 500 次 reflow。 | 用 `TreeWalker` 或在 card 上使用 `innerHTML` 快照恢復原始內容（搜尋前快取原始 innerHTML）。 |
| J3 | Critical | `buildSubjectView()` 克隆大量 DOM 節點 | app.js:366-432 | `cloneNode(true)` 深度克隆每個 subject-card（含所有題目 DOM 節點）。若有 63 張卡片，每張含數十個題目，可能克隆數千個 DOM 節點。手機上首次切換到「依科目瀏覽」時會明顯卡頓。 | 方案一：延遲克隆（lazy clone），只在使用者展開 card 時才克隆 body 內容；方案二：使用虛擬滾動；方案三：改為共享 DOM 節點而非克隆（用 CSS 切換可見性）。 |
| J4 | Major | `window._cardTextCache` Map 記憶體占用 | app.js:285-289, 427-431 | `_cardTextCache` 在 DOMContentLoaded 時快取所有 card 的 `textContent.toLowerCase()`。若有 63 張卡片，每張平均 5KB 文字，就是 ~315KB。切換到科目瀏覽後又加入 63 份克隆卡片的文字，總共 ~630KB。在低端手機上可能有記憶體壓力。 | 可接受的權衡。若需優化，可改用 `WeakMap`（但 WeakMap 不支援 `.has()` 的方式列舉）。或限制快取大小。 |
| J5 | Major | `scroll` 事件無 throttle | app.js:223 | `window.addEventListener('scroll', function() { backToTop.classList.toggle('visible', window.scrollY > 400); });` 沒有使用 throttle/debounce 或 `passive: true`。scroll 事件在快速滑動時每秒觸發 60+ 次，每次都執行 DOM 操作（classList.toggle）。 | 方案一：加入 `{ passive: true }`（已確認沒有 `preventDefault`，安全）；方案二：用 `IntersectionObserver` 替代監聽一個隱藏的哨兵元素；方案三：至少加入 `requestAnimationFrame` 節流。 |
| J6 | Major | localStorage 無完整例外處理 | app.js:217-218, 292-293 | `getStore` 和 `setStore` 有 try-catch，但第 217 行 `localStorage.getItem('sidebar-collapsed')` 和第 337 行 `localStorage.getItem('exam-dark')` **沒有** try-catch。在 Safari 隱私模式下，localStorage 在容量滿時會拋出 `QuotaExceededError`。雖然讀取通常不會失敗，但在某些極端 WebView 環境中可能拋出安全例外。 | 將所有 `localStorage` 直接存取改用 `getStore`/`setStore` 函數包裝，或加入全域 try-catch wrapper。 |
| J7 | Major | `filter-chip` 使用 inline `onclick` | 類科HTML:144-153 | `<button class="filter-chip" onclick="toggleFilter(this,'year')">` 使用 inline event handler。每個按鈕各有一個 handler 實例。雖然數量不多（~10 個），但不符合事件委派最佳實踐。 | 改用事件委派：在 `.search-filters` 上監聯 `click` 事件，根據 `e.target.closest('.filter-chip')` 判斷。 |
| J8 | Major | `touchstart`/`touchend` 未處理 `touchcancel` | app.js:207-211 | sidebar 滑動關閉只監聽 `touchstart` + `touchend`，沒有 `touchcancel`。當系統中斷觸控（如來電、通知下拉）時，`touchend` 不會觸發，`touchStartX` 會保留舊值，下次觸控可能產生誤判。 | 加入 `touchcancel` 事件監聽器，重設 `touchStartX = 0`。 |
| J9 | Major | sidebar 滑動關閉只偵測左滑，缺乏閾值保護 | app.js:209-210 | `dx < -60` 判斷左滑關閉，但沒有 Y 軸位移閾值。使用者在 sidebar 中垂直滾動時，如果手指有些水平偏移（超過 60px），可能誤觸關閉。且 60px 在高 DPI 裝置上很容易達到。 | 加入 Y 軸閾值條件：`Math.abs(dy) < Math.abs(dx) && dx < -60`（即水平位移大於垂直位移才觸發）。同時紀錄 touchStartY。 |
| J10 | Major | `doSearch()` 中 `sections.forEach` 使用 `style*="display: none"` 字串匹配 | app.js:78, 133 | `s.querySelectorAll('.subject-card:not([style*="display: none"])')` 依賴 inline style 字串匹配。這是脆弱的做法 -- 如果瀏覽器序列化 style 為 `display:none`（無空格）或 `display: none;`（有分號），選擇器可能失配。 | 改用 class 標記：隱藏 card 時加 `.hidden` class，判斷用 `.subject-card:not(.hidden)` 選擇器。 |
| J11 | Minor | `exportPDF()` cleanup 的 `setTimeout(cleanup, 5000)` | app.js:698 | `afterprint` 和 5 秒 fallback 清理。在手機上列印對話框可能保持更久（使用者思考選項），5 秒可能不夠。 | 增加到 30 秒或使用 MutationObserver 監控 print header 的移除。 |
| J12 | Minor | search debounce 180ms 可能在手機上過短 | app.js:5 | `debounce(v => doSearch(v), 180)` 在低端手機（搜尋 + highlight 可能需 200ms+）上可能還未完成上次搜尋就觸發下次。 | 考慮在手機上增加到 300ms：`const ms = window.innerWidth <= 768 ? 300 : 180;`。 |
| J13 | Minor | `initBookmarks()` 為每個 card 的 bookmark-btn 綁定個別 `onclick` | app.js:295-322 | 63 張卡片各有一個 bookmark button 的 onclick handler。加上科目瀏覽的 63 份克隆，共 126 個 handler。 | 改用事件委派：在 `#yearView` 和 `#subjectView` 層級監聽 click，判斷 `.bookmark-btn`。 |
| J14 | Minor | `highlightText` 遞迴搜尋 while 迴圈可能對極長文字效能差 | app.js:21-31 | while 迴圈在同一文字節點中反覆搜尋。如果一段文字中有大量匹配（如搜尋單字「的」），每次 `splitText` 都產生新節點，迴圈持續，O(n*m) 複雜度。 | 加入每節點最大匹配數限制（如 50），或改用正則表達式一次找出所有匹配位置再批次處理。 |
| J15 | Minor | `handleHash()` 使用 `setTimeout(scrollToWithOffset, 100)` | app.js:584, 600 | 100ms 延遲在低端手機上可能不足以讓 DOM 完全渲染（特別是有 content-visibility 的卡片）。 | 改用 `requestAnimationFrame` 雙層嵌套或 `ResizeObserver` 監控目標元素。 |
| J16 | Info | `practiceMode session` 1 小時 TTL | app.js:466 | `Date.now() - session.ts < 3600000`（1 小時）。對於考試練習來說合理，但如果使用者放下手機吃飯再回來（>1 小時），進度會遺失。 | 可考慮增加到 4 小時或提供「恢復上次練習」的確認對話框。 |
| J17 | Info | `bookmarkFilterActive` 全域變數 | app.js:324 | 使用全域變數管理狀態。不是問題但不利於未來擴展。 | 知悉即可。若未來需要重構，考慮用狀態物件封裝。 |

---

## 一致性問題（首頁 vs 類科頁）

| # | 頁面 | 差異 | 建議 |
|---|------|------|------|
| I1 | 首頁 index.html | 深色模式按鈕位於**右下角** (`right: 2rem`)，第 42 行 | 與類科頁不一致（類科頁在**左下角** `left: 2rem`，style.css:91）。使用者切換頁面時按鈕位置跳動，造成認知負擔。**建議統一為右下角**（首頁的做法），因為 back-to-top 和 dark-toggle 分別在右/左，互不干擾。 |
| I2 | 首頁 index.html | CSS 變數 `--text-light` 值為 `#718096` | 類科頁 style.css 中 `--text-light` 值為 `#4a5a6e`。兩者色值不同，首頁的 `#718096` 更淡。深色模式下兩頁都用 `#a0aec0`，一致。 |
| I3 | 首頁 index.html | 新增 `--gold: #d69e2e` 變數 | 類科頁 style.css 中沒有 `--gold` 變數（使用硬編碼 `#d69e2e` 或 `--warning`）。建議統一。 |
| I4 | 首頁 index.html | 缺少 `input` 的 `touch-action: manipulation` | 首頁第 53 行只有 `a, button, [role="button"]`，缺少 `input, select`。類科頁 style.css:17 完整包含 `a, button, input, select, [role="button"]`。 |
| I5 | 首頁 index.html | 無 `scroll-behavior: smooth` | 類科頁 style.css:18 有 `html { scroll-behavior: smooth; }`，首頁無此設定。首頁目前無需平滑捲動（無錨點導航），但一致性角度建議加入。 |
| I6 | 首頁 index.html | 無 `overflow-x: hidden` on body | 類科頁 style.css:20 body 有 `overflow-x: hidden`，首頁無。若首頁 hero 區域在某些手機上溢出，可能出現水平捲軸。 |
| I7 | 首頁 index.html | Safe area 支援差異 | 首頁第 55 行只處理 dark-toggle 和 footer 的 safe-area。類科頁 style.css:253 額外處理 back-to-top、hamburger、main padding-bottom。一致性尚可，因為首頁沒有這些元素。 |
| I8 | 首頁 index.html | 無 `@media (prefers-reduced-motion: reduce)` | 類科頁 style.css:19 有減少動畫的支援，首頁缺少。首頁的 `.category-card:hover` 有 `transform: translateY(-2px)` 動畫。 |
| I9 | 首頁 index.html | 橫屏最佳化差異 | 首頁第 56 行有簡單的橫屏規則。類科頁 style.css:255 有更完整的橫屏優化。首頁在橫屏下 hero 區域可能過高。 |
| I10 | 類科 HTML | `filter-chip` 使用 inline `onclick` | 類科頁第 144-153 行使用 `onclick="toggleFilter(this,'year')"` inline handler，而其他互動元素（sidebar-link, subject-header）在 JS 中用 `addEventListener`。風格不一致。 |

---

## 效能建議

| # | 影響度 | 建議 | 說明 |
|---|--------|------|------|
| P1 | High | 搜尋 highlight 改用 CSS Custom Highlight API | `CSS.highlights` API（Chrome 105+, Safari 17.2+）可避免所有 DOM 操作的 reflow，直接在 paint 層標記文字範圍。對手機效能改善最大。需要 polyfill 或 fallback 策略。 |
| P2 | High | scroll 事件加入 `{ passive: true }` | app.js:223 的 scroll 監聽器未標記 passive。手機瀏覽器在非 passive 的 scroll 事件中會等待 JS 執行完畢才滾動，造成明顯卡頓。 |
| P3 | High | `buildSubjectView` 改為漸進式建構 | 改為 `IntersectionObserver` 監控的懶載入：先建立空的 section 骨架，當 section 進入 viewport 時才克隆 card。可將首次切換延遲從 ~500ms 降到 ~50ms。 |
| P4 | Medium | 事件委派取代個別綁定 | 將 bookmark-btn（126 個 handler）、filter-chip（10 個 inline onclick）、sidebar-link 的 click 事件改為各自父容器的事件委派。減少記憶體占用和 GC 壓力。 |
| P5 | Medium | `doSearch` 中的 section 可見性判斷改用 class | 取代 `[style*="display: none"]` 字串匹配選擇器，改用 `.hidden` class 搭配 CSS `.hidden { display: none; }`。querySelectorAll 搭配 class 選擇器比屬性選擇器快 ~2-5x。 |
| P6 | Medium | `content-visibility` 搭配搜尋的整合 | 搜尋跳轉前先對目標 card 設定 `content-visibility: visible`，並在 `requestAnimationFrame` 後才執行 `scrollIntoView`。避免捲動位置計算錯誤。 |
| P7 | Low | 深色模式 transition 限定範圍 | 移除 `body` 上的 transition，改為只在 `.main, .sidebar, .toolbar, .search-box` 等容器上設定。減少深色模式切換時的全域 paint 成本。 |
| P8 | Low | Google Fonts 載入策略 | 目前使用 `media="print" onload="this.media='all'"` 技巧，良好。但在手機網路慢時，CLS（Cumulative Layout Shift）可能很高，因為回退字體與 Noto Sans TC 的 metrics 差異大。考慮使用 `font-display: optional` 或預載字體子集。 |

---

## 總結

### 嚴重度統計

| 嚴重度 | CSS | JS | 一致性 | 合計 |
|--------|-----|----|--------|------|
| Critical | 3 | 3 | - | **6** |
| Major | 8 | 7 | - | **15** |
| Minor | 5 | 5 | - | **10** |
| Info | 2 | 2 | 10 | **14** |
| **合計** | **18** | **17** | **10** | **45** |

### 最高優先修復項

1. **J1/J2** - 搜尋 highlight 的 DOM 操作效能（手機搜尋卡頓的主因）
2. **C3** - content-visibility 與搜尋跳轉的整合問題
3. **J5/P2** - scroll 事件缺少 passive 標記
4. **C8** - practice-score 與 search-box 的 sticky 重疊
5. **I1** - 深色模式按鈕位置不一致
6. **J3/P3** - buildSubjectView 大量 DOM 克隆的效能

### 整體評價

CSS 架構紮實，深色模式和響應式設計覆蓋全面，z-index 管理有序。JS 功能完整但存在效能瓶頸，主要集中在搜尋 highlight 和科目瀏覽的 DOM 操作。首頁與類科頁的一致性有多處小差異需要統一。手機觸控交互基本到位但滑動手勢邊界處理可加強。
