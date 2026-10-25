# #110 窄螢幕複習設定驗收

本次 admitted base 為 `36fb1519ed08d40d0d22a8f41672e6d97f2953ef`，已包含 PR #111／`740c42f1` 的修正。本次沿用既有 `.deadline-grid` 響應式 CSS、`saveReviewSettingsFromForm()` 與 `AttemptLedger`，只補強測試、文件與證據，沒有重做產品修正。

## 紅燈來源與順序

先補強既有 `考古題網站/tests/audit-legibility.spec.js`，再以 issue 所指的修正前 `8f8f2ce6340b568d663d526188053d0c2ae7c3c9:考古題網站/quiz.html` 重播相同驗收。測試期間暫置該檔，結束後以 `finally` 還原原始 bytes；未切換分支。紅燈是歷史缺陷的回歸證明，**不是 admitted base 失敗**。

```bash
cd 考古題網站
node node_modules/@playwright/test/cli.js test tests/audit-legibility.spec.js --grep 今日複習 --workers=1 --timeout=60000
```

歷史來源：結束碼 **1**，**2 failed / 1 passed**。保留 [失敗輸出](red-test-output.txt)、[初始及重載幾何](red-layouts.json) 與 [320px](red-320.png)、[390px](red-390.png)、[1280px](red-1280.png) 初始截圖。另一次 JSON reporter 執行用於保存附件，結果相同。

還原 admitted base 後，三種寬度皆轉綠。最後加入字型載入等待，讓幾何與截圖使用相同字型狀態，再次通過三種寬度驗收；保留 [初始及重載幾何](green-layouts.json) 與 [320px](green-320.png)、[390px](green-390.png)、[1280px](green-1280.png) 重載後截圖。

| 寬度 | 歷史欄數 → 採用來源欄數 | grid client / scroll（歷史 → 採用） | 數字內容寬度（題量／分鐘／估算） |
|---|---|---|---|
| 320px | 4 → 1 | 226 / 245 → 226 / 226 | 0／0／3 → 204／204／204px |
| 390px | 4 → 1 | 296 / 296 → 296 / 296 | 18／18／18 → 274／274／274px |
| 1280px | 4 → 4 | 690 / 690 → 690 / 690 | 142／142／142px，維持不變 |

## 驗收對照

| 要求 | 結果與機制 |
|---|---|
| 320／390px 標籤、數值可讀，控制項留在面板內 | ✅ 初始及重載後量測單欄、無 grid 溢位、每個 label/input 邊界與標籤行數；數字內容空間至少為量測文字寬度加 16px 原生 spinner 預留。 |
| 原生鍵盤、編輯、自動儲存、重載 | ✅ Space 啟用截止日、Tab 走訪欄位、鍵盤輸入三個數值後 Tab 觸發 change/blur。重載後比對全部五個 UI 設定與 `AttemptLedger.getSettings()`；日期為 2099-12-31，題量為 37／42／53，分鐘涵蓋 0／1440，估算涵蓋 0.5／120。 |
| 保留桌面配置、限制與資料語意 | ✅ 1280px 四欄及三個 number 欄位 max=200／1440／120；產品 HTML、JS、storage schema 與題庫均未變動。 |
| 測試正常採用來源 | ✅ 每次導覽的 HTTP HTML 本文必須等於 worktree 的 `quiz.html`。該檔 Git blob 仍為 `5a14da935cd8c6ab8fd1ef6d26855780a214af6f`，與 admitted base 相同。 |
| 留存實際瀏覽器回歸 | ✅ 使用 Chromium、本機 HTTP、隔離 browser context；只替換兩題 owned index 與非搜尋用 MiniSearch fixture，實際 DOM、CSS、原生 localStorage 與服務程式照常執行。 |

## 完整檢查

相關檔案測試數由 **6 → 6**，補強既有三個寬度案例的斷言，未複製新測試。以下皆結束碼 **0**：

```bash
PYTHONUTF8=1 REQUIRE_NODE_FOR_TESTS=1 python -m pytest tests -q --tb=short
# 400 passed in 207.03s

(cd 考古題網站 && node node_modules/@playwright/test/cli.js test --workers=1 --timeout=60000)
# 52 passed (1.9m)

node --check 考古題網站/tests/audit-legibility.spec.js
node 考古題網站/tests/quiz-answer-contract.js
# quiz answer contract passed
node --test 考古題網站/tests/analytics-pair.test.js 考古題網站/tests/analytics-pair.regression.js
# 28 passed, 0 failed
```

完整瀏覽器套件後，針對最後的字型等待補強，重新執行三個寬度，再執行整份 `audit-legibility.spec.js`。driver 的精確重跑命令及結果記於根目錄 `.issue-loop-evidence.json`。獨立唯讀審查沒有實質 findings；`git diff --check` 通過。未新增 dependency、lint、coverage ratchet、CRAP 或 mutation 工具。

未 push、開 PR、合併、關 issue、部署或執行遠端 CI；未宣稱實體觸控效能、其他瀏覽器或全面無障礙認證。
