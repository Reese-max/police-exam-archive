# Round 2 UX 審計報告

**生成時間**: 2026-02-22
**測試工具**: Playwright (Python sync API, Chromium headless)
**測試頁面**:
- 首頁: `index.html`
- 類科頁面: `行政警察/行政警察考古題總覽.html`

**測試視口**:
- 桌面: 1280x800
- 手機: 375x667
- Galaxy Fold: 320x658

---

## 測試總覽

- **總測試數**: 61
- **通過**: 59
- **失敗**: 2（均為 Round 1 未修復的遺留問題）
- **新問題**: 0

### Round 1 修復驗證結果

| Round 1 問題 | 修復狀態 |
|-------------|---------|
| #1 側邊欄連結點擊後不自動關閉 | **已修復** |
| #2 select#subjectFilter 造成水平溢出 | **未修復**（見下方 #1） |
| #3 filter-chip 溢出視口 | **已修復**（body overflow-x:hidden 有效遮蔽） |
| #4 .sidebar-link 觸控目標不足 44px | **已修復**（min-height: 44px） |
| #5 Galaxy Fold 水平溢出 | **已修復**（scrollWidth=320） |
| #6 深色模式按鈕位置不一致 | **未修復**（見下方 #2） |
| #7 首頁缺少 skip-link | **已修復** |
| #8 .filter-chip 觸控目標寬度不足 | **已修復**（所有可見觸控目標 >= 44px） |
| 書籤按鈕 aria-label + aria-pressed | **已修復**（63/63 按鈕） |
| 搜尋跳轉按鈕 aria-label | **已修復**（2 個按鈕） |
| Google Fonts 非阻塞載入 | **已修復**（media=print + onload swap） |
| Sidebar-link title 屬性 | **已修復**（63/63 連結） |
| highlightText 全匹配 | **已修復**（搜尋「警察」找到 1931 處高亮） |
| 搜尋索引預建 | **已修復**（cache size=63） |

---

## 未修復問題

共 **2** 個遺留問題（均來自 Round 1）：

| # | 嚴重度 | 來源 | 問題描述 | 位置 |
|---|--------|------|---------|------|
| 1 | Major | R1 #2 | select#subjectFilter 在手機上寬度 792px，遠超 375px 視口 | css/style.css `.toolbar-select` |
| 2 | Minor | R1 #6 | 深色模式按鈕位置不一致（首頁右下 vs 類科頁左下） | index.html 內嵌 CSS |

### #1 [Major] select#subjectFilter 在手機上溢出（R1 #2 遺留）

- **描述**: 在 375px 手機視口下，`select#subjectFilter` 的計算寬度為 792px，`max-width` 為 `none`。雖然 `body { overflow-x: hidden }` 阻止了整個頁面水平捲動（scrollWidth 確實等於 375px），但 select 元素本身仍然溢出其父容器，在某些情況下可能導致佈局問題。
- **位置**: `css/style.css` `.toolbar-select`（第 197 行）及 `@media (max-width: 768px)` 區塊（第 132 行）
- **測試數據**: width=792px, right=808px, maxWidth=none
- **影響**: 中等 -- `overflow-x: hidden` 防止使用者感知到水平捲動，但 select 元素的選項文字（如「警察情境實務(包括警察法規、實務操作標準作業程序...)」）超長導致 native select 寬度撐開。
- **建議修復**:
  ```css
  /* 在 @media (max-width: 768px) 中加入 */
  .toolbar-select {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  /* 或直接設定固定寬度 */
  .toolbar { overflow: hidden; }
  ```

### #2 [Minor] 深色模式按鈕位置不一致（R1 #6 遺留）

- **描述**: 首頁 (`index.html`) 的深色模式按鈕使用內嵌 CSS `right: 2rem`（右下角，x=1204），而類科頁面使用 `css/style.css` 中的 `left: 2rem`（左下角，x=32）。使用者在頁面間切換時可能找不到按鈕。
- **位置**: `index.html` 內嵌 `.dark-toggle { right: 2rem }` vs `css/style.css` `.dark-toggle { left: 2rem }`
- **建議修復**: 統一為左下角（避免與回到頂部按鈕衝突）：
  ```css
  /* index.html 內嵌 CSS 中改為 */
  .dark-toggle { left: 2rem; }
  /* 刪除 right: 2rem */
  ```

---

## 詳細測試結果

### A. Round 1 修復驗證

| 狀態 | 測試項目 | 細節 |
|------|---------|------|
| PASS | --text-light value is #4a5a6e (improved contrast) | got: #4a5a6e |
| PASS | --accent value is #3182ce | got: #3182ce |
| PASS | .sidebar-link min-height >= 44px | got: 44px |
| PASS | body overflow-x: hidden | got: hidden |
| PASS | Bookmark buttons have aria-label | count=63, allHaveLabel=True |
| PASS | Bookmark buttons have aria-pressed | count=63, allHavePressed=True |
| PASS | Search jump buttons have aria-label | count=2, allLabel=True |
| PASS | Index page has skip-link | href=#categories, text='跳至類科列表' |
| PASS | Google Fonts non-blocking on index page | media=all, onload=yes |
| PASS | Google Fonts non-blocking on category page | media=all, onload=yes |
| PASS | Sidebar links have title attribute | 63/63 have title |
| PASS | highlightText finds multiple matches for '警察' | found 1931 highlights |
| PASS | Search text cache pre-built | cache exists and populated |

### B. 鍵盤導航測試

| 狀態 | 測試項目 | 細節 |
|------|---------|------|
| PASS | First Tab focuses skip-link | focused: A.skip-link |
| PASS | Tab reaches searchInput | found after 13 tabs |
| PASS | Ctrl+K focuses searchInput | |
| PASS | / focuses searchInput | |
| PASS | Escape clears search + blurs | value='', blurred=True |
| PASS | Enter expands subject card | |
| PASS | Space collapses subject card | |
| PASS | Enter expands sidebar year | |
| PASS | Escape closes export panel | |
| PASS | Tab reaches bookmark button | focused: bookmark-btn |
| PASS | Practice toggle is focusable | |

### C. 手機深度測試

| 狀態 | 測試項目 | 細節 |
|------|---------|------|
| PASS | 375px: no horizontal overflow | scrollWidth=375 |
| PASS | 320px: no horizontal overflow | scrollWidth=320 |
| PASS | Hamburger opens sidebar | |
| PASS | Overlay click closes sidebar | |
| PASS | Sidebar link click closes sidebar (R1 #1 fix) | sidebar correctly closes |
| PASS | Escape closes mobile sidebar | |
| PASS | All visible touch targets >= 44px | all pass |
| **FAIL** | select#subjectFilter width <= viewport (R1 #2) | width=792, right=808, maxWidth=none |
| PASS | filter-chip no page overflow (R1 #3 fix) | scrollWidth=375 |

### D. 深色模式視覺一致性

| 狀態 | 測試項目 | 細節 |
|------|---------|------|
| PASS | Dark mode activates | |
| PASS | Dark mode --bg is dark (#1a202c) | got: #1a202c |
| PASS | Dark mode --text is light (#e2e8f0) | got: #e2e8f0 |
| PASS | Search highlight in dark mode has visible style | bg=rgb(146, 64, 14), color=rgb(254, 243, 199) |
| PASS | Practice score panel visible in dark mode | gradient background correct |
| PASS | Free point cells styled in dark mode | gradient bg + gold border |
| PASS | Passage fragment styled in dark mode | bg=rgb(30,41,59), borderLeft=rgb(59,130,246) |
| PASS | Dark mode deactivates correctly | |

### E. 新功能驗證

| 狀態 | 測試項目 | 細節 |
|------|---------|------|
| PASS | highlightText: '警察' finds many matches | 1931 highlights in 55 cards |
| PASS | Search jump buttons appear for multi-match | 2 buttons (prev/next) |
| PASS | Search jump: next button works | counter='1/1931', hasCurrent=true |
| PASS | Search jump: prev button works | counter='1931/1931' |
| PASS | Search index pre-built with entries | cache size=63 |
| PASS | Index: Tab first focuses skip-link | '跳至類科列表' href=#categories |
| PASS | Category: Tab first focuses skip-link | '跳至搜尋' |

### F. 按鈕位置一致性

| 狀態 | 測試項目 | 細節 |
|------|---------|------|
| INFO | Index dark toggle position | right side (x=1204) |
| INFO | Category dark toggle position | left side (x=32) |
| **FAIL** | Dark toggle position consistent across pages (R1 #6) | index=right, category=left |

### G. 控制台錯誤檢查

| 狀態 | 測試項目 | 細節 |
|------|---------|------|
| PASS | No JS errors on Index page | clean |
| PASS | No JS errors on Category page | clean |

### H. 無障礙 (ARIA/Focus) 檢查

| 狀態 | 測試項目 | 細節 |
|------|---------|------|
| PASS | :focus-visible rule exists in CSS | found in style.css |
| PASS | Search box has role=search | |
| PASS | Toolbar has role=toolbar | |
| PASS | Export panel has role=dialog | |
| PASS | Search stats has aria-live=polite | |
| PASS | Sidebar nav has aria-label | |

### I. 類科連結檢查

| 狀態 | 測試項目 | 細節 |
|------|---------|------|
| PASS | Index has 15 category cards | found 15 |

---

## 測試截圖

截圖存放於 `reports/screenshots/` 目錄：

| 檔案 | 說明 |
|------|------|
| `r2_keyboard_nav.png` | 鍵盤導航測試 |
| `r2_galaxy_fold_320.png` | Galaxy Fold 320px |
| `r2_mobile_375.png` | 手機 375px |
| `r2_dark_mode.png` | 深色模式 |

---

## 總結

Round 1 提出的 8 個問題中，**6 個已成功修復**，**2 個仍未修復**：
- R1 #2（select 溢出）：`body overflow-x: hidden` 部分緩解了問題（頁面不再水平捲動），但 select 元素本身仍然超寬（792px），需要加上 `max-width: 100%`。
- R1 #6（按鈕位置不一致）：首頁使用 `right: 2rem`，類科頁使用 `left: 2rem`，建議統一。

**Round 2 未發現新問題。** 鍵盤導航、深色模式、手機佈局、無障礙標記等均表現良好。

---

## 測試環境
- **工具**: Playwright (Python sync API)
- **瀏覽器**: Chromium (headless)
- **測試腳本**: `reports/round2_ux_test.py`
- **平台**: Windows 10 / MSYS2
