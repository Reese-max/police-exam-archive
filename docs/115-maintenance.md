# 115 年題庫維護與驗收

## 正式流程

1. 下載器必須使用 TLS 憑證驗證，並檢查 PDF 檔頭、EOF、頁數與可解析性。
2. 修復工具只處理可由官方原卷確認的內容；答案一律透過「更正答案優先」入口。
3. `scripts/audit/finalize_115_import.py` 為資料遷移工具，會寫入資料；不得當成獨立驗證器。
4. CI 與合併前驗收只使用 `scripts/audit/verify_115_integrity.py`，該工具唯讀且不得產生 git diff。
5. 跨類科共同卷保留各類科副本供瀏覽，但搜尋索引只收正本，並以 `categories` 保存所有 membership。
6. 類科總覽頁在 Pages 建置時由 `scripts/build_category_pages.py` 重建。

## 合併門檻

- Python 全測試通過。
- Node 模擬考答案契約測試通過。
- 搜尋與分析資料可重建。
- 13 個 115 年類科頁可重建，且每頁可見 115 年。
- 唯讀稽核通過，執行後工作樹不得出現任何變更。
- PR 由維護者人工審查與合併；Repository 內不得保留自動 `gh pr merge` 工作流。

## Repository 設定

程式碼已移除所有自動合併工作流。Repository 管理員仍應在 GitHub Settings → Branches／Rulesets
對 `master` 啟用：禁止直接推送、要求 PR、至少一位核准者、要求 CI 與 Data Quality Check 通過。
