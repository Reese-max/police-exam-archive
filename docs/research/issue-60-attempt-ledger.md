# Issue #60 — 逐題 Attempt Ledger 驅動考前複習佇列（設計）

Design deliverable for `Reese-max/police-exam-archive#60`。
目前 `saveHistory()` 只存 aggregate score/time；本設計把 per-question
outcome 變成可重建的本機事實。

## 1. Schema

### 1.1 `AttemptEvent`（append-only ledger，原始事實）

```jsonc
{
  "questionId": "stable-id",          // cat/yr/sub/no 或既有穩定 id
  "attemptedAt": "ISO-8601",
  "outcome": "correct | wrong | unanswered | marked_review",
  "chosenAnswer": "B | null",
  "elapsedMs": 4200,                   // 僅資料可靠時保存
  "datasetHash": "sha256(題庫版本)",
  "quizMode": "official | custom | review",
  "filters": { "cat": "...", "yr": 113 }
}
```

### 1.2 `QuestionReviewState`（deterministic 派生，不黑箱）

```jsonc
{
  "questionId": "...",
  "attempts": 4, "wrongCount": 2, "unansweredCount": 0,
  "correctStreak": 1,
  "lastSeen": "...", "lastWrong": "...",
  "dueAt": "...",
  "reasonCodes": ["上次答錯","21天未複習"],
  "sourceCompat": "current | stale | review_required"
}
```

## 2. 「今日複習」Queue 優先序（重用 QuizEngine 渲染）

1. 最近答錯 / 未答 / 手動標記
2. 已到期的 review（dueAt ≤ now）
3. coverage gap（久未出現的科目）
4. 少量 exploration（未見過題目）

每題 UI 顯示 deterministic reason（「上次答錯」「連續 2 次答錯」
「標記回顧」「21 天未複習」「本科目近期覆蓋不足」）。

## 3. Deadline-aware scheduling

- 使用者自行設定目標考試日 + 每日題量/分鐘上限；不硬編考試日。
- `dueAt` 不應無聲落在 target date 之後。
- 剩餘弱項 > 可用容量 → 顯示 overload/backlog，不假裝計畫可完成。
- 可壓縮 priority，但不得因 deadline 把所有題標為已掌握。
- 可關閉 deadline mode 回到單純 due queue。

## 4. Local-first portability

- ledger / review state / settings 可 export/import。
- dataset 更新時依 stable questionId 重對應；hash 變更 → `STALE /
  REVIEW_REQUIRED`，不把舊結果無聲套到新題。

## 5. 不做什麼

- 不用黑箱 AI / 假精準「通過機率」；MVP 是 deterministic heuristic。
- FSRS 類模型只在足夠 fixture/evidence 後才評估。
- 不產生新考題——只深化官方題庫的可追溯練習。
