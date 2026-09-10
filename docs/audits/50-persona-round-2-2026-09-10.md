# 50-Persona Audit — Round 2

Date: 2026-09-10
Protocol: `Reese-max/autodev-ng/docs/portfolio-audit/2026-09-06-50-persona-audit.md`

> Fixed 50-persona model simulation plus current default-branch/repository evidence review; not 50 human participants.

## Round 2 result

Status: **P2 OPEN — NOT CLEAN**

Round 1's image-choice finding #58 remains open on the current default branch. PR #59 contains a proposed remediation and records branch/local validation, but it is still open and unmerged, so this audit does not credit it as default-branch or production evidence.

Round 2 also confirms a distinct current-corpus trust defect already tracked as Issue #61: the machine-readable manifest and executable data-quality tests use **36,760** non-duplicate choice questions, while user-facing quality claims in `README.md` still state **36,210/36,210 = 100%** and `考古題網站/quiz.html` still describes a 36,210-question pool. The unexplained delta is 550, matching the documented year-115 non-duplicate choice import.

This does **not** prove the 550 questions are malformed or untested. It proves the public denominator for the strongest completeness claims is stale relative to the current corpus, so a user cannot determine from the claim whether year 115 is inside the 100% scope.

## Fixed-persona rerun

The same fixed 50 IDs were applied to corpus discovery, practice/search trust, export and maintenance scenarios.

#61 materially affects:

- A04 candidate under time pressure: cannot tell whether current-year questions are included in the quality percentage.
- B04 research assistant: cannot cite a stable corpus denominator from README without reconciling another file.
- C01 public-sector/police user: provenance/completeness claims disagree across repository surfaces.
- C02 teacher: cannot confidently communicate whether a class pack includes the full current validated choice corpus.
- C05 DevOps/SRE: CI-generated totals do not govern all public count/quality projections.
- D01/D02 management: summary quality metrics are not traceable to one current source of truth.
- D05 audit/compliance: a stated 100% result has an ambiguous population.
- E03 low-digital-confidence user and G05 slow-network user: README/text surfaces can be the only evidence they read, so the stale denominator is material.
- H05 first-time maintainer: future yearly imports can repeat the drift because the denominator strings are manually maintained.
- J01 large-data and J05 expert/export users: corpus identity and quality scope must reconcile before downstream use.

No additional distinct P0/P1/P2 fingerprint was confirmed in this round after deduplication against #58, #61 and active remediation work.

## Actionable issues

- #58 — `[P2][50-persona audit] Preserve and render the 4 image-based answer choices` — still open; PR #59 is not merged.
- #61 — `[P2][RELIABILITY][DOCUMENTATION] Keep dataset quality denominators in sync with the current corpus` — current Round-2 finding.

For #61, derive all public corpus counts and quality numerator/denominator values from one versioned machine-readable quality summary and fail CI when README/site/manifest/test projections drift.

## Runtime evidence boundary

Static/default-branch evidence is sufficient to confirm the denominator inconsistency. This round does not claim that a deployed Pages remediation exists: #61 has no merged fix, and #58's proposed fix remains in open PR #59.

PR #59's own recorded branch/local browser checks are useful candidate evidence but are not treated as merged default-branch or production verification. After either issue lands, verify the deployed Pages artifact against the same commit/corpus identity.

## CLEAN gate

1. Merge and verify a remediation for #58, including deployed category/search/quiz/image/PDF paths and accessibility/source-image behavior.
2. Resolve #61 with one generated quality/corpus identity contract across all public surfaces and a CI drift gate.
3. Re-run the same fixed 50 personas on the resulting default-branch SHA.
4. Obtain required production/runtime evidence for remediated user paths.
5. Require two consecutive no-new-P0/P1/P2 rounds.

Consecutive no-new-P0/P1/P2 count: **0/2** because Round 2 confirms P2 #61.