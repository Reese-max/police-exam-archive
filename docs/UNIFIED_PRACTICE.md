# 統一題庫、搜尋與線上練習架構

## 單一資料來源

`police-exam-archive` 是正式題庫的唯一來源。所有介面均從
`考古題庫/**/試題.json` 建置，不再於另一個 Repository 內嵌第二份題庫。

```text
考選部官方 PDF／答案
          ↓
考古題庫/**/試題.json
          ↓
scripts/build_search_index.py
          ↓
考古題網站/data/search-index.json（schema v2）
          ├─ search.html
          ├─ practice.html
          └─ quiz.html → practice.html
```

## 搜尋索引 schema v2

每題包含以下欄位：

```text
cat       正本類科
cats      共用考卷所屬的全部類科
yr        年度
sub       科目
no        原始題號
type      choice／essay
stem      題幹
passage   閱讀或克漏字共用文章
optA-D    選項
ans       官方答案
```

`cats` 可避免共用考卷去重後，其他類科在搜尋與模擬考中遺失共同科目。
`passage` 讓閱讀題組在搜尋與作答時都能取得完整文章。

## 官方答案語意

`考古題網站/js/answer-utils.js` 統一處理：

- 單一答案：`A`
- 複數正解：`A或C`、`A或C或D`
- 送分題：`送分` 或舊資料的 `*`

搜尋結果、模擬考計分與錯題回顧都必須使用此模組，不得自行以字串嚴格相等比較答案。

## 115 年共同英文

`scripts/repair/fix_115_common_english.py` 保存依考選部原卷核對的
第 41–60 題固定 fixture，並支援唯讀驗證：

```bash
python scripts/repair/fix_115_common_english.py --check
```

修復內容包含：

- 第 41–50 題英文斷詞與選項
- 第 50 題選項污染
- 第 51–55 題 `[[51]]` 至 `[[55]]` 填空位置
- 第 56–60 題完整 Zero Trust 閱讀文章

## 本地驗證

```bash
python scripts/repair/fix_115_common_english.py --check
python -m pytest tests/ -v --tb=short
python scripts/build_search_index.py --output /tmp/search-index.json
python scripts/check_frontend_inline_js.py
node 考古題網站/tests/answer-utils.test.js
node 考古題網站/tests/search-engine-v2.test.js
node 考古題網站/tests/quiz-engine-v2.test.js
```

## 舊練習站遷移

`police-exam-practice` 不再保存題庫與作答邏輯，只保留相容入口，將使用者
導向 `police-exam-archive/practice.html`，並保留 URL query 與 hash。

這樣可以維持舊書籤可用，同時避免兩份題庫逐年分岔。
