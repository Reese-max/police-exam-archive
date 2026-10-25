The required Python gate also runs the original quiz page in Node with a pinned,
independent IndexedDB implementation. Install its single test dependency first:

```sh
npm ci --prefix tests --ignore-scripts
REQUIRE_NODE_FOR_TESTS=1 python -m pytest tests/ -q
```

`quiz_dom_harness.js` awaits the original page's transaction completion rather
than treating synchronous localStorage comparisons as cross-tab ownership.
The durability cases cover stale legacy renderer writes, simultaneous claims,
fresh answers accepted after the banner was offered, completion tombstones,
timer/answer overlap, corrupt records, aborted transactions, and failed cleanup
after a durable save (including the later no-recovery transition). Failed finish
keeps the original exam and clock until a retry commits the tombstone. These are Node
regressions; actual browser close/reopen durability needs browser verification.

## #109 主操作對比驗收

指定基底 `36fb1519` 已包含 `740c42f1` 的字色修正；本次保留該修正，
補齊正常來源驗收及測試伺服器隔離。

```sh
cd 考古題網站
PLAYWRIGHT_PORT=18769 npx playwright test tests/audit-legibility.spec.js --workers=2 --output=../output/playwright/issue-109
```

Playwright 的測試站啟動前會先呼叫既有的 `scripts/build_search_index.py`，
使用完整產生索引與原本的 MiniSearch CDN。沒有替換網頁、腳本或資料回應，
並逐位元組比對實際載入的 HTML 與本 worktree 原始碼。需要 Python、網站 npm
依賴、Chromium，以及可載入原本 CDN 的網路。

| 驗收 | 機制 |
| --- | --- |
| 深淺色主操作字色均達 4.5:1 | 390px、1280px × light、dark 的實際 computed foreground/background |
| normal／hover／focus | 等待按鈕 transition 完成，使用滑鼠 hover、Tab focus-visible 與 Enter |
| 正常開始及搜尋 | 原始題池開始 20 題考試；原生啟動「憲法」搜尋並檢查結果與高亮 |
| 同族字色及停用語意 | 原有 owned fixture 測試保留，並補齊已選、回復、交卷與重試控制的 focus |
| 不更動資料及操作行為 | 產品 HTML、CSS、JavaScript 與來源題庫沒有差異 |

第一次完整來源測試暴露就緒等待不足；下一次收到 `索引載入失敗：HTTP 404`。
檢查後確認原設定的 8765 埠被另一個 issue worktree 使用。現在可透過
`PLAYWRIGHT_PORT` 指定埠（預設仍為 8765），且埠已占用時直接失敗，避免驗證別份來源。
這些失敗是驗收環境的 RED；原始對比缺陷在指定基底已修復，本次沒有該產品缺陷的 RED。
測試不代表真人使用成效、輔助科技語音或全站 WCAG 認證。

本機驗證：相關測試由 6 增為 10 個並全數通過；完整瀏覽器套件 56 個、
`REQUIRE_NODE_FOR_TESTS=1 python -m pytest tests/ -q --tb=short` 的 400 個，
以及 Analytics Node 測試的 28 個均通過（exit 0）。JavaScript syntax、
quiz answer contract、類科頁、首頁統計、corpus claims 與 115 integrity 檢查亦通過。
版面掛載依 CI 的 apply → check 順序在實際頁面的暫存副本驗證，未更動 worktree HTML。
沒有新增 lint、coverage ratchet、CRAP 或 mutation 工具。

| 主操作實測（兩種寬度相同） | normal／focus | hover |
| --- | --- | --- |
| light：白字／深綠底 | 4.8433:1 | 6.1451:1 |
| dark：深色字／薄荷綠底 | 6.6098:1 | 7.9717:1 |

四組測試的 computed 色彩紀錄與 8 張實際檢視過的截圖保存在
`output/playwright/issue-109/`。原始題庫與產品檔案相對指定基底的差異為零。
