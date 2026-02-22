# Round 1 UX 審計報告

**生成時間**: 2026-02-22
**測試工具**: Playwright 1.58.0 (Python sync API, Chromium headless)
**測試頁面**:
- 首頁: `index.html`
- 類科頁面: `行政警察/行政警察考古題總覽.html`
- 所有 15 個類科連結（驗證可達性）

**測試視口**:
- 桌面: 1280x800
- 手機: 375x667
- Galaxy Fold: 280x653

---

## 問題總覽

共發現 **8** 個問題：
- Critical: 0
- Major: 4
- Minor: 4

| # | 嚴重度 | 角色 | 問題描述 | 位置 |
|---|--------|------|---------|------|
| 1 | Major | 手機用戶 | 側邊欄點擊連結後不自動關閉，阻擋頁面互動 | app.js + CSS z-index |
| 2 | Major | 手機用戶 | select#subjectFilter 造成水平溢出 (808px) | .toolbar-select CSS |
| 3 | Major | 手機用戶 | filter-chip 年份篩選列溢出視口 | .search-filters CSS |
| 4 | Major | 手機用戶 | .sidebar-link 觸控目標不足 44px (40px高) | .sidebar-link min-height |
| 5 | Minor | 手機用戶 | Galaxy Fold (280px) 水平溢出 | @media (max-width:320px) |
| 6 | Minor | 深色模式 | 深色模式切換按鈕位置不一致（首頁右下 vs 類科頁左下） | .dark-toggle CSS |
| 7 | Minor | 通用 | 首頁缺少 skip-link | index.html HTML |
| 8 | Minor | 鍵盤專家 | Galaxy Fold 下 .filter-chip 觸控目標寬度不足 44px (40px) | .filter-chip CSS |

---

## 詳細問題

### #1 [Major] 側邊欄點擊連結後不自動關閉，阻擋頁面互動
- **角色**: 手機用戶
- **描述**: 在手機視口 (375px) 下，開啟漢堡選單後展開年度並點擊 sidebar-link，側邊欄不會自動關閉。由於 `.sidebar` 的 z-index (100) 高於 `.sidebar-overlay` 的 z-index (90)，側邊欄元素會攔截所有觸控事件，導致使用者無法點擊搜尋框、工具列、試卷卡片等任何主內容區域元素。
- **位置**: `js/app.js` 第 194-196 行, `css/style.css` `.sidebar` z-index:100
- **重現步驟**:
  1. 以 375x667 視口開啟類科頁面
  2. 點擊漢堡選單 (hamburger)
  3. 點擊「114年」展開年度
  4. 點擊任一科目連結（如「中華民國憲法與警察專業英文」）
  5. 側邊欄保持開啟，覆蓋整個螢幕
  6. 嘗試點擊搜尋框 -- 被側邊欄攔截，無法操作
- **Playwright 驗證**: `sidebar.classList.contains('open') === true`（連結點擊後仍為 true）
- **建議修復**: 確認 `closeMobileSidebar()` 在 sidebar-link 的 click 事件處理器中被正確呼叫。目前 app.js 第 194-196 行有相關程式碼，但在展開 sidebar-year 後產生的可見連結可能未被正確綁定。

### #2 [Major] select#subjectFilter 造成水平溢出 (808px)
- **角色**: 手機用戶
- **描述**: 在 375px 視口下，`select#subjectFilter.toolbar-select` 的計算寬度為 792px，遠超過視口寬度，造成頁面 scrollWidth 達到 808px（應為 375px）。這是手機水平捲動的主要原因。
- **位置**: `css/style.css` `.toolbar-select` 及 `@media (max-width: 768px)` 區塊
- **重現步驟**:
  1. 以 375px 寬度開啟類科頁面
  2. 檢查 `document.documentElement.scrollWidth`（返回 808px）
  3. 檢查 `select#subjectFilter` 的 `getBoundingClientRect().right`（返回 808px）
- **建議修復**: 在 `@media (max-width: 768px)` 中為 `.toolbar-select` 加上 `max-width: 100%` 或 `width: 100%`，並確保 `.toolbar` 容器有 `overflow: hidden`。

### #3 [Major] filter-chip 年份篩選列溢出視口
- **角色**: 手機用戶
- **描述**: `.search-filters` 容器中的年份篩選按鈕 (`.filter-chip`) 在手機上水平排列，雖然有 `overflow-x: auto` 和 `flex-wrap: nowrap`，但篩選按鈕本身延伸到 viewport 之外（最右邊的按鈕 right=556px），導致頁面整體產生水平捲動。
- **位置**: `css/style.css` `.search-filters` 及 `.filter-chip` 在 `@media (max-width: 768px)`
- **重現步驟**:
  1. 以 375px 寬度開啟類科頁面
  2. 觀察年份篩選列可向右捲動，但同時整個頁面也跟著水平捲動
- **建議修復**: 確保 `.search-filters` 的父容器有 `overflow: hidden` 或 `.search-box` 設定 `max-width: 100%; overflow: hidden`，讓篩選列的橫向捲動不影響頁面整體。

### #4 [Major] .sidebar-link 觸控目標不足 44px
- **角色**: 手機用戶
- **描述**: `.sidebar-link` 的高度為 40px，低於 Apple/Google 建議的最小觸控目標 44x44px。在手機上使用側邊欄導航時，連結之間間距過小，容易誤觸。
- **位置**: `css/style.css` `.sidebar-link` 第 29 行（`min-height: 40px`）
- **建議修復**: 將 `.sidebar-link` 的 `min-height` 從 40px 改為 44px。

### #5 [Minor] Galaxy Fold (280px) 水平溢出
- **角色**: 手機用戶
- **描述**: 在 Galaxy Fold 的 280px 視口下，scrollWidth=710px 遠超過 clientWidth=280px。雖然已有 `@media (max-width: 320px)` 媒體查詢，但仍有嚴重的水平溢出問題，主要來自 `.toolbar-select` 和 `.filter-chip` 列。
- **位置**: `css/style.css` `@media (max-width: 320px)` 區塊
- **建議修復**: 在 320px 以下的媒體查詢中，為 `.toolbar-select` 加上 `max-width: 100%`，`.toolbar` 設定 `flex-wrap: wrap; overflow: hidden`。

### #6 [Minor] 深色模式切換按鈕位置不一致
- **角色**: 深色模式愛好者
- **描述**: 首頁 (index.html) 的深色模式切換按鈕位於右下角 (x=1204)，而類科頁面的切換按鈕位於左下角 (x=32)。使用者從首頁切換到類科頁面時，可能找不到深色模式按鈕。
- **位置**: `index.html` 內嵌 CSS `.dark-toggle { right: 2rem }` vs `css/style.css` `.dark-toggle { left: 2rem }`
- **重現步驟**:
  1. 開啟 index.html，觀察右下角的月亮圖示
  2. 點擊任一類科進入
  3. 深色模式按鈕移到左下角
- **建議修復**: 統一深色模式按鈕位置，建議都放在左下角（與類科頁面一致，避免與回到頂部按鈕衝突）。

### #7 [Minor] 首頁缺少 skip-link
- **角色**: 通用（無障礙）
- **描述**: `index.html` 沒有 `.skip-link` 元素，而類科頁面有 `<a href="#searchInput" class="skip-link">跳至搜尋</a>`。鍵盤使用者在首頁無法快速跳過導航區域。
- **位置**: `index.html` HTML 結構
- **建議修復**: 在 `<body>` 開頭加入 `<a href="#main" class="skip-link">跳至內容</a>`，並為 `<main>` 加上 `id="main"`。同時需要加入 skip-link 的 CSS（可參考類科頁面的 style.css）。

### #8 [Minor] Galaxy Fold 下 .filter-chip 觸控目標寬度不足
- **角色**: 鍵盤/觸控使用者
- **描述**: 在 280px 視口下，`.filter-chip` 的寬度為 40px，低於建議的 44px 最小觸控目標。高度 (44px) 符合標準。
- **位置**: `css/style.css` `@media (max-width: 320px)` `.filter-chip` 規則
- **建議修復**: 在極端窄螢幕下，考慮增加 `.filter-chip` 的 `min-width: 44px`。

---

## 通過的測試（無問題）

### 角色 1: 新手考生
- [PASS] 首頁 15 個類科卡片全部可見
- [PASS] 點擊類科卡片正確導航至類科頁面
- [PASS] 類科頁面標題、統計數據正確顯示
- [PASS] 展開試卷卡片可看到題目（63 張卡片，首張含 60 題）
- [PASS] 搜尋「憲法」找到 22 份試卷、377 處匹配
- [PASS] 搜尋結果正確高亮
- [PASS] 無 console 錯誤、無頁面錯誤

### 角色 2: 密集複習者
- [PASS] 練習模式啟用/停用正常
- [PASS] 計分面板正確顯示
- [PASS] 「顯示答案」→「答對」流程正常，分數即時更新
- [PASS] 書籤功能正常（3/3 成功啟用）
- [PASS] 「只看書籤」篩選正確（顯示 3 張書籤卡片）
- [PASS] 年份篩選正常
- [PASS] 科目瀏覽模式正常（8 個科目區段）
- [PASS] 無 console 錯誤

### 角色 3: 手機用戶
- [PASS] 漢堡選單在 375px 下可見
- [PASS] 點擊漢堡選單正確開啟側邊欄
- [PASS] 搜尋功能在手機上正常運作
- [FAIL] 側邊欄連結點擊後不自動關閉（見 #1）
- [FAIL] 水平溢出（見 #2, #3）
- [FAIL] .sidebar-link 觸控目標不足（見 #4）

### 角色 4: 深色模式愛好者
- [PASS] 深色模式切換正常
- [PASS] localStorage 正確保存偏好 (`exam-dark: true`)
- [PASS] 深色模式跨頁面持續生效
- [PASS] 所有主要元素（sidebar、卡片、搜尋框、工具列）正確套用深色主題
- [PASS] 搜尋高亮在深色模式下可讀（bg: #92400e, color: #fef3c7）
- [PASS] 練習模式在深色模式下正常
- [PASS] 切回淺色模式正常
- [PASS] 無 console 錯誤

### 角色 5: 鍵盤專家
- [PASS] Skip-link 是第一個 Tab 焦點
- [PASS] Ctrl+K 正確聚焦搜尋框
- [PASS] `/` 正確聚焦搜尋框
- [PASS] Escape 清除搜尋內容並取消焦點
- [PASS] Enter 展開試卷卡片
- [PASS] Space 收合試卷卡片
- [PASS] Enter 展開側邊欄年度
- [PASS] 所有檢查的元素都有 focus-visible 樣式
- [PASS] Escape 正確關閉匯出面板

### 額外檢查
- [PASS] 所有 15 個類科連結正確可達
- [PASS] 無 JavaScript 錯誤（console 或 pageerror）
- [PASS] 無失敗的網路請求
- [PASS] 列印模式正確隱藏 sidebar、search-box、toolbar
- [PASS] 側邊欄收合/展開功能正常，localStorage 持續化
- [PASS] 回到頂部按鈕在捲動 400px 後正確出現
- [PASS] 匯出面板 ARIA 屬性正確（role=dialog, aria-label）
- [PASS] 匯出面板取消按鈕正常

---

## 測試截圖

截圖存放於 `reports/screenshots/` 目錄：

| 檔案 | 說明 |
|------|------|
| `r1_01_index.png` | 首頁（淺色模式） |
| `r1_02_category_page.png` | 類科頁面 |
| `r1_03_expanded_card.png` | 展開的試卷卡片 |
| `r1_04_search.png` | 搜尋「憲法」結果 |
| `r2_01_practice_mode.png` | 練習模式啟用 |
| `r2_02_revealed_answer.png` | 顯示答案 |
| `r2_03_scored.png` | 計分後 |
| `r2_04_bookmark_filter.png` | 書籤篩選 |
| `r2_05_year_filter.png` | 年份篩選 |
| `r2_06_subject_view.png` | 科目瀏覽 |
| `r3_01_mobile_initial.png` | 手機版初始畫面 |
| `r3_02_sidebar_open.png` | 手機側邊欄開啟 |
| `r3_03_mobile_search.png` | 手機搜尋 |
| `r4_01_index_light.png` | 首頁淺色模式 |
| `r4_02_index_dark.png` | 首頁深色模式 |
| `r4_03_category_dark.png` | 類科頁深色模式 |
| `r4_04_dark_search.png` | 深色模式搜尋 |
| `r4_05_dark_practice.png` | 深色模式練習 |
| `r4_06_back_to_light.png` | 切回淺色模式 |
| `r5_01_keyboard_test.png` | 鍵盤測試 |
| `extra_galaxy_fold.png` | Galaxy Fold 280px |
| `extra_mobile_overflow.png` | 手機溢出檢查 |
| `extra_dark_highlight.png` | 深色模式搜尋高亮 |

---

## 測試環境
- **工具**: Playwright 1.58.0 (Python sync API)
- **瀏覽器**: Chromium (headless)
- **測試腳本**: `reports/ux_audit_test.py` (主測試), `reports/ux_audit_extra.py` (額外測試)
- **平台**: Windows 10 / MSYS2
