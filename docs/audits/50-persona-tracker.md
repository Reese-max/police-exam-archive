# 50-Persona Audit Tracker — Fixed A01–J05

Umbrella tracker: GitHub issue [#68](https://github.com/Reese-max/police-exam-archive/issues/68)
Protocol: `Reese-max/autodev-ng/docs/portfolio-audit/2026-09-06-50-persona-audit.md`

> The 50 personas are fixed synthetic simulations (A01–J05), not real-user
> research. This file is the repo-local tracking record only: it records
> round status and links independent actionable findings. It does **not**
> implement any finding and grants no worker, merge, or deploy authority
> (`auto_implementation: false`).

## Audit baseline

- Default branch: `master`
- Inspected product SHA: `a0b5dbb9352b5558dbe62445c6452947dbd2501b`
  (audit-only head `docs: add 50-persona audit round 1`; product baseline
  remains its parent `fe497aa9fac7a4e4a411e663edeef6c1c5356577`)
- Current status: **NOT CLEAN — CLEAN streak 0/2**

## Round status

| Round | Date | Record | Result | Findings |
|---|---|---|---|---|
| 1 | 2026-09-06 | `docs/audits/50-persona-round-1-2026-09-06.md` | NOT CLEAN | P2 #58 carried open |
| 2 | 2026-09-10 / 2026-09-13 | Candidate reports exist only in open, unmerged PRs #63 and #67 | NOT CLEAN | P2 #61 formally added to the CLEAN gate; #58 remains |
| 3 | 2026-09-16 | Central report `round-5-progress-2026-09-16-0825Z-fixed50-police-exam-archive-r3.md` in `Reese-max/autodev-ng` (blob `8d4088a3`); umbrella #68 created | NOT CLEAN | New P2 #69; #58/#61 remain |
| 4 | 2026-09-21 | Central report `round-5-progress-2026-09-21-0848Z-fixed50-police-exam-archive-r4.md` in `Reese-max/autodev-ng` (blob `bad14769`); repo-local report write rejected by protected `master` (HTTP 409, recorded as `REPORT_WRITE_BLOCKED`) | NOT CLEAN | Existing P2 #74 incorporated; new P2 #75; #58/#61/#69 remain |

Only reports merged to the default branch or recorded in the tracker issue
count as current-product evidence; open PR-head content does not.

## Linked independent actionable findings

Each finding stays in its own issue; this tracker does not combine unrelated
root causes.

| Issue | Severity | Summary | Remediation PRs (open, unmerged — not current-product evidence) |
|---|---|---|---|
| #58 | P2 | The 4 image-based answer choices are not preserved/rendered in the structured experience | #59, #65, #71 |
| #61 | P2 | Public dataset quality denominators (36,210) drift from the current 36,760-question corpus | #64, #72, #86 |
| #69 | P2 | An in-progress mock exam is lost on reload/interruption; no resumable checkpoint | #73, #83 |
| #74 | P2 | Analytics `analytics-chart.js` / `analytics-chart-data.js` can mix versions from independent cache fallbacks | #77, #78, #85 |
| #75 | P2 | First offline Analytics visit lacks the precached Chart.js runtime dependency | #76, #79, #84 |

Related non-blocking item: #70 is an open VALIDATION_GAP for revalidating
diverged PR #50 against protected `master`; it is tracked separately and is
not promoted into a current-product finding.

## CLEAN gate

The repository may enter CLEAN counting only after all P0/P1/P2 findings are
resolved or explicitly dispositioned on the default branch, required
user-facing runtime evidence exists, and the same fixed 50 personas produce
no new P0/P1/P2 findings for **two consecutive** current rounds. Issue
closure, PR merge, or source diff alone does not mark a finding
`VERIFIED_FIXED`; the relevant path must be rerun on default.

## Evidence boundary

Exact-SHA CI run `33989440607` and Pages run `33989440679` on `a0b5dbb9`
prove only the executed workflow steps. They do not prove browser reload
recovery (#69), image-choice rendering (#58), mixed-cache or first-offline
Analytics behavior (#74/#75), or assistive-technology paths.