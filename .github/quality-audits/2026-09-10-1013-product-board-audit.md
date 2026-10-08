# Product Board Audit — police-exam-archive

- Audit date: 2026-09-10
- Repository: `Reese-max/police-exam-archive`
- Default branch reviewed: `master`
- Evidence snapshot: `a0b5dbb9352b5558dbe62445c6452947dbd2501b`
- Method: discovery, current competitive research, 13-role board, 50 synthetic personas, switching test, Red Team, Quality Gate, GitHub write closure.
- Persona results and preference shares are synthetic simulations, not human research or market share.

## Executive Summary

**Decision: INVEST, gated by SIMPLIFY/FIX.** The product should be the canonical, reproducible truth layer for Taiwan police-exam questions: official provenance, faithful text/image/answer representation, deterministic builds, and a lightweight practice surface over the same identities. It should not become a generic AI tutor, LMS, social network, or account-heavy analytics product.

The corpus has 2,049 non-duplicate JSON files, 36,760 choice questions, 5,758 essays, source URLs/hashes, duplicate marking, deterministic tests, and active work on four image-choice questions. The new issue is a trust-contract drift: manifest/tests use 36,760 choices, but README quality claims and a quiz source comment retain 36,210. The 550-question delta exactly equals the documented 115-year unique-choice import. Current tests iterate 36,760; evidence supports stale public denominators, not lost questions.

Quality-Gate mapping: [#61 `[P2][RELIABILITY][DOCUMENTATION] Keep dataset quality denominators in sync with the current corpus`](https://github.com/Reese-max/police-exam-archive/issues/61).

CEO’s three actions: (1) #61 single generated quality contract, (2) complete and production-verify #58/PR #59 image fidelity, (3) then build the smallest deterministic attempt ledger in #60. Do not build AI tutoring, cloud learner accounts, social/community features, marketplace, or pass prediction.

## Project Discovery

| Area | Evidence | Status |
|---|---|---|
| Product | Open structured data + static search/analytics/practice web app | CONFIRMED |
| Users | Police candidates, tutors, maintainers, researchers, developers | LIKELY |
| Core job | Find, query, export, and practise official questions with provenance | CONFIRMED |
| Inventory | 2,049 unique JSON; 36,760 choice; 5,758 essay; 42,518 total | CONFIRMED |
| Tests | `test_data_quality.py` loads non-duplicates and validates 36,760 choices | CONFIRMED |
| 115 import | 550 unique choice + 157 unique essay; 41 duplicate copies | CONFIRMED |
| README quality | 36,210/36,210 option and answer claims | CONFIRMED stale scope |
| Quiz copy | Inline comment says 36,210-choice corpus | CONFIRMED stale copy |
| CI | pytest, home-stats check, search-index, analytics/category checks | CONFIRMED config |
| Snapshot CI | No workflow run associated with `a0b5dbb...` | CONFIRMED; no green claim |
| Image limitation | Four placeholder image questions, #58 + active PR #59 | CONFIRMED |
| Open work | PR #50, #57, #59 and dedicated branches | CONFIRMED |
| Prior audit | 2026-09-06 persona Round 1 focused on #58 | CONFIRMED |
| Full product-board audit | None found before this report | CONFIRMED |

Code/CI confirms the mismatch and current iteration scope. It is **LIKELY** that copied pre-115 strings missed the import because the delta exactly equals 550. Deployed Pages counts, search pool, image rendering, and accessibility need runtime checks. Real user impact is **UNKNOWN**.

## Competitive Intelligence

Research refreshed 2026-09-10.

| Dimension | This product | MOEX | Yamol | Quizlet | Anki | PDFs/scripts |
|---|---|---|---|---|---|---|
| Target | Police candidates/data users | All examinees | Taiwan candidates | General learners | Power learners | Technical users |
| Value | Structured official corpus | Authoritative PDFs | Exam practice/explanations | Adaptive study | Review scheduling | Local control |
| Killer feature | Provenance + JSON/SQLite | Source authority | Taiwan catalog | Polished adaptation | Mature revlog/stats | Portability |
| Onboarding | README/static site | Search/PDF | Web/account | App/web guided | Steeper | High burden |
| AI/automation | Deterministic parse/audit | None | Platform tooling | Strong AI/adaptive | Algorithmic scheduling | User-defined |
| Mobile | Responsive static | Web/PDF | Web/mobile | Native | Native | Weak |
| Reliability | Strong tests; count drift | Official | Closed internals | Managed SaaS | Mature local model | Operator-dependent |
| Privacy | Local/static | Government | Account service | Account/data collection | Local + optional sync | Local |
| Pricing | Open repo | Public | Freemium | Freemium/subscription | Mixed | Tool-dependent |
| Open/closed | Open transforms; source rights apply | Public docs | Closed | Closed | Open desktop ecosystem | Open/local |
| Main advantage | Police-specific reproducibility | Authority | Explanations/catalog | UX/adaptation | Review depth | Ownership |
| Main weakness | Governance/image/runtime gaps | PDF friction | Opaque provenance | Generic/account | Setup burden | No shared contract |

Sources: [MOEX question portal](https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx), [Yamol police-law catalog](https://yamol.tw/cat-%E8%AD%A6%E5%AF%9F%E2%97%86%E8%AD%A6%E5%AF%9F%E6%B3%95%E8%A6%8F-131.htm), [Anki statistics manual](https://docs.ankiweb.net/stats.html), [Quizlet Android listing](https://play.google.com/store/apps/details?id=com.quizlet.quizletandroid).

- **MUST MATCH:** current scoped counts, stable source links, accessible core practice, production verification.
- **SHOULD BE BETTER:** one generated provenance/quality artifact across README, manifest, site, tests, exports.
- **DIFFERENTIATOR:** official PDF/hash → structured question → search/practice identity graph.
- **DO NOT COPY:** generic generated questions, cloud-account requirement, social feed, opaque pass probability, LMS breadth.

## Virtual Executive Board

| Role | Question / opportunity / priority |
|---|---|
| CEO | Invest in provenance; #61 then #58 then #60. |
| CPO | Users must understand what “100%” covers; make quality a visible contract. |
| CTO | Generate every annual-import projection from one artifact. |
| Staff Engineer | Shared loader/schema, deterministic projections, seeded drift tests. |
| UX Lead | Put snapshot/scope beside counts, not in hidden notes. |
| UX Researcher | Later test unique-vs-raw terminology with real candidates. |
| Growth Lead | “Current through 115, reproducibly verified” beats feature volume. |
| CFO/Business Analyst | Remove duplicated handwritten stats before new surfaces. |
| Security/Privacy | Keep static/local; no identity or telemetry required. |
| QA Lead | One-question import and duplicate fixtures must gate drift. |
| SRE Lead | Publish deployed build/version receipt. |
| Accessibility Specialist | README/text surfaces must expose the same truth. |
| Support Lead | “Are 115 questions included and verified?” needs one answer. |

Minority opinion: manually fix two strings because executable tests already cover 36,760. Majority: that fixes one snapshot, not annual-import drift; a small shared artifact and CI check are proportionate, while a new dashboard is not.

## 50 Synthetic Personas

Exactly 30 baseline (B, 60%) and 20 rotating (R, 40%). Every row is a simulated journey.

| ID | Set | Background/device/network | Goal | Expectation | Task/journey | Friction | Outcome/comment | Sev | Suggestion |
|---|---|---|---|---|---|---|---|---|---|
| P01 | B | 24歲初考生／Android／4G | 確認115年已納入 | 最新且完整 | README→品質 | 36,760 vs 36,210 | 失敗：不知新題是否受驗 | P2 | 單一分母 |
| P02 | B | 31歲重考生／桌機 | 找警察法規原題 | 可追官方 | 搜尋→來源PDF | 無靜態缺陷 | 成功：來源清楚 | — | 保留來源hash |
| P03 | B | 22歲低熟練／手機 | 開始20題測驗 | 題池可信 | 首頁→篩選→測驗 | 題池基準未解釋 | 部分成功 | P3 | 顯示snapshot |
| P04 | B | 38歲家長考生／慢網 | 快速複習 | 離線可用 | 快取→測驗 | 正式池數未實測 | 待runtime | P3 | build版本 |
| P05 | B | 27歲螢幕閱讀器使用者 | 讀懂覆蓋率 | 文字即真相 | README→品質 | 文字數字衝突 | 失敗：100%不可解讀 | P2 | 文字版生成摘要 |
| P06 | B | 25歲鍵盤使用者／筆電 | 完成測驗 | 完整鍵盤操作 | 篩選→選項→送出 | 只見靜態支援 | 待runtime | P2 | 鍵盤/SR回歸 |
| P07 | B | 34歲補教老師／筆電 | 製作115教材 | 資料已驗證 | README→JSON→匯出 | 550題範圍不明 | 部分成功 | P2 | 版本化品質artifact |
| P08 | B | 29歲資料分析師／Linux | 查詢唯一題目 | 統計可重播 | SQLite→stats | raw/unique分散 | 部分成功 | P3 | 並列排除數 |
| P09 | B | 45歲講師／桌機 | 驗證答案合法率 | 完整分母 | 品質→tests | 公開分母舊 | 失敗 | P2 | 連結CI receipt |
| P10 | B | 20歲低頻寬／手機 | 只看README | 不載入圖表也可信 | Repo首頁→品質 | 無法依賴其他頁 | 部分成功 | P2 | 治理README |
| P11 | B | 26歲隱私敏感 | 免帳號練習 | 本機完成 | 站點→quiz | 無帳號 | 成功 | — | 維持local-first |
| P12 | B | 33歲power user | 多條件篩選 | 結果範圍可知 | facets→search | count provenance隱含 | 部分成功 | P3 | 結果scope |
| P13 | B | 21歲圖像題考生 | 作答圖題 | 選項可見 | quiz→圖題 | #58已知限制 | 失敗／active fix | P2 | 完成#58 |
| P14 | B | 36歲教師／iPad | 匯出圖題PDF | 順序正確 | 分類→PDF | #59未進master | 待runtime | P2 | 合併後實測 |
| P15 | B | 28歲法律研究者 | 引用原題 | 可追溯 | 搜尋→source/hash | 無 | 成功 | — | 保留hash |
| P16 | B | 41歲maintainer | 匯入116年 | 所有投影同步 | pipeline→tests→docs | 手寫字串可漂移 | 失敗安全閘 | P2 | CI drift check |
| P17 | B | 30歲QA | 重算總數 | 執行結果一致 | pytest→manifest | 程式計數一致 | 成功 | — | 輸出共用receipt |
| P18 | B | 23歲Mac開發者 | 本機查詢 | 快速啟動 | README→examdb | 未clean-clone實測 | 大致成功 | P3 | clean-clone test |
| P19 | B | 52歲低視力／zoom | 讀統計 | 放大可用 | analytics→cards | 未runtime | 未知 | P2 | zoom/contrast測試 |
| P20 | B | 19歲閱讀障礙 | 短題組練習 | 低負荷 | filter→quiz | 無真人可用性證據 | 未知 | P3 | 先研究 |
| P21 | B | 35歲考試教練 | 比較年度覆蓋 | 年度可信 | analytics→year | 品質分母漂移 | 部分成功 | P2 | 圖表旁標scope |
| P22 | B | 27歲API開發者 | 重用JSON | 權利/格式清楚 | clone→schema | 授權邊界簡短 | 部分成功 | P3 | 另做權利研究 |
| P23 | B | 32歲offline使用者 | 無雲練習 | 下載後可用 | 下載→local site | 靜態架構適合 | 成功 | — | 保留離線 |
| P24 | B | 44歲support志工 | 回答覆蓋問題 | 一句話可答 | README→import report | 須手算550 | 失敗效率 | P2 | reconciliation table |
| P25 | B | 25歲焦慮考生 | 相信100% | 定義清楚 | landing→quality | 分母矛盾 | 失敗信任 | P2 | metric scope |
| P26 | B | 37歲a11y測試者 | 驗證語意 | 符合核心操作 | 靜態DOM→操作 | 缺實機證據 | 未知 | P2 | AT matrix |
| P27 | B | 29歲資安工程師 | 檢查外部依賴 | 風險透明 | source→CDN | 無可證缺陷 | 通過靜態 | — | 另作threat model |
| P28 | B | 22歲平板考生 | 續作錯題 | 逐題狀態保留 | quiz→history | aggregate-only | 已由#60追蹤 | P2 | 不重複issue |
| P29 | B | 40歲數位典藏員 | 追更正答案 | 更正可稽核 | report→hash | 證據強 | 成功 | — | 保留audit trail |
| P30 | B | 26歲開放資料貢獻者 | 年度更新 | 一處改全站 | docs→pipeline | 無單一stats source | 部分成功 | P2 | 共用generator |
| P31 | R | 58歲退休警員／手機 | 瀏覽舊題 | 手機清楚 | search→paper | 未真機 | 未知 | P3 | 真機測試 |
| P32 | R | 18歲偏鄉／低階Android | 載入題庫 | 慢網可用 | cold load→quiz | 未量測效能 | 未知 | P3 | 量測後再立項 |
| P33 | R | 46歲補習班主 | 稽核課綱 | 完整到115 | counts→category | 分母衝突 | 失敗證明 | P2 | snapshot對帳 |
| P34 | R | 27歲記者 | 核對原文 | 直達官方 | search→PDF | 無 | 成功 | — | 維持original |
| P35 | R | 39歲政府資料管理者 | 評估再利用 | 單一事實 | README→manifest/tests | 多個truth | 部分成功 | P2 | machine artifact |
| P36 | R | 24歲色覺差異 | 讀圖表 | 非只靠色彩 | analytics | 未runtime | 未知 | P3 | 可及性實測 |
| P37 | R | 30歲斷線使用者 | 重載後續作 | 狀態可復原 | quiz→offline→reload | 未測 | 未知／#60 | P3 | 納入#60 |
| P38 | R | 28歲雙語考生 | 搜英文段落 | passage完整 | search passage | 程式支援 | 大致成功 | — | 固定fixture |
| P39 | R | 33歲PDF使用者 | 列印含圖題 | 順序與來源正確 | category→export | #59 active | 待runtime | P2 | 不重複#58 |
| P40 | R | 21歲ADHD考生 | 10題短練習 | 快速開始 | filter→10題 | 核心適合 | 成功 | — | 避免膨脹 |
| P41 | R | 48歲政策訓練員 | 找送分題 | 特殊值明確 | query→results | README有說明 | 成功 | — | 保留語意 |
| P42 | R | 25歲CI開發者 | 抓過期文件 | 漂移即失敗 | 改fixture→CI | 現CI漏字串 | 失敗 | P2 | seeded drift |
| P43 | R | 36歲資料科學講師 | 教provenance | 可展示流程 | manifest→report | 總數分散 | 部分成功 | P2 | artifact graph |
| P44 | R | 62歲大字體使用者 | 只讀README | 同一真相 | zoom→quality | 數字衝突 | 失敗 | P2 | 單一表 |
| P45 | R | 20歲共用電腦使用者 | 私密練習 | 無帳號 | site→quiz | 無帳號 | 成功 | — | 不建auth |
| P46 | R | 29歲動作障礙 | 鍵盤作答 | 原生操作 | controls→radio | 待runtime | 未知 | P2 | 鍵盤/SR |
| P47 | R | 34歲release manager | 核准年度匯入 | 投影全綠 | PR→CI→report | 公開投影未全受控 | 失敗信心 | P2 | block drift |
| P48 | R | 23歲Safari使用者 | 分享PDF | 下載可靠 | quiz→export/share | 未真機 | 未知 | P3 | 合併後測 |
| P49 | R | 43歲內容編輯 | 修正官方答案 | 保留來源 | hash→JSON→audit | 流程強 | 成功 | — | 保留紀錄 |
| P50 | R | 31歲portfolio architect | 跨產品共用ID | 語意穩定 | corpus→learner state | identity contract未完整 | 部分成功 | P2 | #61先於#60 |

Coverage: ages 18–62; candidates, tutors, maintainers, QA/release, developers, researchers, support, public-data and accessibility roles; Android/iOS/tablet/desktop; screen reader, keyboard, low vision, slow/intermittent network, first-time and power users. Simulated outcomes: 17 success/likely, 18 partial/fail, 15 unknown/runtime. Fifteen personas relied on a reconciled denominator; six could not interpret “100%” and nine requested explicit scope/version.

## Synthetic Preference Share

| Choice | Personas | Share | Main reason |
|---|---:|---:|---|
| police-exam-archive | 19 | 38% | Police-specific structured official data |
| MOEX portal/PDF | 9 | 18% | Absolute source authority |
| Yamol | 9 | 18% | Explanations and Taiwan exam catalog |
| Quizlet | 6 | 12% | Polished adaptive/mobile study |
| Anki | 5 | 10% | Review control |
| PDFs/local scripts | 2 | 4% | Offline ownership |

Simulation only, not market share or a survey.

## Red Team

1. The 550 may be omitted from tests—contradicted by current 36,760 iteration.
2. The metric may be historical—then it still lacks a snapshot label.
3. Two-line manual fix could work now—but does not prevent next-year drift.
4. Do not overbuild—a static artifact/check is enough; no backend/dashboard.
5. Persona set favors provenance—counterbalanced by users choosing guided competitors.
6. Competitors are heterogeneous—intentional because product spans source and practice.
7. Do not conflate #58 and #61—image usability and count governance are distinct.
8. Do not claim production from source—runtime stays pending.
9. Do not pursue parity—accounts, AI tutor and social features are rejected.
10. Prefer removal—remove handwritten duplicates or make them generated projections.

## Findings and Issue Mapping

| ID | Finding | Type | Priority | Evidence | Gate | Mapping |
|---|---|---|---|---|---|---|
| F-01 | 36,760 current choices vs 36,210 README/quiz quality scope; 550 equals year-115 import | RELIABILITY / DOCUMENTATION / DATA_QUALITY | P2 | CONFIRMED | PASS | NEW #61 |

Stable fingerprint: `police-exam-archive + corpus quality statistics + after 115 import + README/quiz retain 36,210 while manifest/tests use 36,760 + manually copied denominators drift`.

- NEW: [#61](https://github.com/Reese-max/police-exam-archive/issues/61).
- UPDATED: none.
- REOPENED: none.
- RESEARCH: none.
- SKIPPED_LOCKED: #58/PR #59, #56/PR #57, PR #50.
- ISSUE_WRITE_BLOCKED: none.
- AUDIT_DEFAULT_BRANCH_WRITE_BLOCKED: HTTP 409, required PR plus four expected checks. This report is preserved on a dedicated audit branch/PR.

## Roadmap

**NOW:** #61 generated quality contract; complete #58/PR #59; keep annual imports deterministic.

**NEXT:** #60 minimal attempt ledger after stable corpus identity; deployed receipt; keyboard/screen-reader/zoom/mobile/slow-network checks.

**LATER:** shared evidence IDs with `exam-archive`, `police-exam-practice`, `cyber-prep-coach`; terminology research; read-only API only after demand.

**DON'T:** AI tutor, generated-question flood, cloud accounts, social feed, marketplace, leaderboard, LMS, pass prediction, or analytics backend for counts.

## Change From Previous Round

The 2026-09-06 persona audit focused on #58. This round keeps #58 **STILL REPRODUCIBLE ON MASTER / ACTIVE IMPLEMENTATION / NEEDS_RUNTIME_VERIFICATION**, does not touch PR #59, adds the first full product-board report, and maps the independent year-115 denominator drift to #61.

## Regression

| Object | State | Evidence/action |
|---|---|---|
| #58 | STILL REPRODUCIBLE on master; active fix | PR #59; skipped locked |
| #60 | OPEN strategic gap | No duplicate/update |
| #61 | NEW / CONFIRMED | Created, locked, mapped |
| Prior CI-green claim | CANNOT VERIFY for `a0b5dbb...` | No workflow run; no green claim |

Verified fixed: 0. PR/code alone is insufficient without acceptance and runtime evidence.

## Runtime Pending

Deployed Pages count; browser search/quiz pool reconciliation; post-merge #58 image/category/search/quiz/PDF checks; keyboard, screen reader, zoom, reduced motion, mobile, slow-network, and offline paths. No human usability, learning outcome, accessibility conformance, or market-share claim is made.

## Decision Memo

- **What:** canonical, versioned police-exam truth layer with lightweight practice.
- **Who:** candidates, tutors, maintainers, researchers, developers.
- **Why choose it:** structured police-specific breadth, local access, source hashes, deterministic audits.
- **Why competitors:** MOEX authority; Yamol explanations; Quizlet UX; Anki scheduling.
- **Gaps:** metric consistency, image fidelity, runtime/accessibility evidence, per-question state.
- **Moat:** official-source evidence identity graph.
- **Top priorities:** #61, #58, #60.
- **Engineering:** generated stats, stable IDs, drift gates, deployed receipts.
- **UX:** clear scope, source navigation, image accessibility, local-first flow.
- **Do not build:** AI tutor, LMS, accounts, community, marketplace, pass prediction.
- **Remove:** handwritten count duplicates that cannot trace to the current artifact.
- **Risks:** trust drift, import inconsistency, source-rights ambiguity, image fidelity, fragmented identities.
- **Experiments:** one-screen coverage comprehension; one-question import replay; deployed-artifact comparison; AT tests.
- **Decision:** **INVEST**, gated by **SIMPLIFY/FIX**.

## Portfolio CEO Review

Rank: (1) `police-exam-archive` INVEST as canonical corpus; (2) `cyber-prep-coach` INVEST WITH SME RELEASE GATE; (3) `exam-archive` MAINTAIN/SIMPLIFY; (4) `police-exam-practice` MAINTAIN AS THIN COMPATIBILITY.

Share a versioned question/evidence ID, accessible answer/source components, portable attempt-event schema, and build receipts. Do not duplicate quiz engines or learner truth. No shared auth or AI gateway is needed yet; later AI must be read-only and source-grounded.

## Mandatory Verification

- Total Findings: **1**
- New Issues Created: **1**
  - [Reese-max/police-exam-archive #61 — `[P2][RELIABILITY][DOCUMENTATION] Keep dataset quality denominators in sync with the current corpus`](https://github.com/Reese-max/police-exam-archive/issues/61)
- Updated Existing Issues: **0**
- Reopened Issues: **0**
- Research Issues: **0**
- Duplicate Avoided: **8 symptom/candidate groups**—image symptoms → #58/PR #59; attempt/history/deadline → #60; all README/quiz/manifest/test/count variants → root #61.
- Issue Write Blocked: **0**
- Audit default-branch write blocked: **1**, preserved through audit branch/Draft PR.
- SKIPPED_LOCKED: **#58/PR #59, #56/PR #57, PR #50**
- Rejected Findings: **12**
  1. “550 questions missing”—contradicted by tests/manifest.
  2. Reopen #58—active branch/PR.
  3. New image issue—duplicate #58.
  4. New attempt issue—duplicate #60.
  5. AI tutor—bloat/source risk.
  6. Accounts/sync—unvalidated/privacy cost.
  7. Social/leaderboard—outside core job.
  8. Native app expansion—no priority evidence.
  9. Performance defect—unmeasured.
  10. Accessibility-conformance claim—no AT runtime.
  11. Immediate legal conclusion—requires owner/legal judgment.
  12. New count dashboard/backend—overengineered.
- Verified Fixed: **0**
- Priority distribution: **P0 0 / P1 0 / P2 1 / P3 0 / STRATEGIC 0**
- Highest Priority: **#61 among new findings; existing #58 should complete before #60**
- Finding mapping: **1/1 = 100%, PASS**
