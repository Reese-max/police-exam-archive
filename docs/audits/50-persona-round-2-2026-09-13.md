# 50-Persona Audit — Round 2

Date: 2026-09-13
Protocol: `Reese-max/autodev-ng/docs/portfolio-audit/2026-09-06-50-persona-audit.md`
Default branch: `master`
Audited default SHA before this report: `a0b5dbb9352b5558dbe62445c6452947dbd2501b`

> This is the same fixed A01–J05 simulated-persona audit plus current repository/CI evidence. It is not a 50-human usability study. Runtime claims below are limited to actual GitHub Actions/Pages execution evidence.

## Result

**NOT CLEAN — consecutive clean rounds: 0/2.**

Existing P2 #58 remains open, and existing P2 #61 is now formally included in the fixed-persona portfolio CLEAN gate. No duplicate issue was created because #61 already tracks the exact stable fingerprint.

## P2 #61 — public quality denominators drift from the current corpus

Current corpus truth is internally inconsistent across user-facing surfaces:

- `考古題庫/dataset_manifest.json` reports 36,760 non-duplicate choice questions, 5,758 essay questions, and 42,518 total questions.
- `tests/test_data_quality.py` asserts 36,760 choices and 42,518 total, and its current quality checks iterate the current choice collection.
- README inventory also reports 36,760 choices.
- The same README quality section still states `36,210/36,210 = 100%` for option completeness and answer legality.
- `考古題網站/quiz.html` still describes the search-backed pool as 36,210 choice questions.

The 550-question difference matches the documented non-duplicate 115-year choice import. This audit does **not** infer that those 550 questions are invalid or untested. The confirmed defect is that a reader cannot tell whether the advertised 100% quality claim covers the full current corpus or a pre-115 snapshot.

Under the portfolio severity rubric this is P2: it is a reproducible trust/provenance and maintainability defect that materially lowers confidence in the dataset, but there is no evidence here of data loss, unauthorized access, or a wrong official answer being served.

Affected fixed personas include A04, B04, C01, C03, D05, G02, G05, H05, and J05. These scenarios rely on a truthful denominator when deciding whether year 115 is covered, whether an export is complete, or which repository statistic is canonical.

## Existing P2 #58 — image-based answer choices remain unresolved

The README still documents four questions whose answer choices are represented as `[圖片選項]`. Issue #58 remains open, and there is no merged current-default evidence showing resolvable image assets/references across the quiz/search/user surfaces.

The same affected fixed-persona scenarios from Round 1 remain blocked, especially A04/A05, G02/G05 and J05. This round does not claim browser verification of those four items.

## Current execution evidence

GitHub Actions CI run `33989440607` executed on audited SHA `a0b5dbb9352b5558dbe62445c6452947dbd2501b` and completed successfully on actual GitHub-hosted runners for Python 3.10, 3.11 and 3.12. Recorded successful steps include checkout, dependency installation, `Run all tests`, 115 UI/static verification, responsive-layout verification, homepage-stat verification, search-index generation, analytics generation/currentness, and frontend JavaScript syntax checks.

GitHub Pages run `33989440679` on the same SHA also completed successfully.

These receipts prove the declared CI/deployment workflows executed successfully on the current default SHA. They do **not** prove that #61 is fixed, because the checked gate does not govern the stale README/quiz denominator strings. They also do **not** establish browser/accessibility acceptance for #58's four image questions.

Current branch metadata also reports `master` as protected with required status contexts for Data Quality Check and CI test jobs on Python 3.10/3.11/3.12. This is positive release-governance evidence, not a substitute for the unresolved product findings.

## Fixed 50-persona rerun summary

- A01–A03/A05: no distinct new P0/P1/P2 finding confirmed; browser/mobile completion is not newly executed here.
- A04/B04/C01/C03/D05/G02/G05/H05/J05: **FAIL/PARTIAL** on #61 trust/provenance scope; several also remain affected by #58 image fidelity.
- G01–G04 generally: no new runtime accessibility evidence sufficient for a pass; G02 specifically remains blocked on image/source accessibility.
- H01–H04: current CI/release governance has positive execution evidence, but this does not close content/provenance issues.
- I01–I05/J01–J04: no distinct new P0/P1/P2 fingerprint passed the issue quality gate in this round; required recovery/scale/browser runtime paths are not promoted to passed without execution evidence.

## Required follow-up

For #61, generate or verify all public corpus totals and quality denominators from one versioned machine-readable source of truth; add CI drift checks that fail when README/quiz/site projections disagree; then obtain current/recent successful execution evidence and re-run the fixed personas.

For #58, preserve faithful source-image assets/references for all four affected questions, render them in user-facing practice/search paths with accessible source context, add a regression gate for unresolved `[圖片選項]`, and execute the relevant browser/accessibility scenarios.

## CLEAN gate

No clean round is credited. #58 and #61 remain open P2 blockers, and required user-facing runtime paths are incomplete. The repository may enter CLEAN counting only after all P0/P1/P2 findings are resolved or explicitly dispositioned, required runtime evidence exists, and the same fixed 50 personas produce no new P0/P1/P2 findings for two consecutive current/recent rounds.
