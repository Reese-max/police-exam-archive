# 50-Persona Audit Tracker — Fixed A01–J05

Umbrella tracker: GitHub issue [#68](https://github.com/Reese-max/police-exam-archive/issues/68)
Protocol: [`Reese-max/autodev-ng/docs/portfolio-audit/2026-09-06-50-persona-audit.md`](https://github.com/Reese-max/autodev-ng/blob/11b8be2b84d20c2234142f0542b5f05d31891abc/docs/portfolio-audit/2026-09-06-50-persona-audit.md)

> The 50 personas are fixed synthetic simulations (A01–J05), not real-user
> research. This file is the repo-local tracking record only: it records
> round status and links independent actionable findings. It does **not**
> implement any finding and grants no worker, merge, or deploy authority
> (`auto_implementation: false`).

## Audit baseline (historical snapshot)

Snapshot date: `2026-09-30` (original tracker capture).
Issue/PR states below describe that snapshot. Recheck the latest `master`
and relevant runtime paths before making a current-product decision.

- Default branch: `master`
- Inspected product SHA: `a0b5dbb9352b5558dbe62445c6452947dbd2501b`
  (audit-only head `docs: add 50-persona audit round 1`; product baseline
  remains its parent `fe497aa9fac7a4e4a411e663edeef6c1c5356577`)
- Status at inspected SHA: **NOT CLEAN — CLEAN streak 0/2**

## Round status

| Round | Date | Record | Result | Findings |
|---|---|---|---|---|
| 1 | 2026-09-06 | [`docs/audits/50-persona-round-1-2026-09-06.md`](50-persona-round-1-2026-09-06.md) | NOT CLEAN | P2 #58 carried open |
| 2 | 2026-09-10 / 2026-09-13 | Candidate reports exist only in open, unmerged PRs [#63](https://github.com/Reese-max/police-exam-archive/pull/63) and [#67](https://github.com/Reese-max/police-exam-archive/pull/67) | NOT CLEAN | P2 #61 formally added to the CLEAN gate; #58 remains |
| 3 | 2026-09-16 | Central report [`round-5-progress-2026-09-16-0825Z-fixed50-police-exam-archive-r3.md`](https://github.com/Reese-max/autodev-ng/blob/8d4088a3ff9ff4e42e69ddf762379a524e10aff2/docs/portfolio-audit/round-5-progress-2026-09-16-0825Z-fixed50-police-exam-archive-r3.md); umbrella #68 created | NOT CLEAN | New P2 #69; #58/#61 remain |
| 4 | 2026-09-21 | Central report [`round-5-progress-2026-09-21-0848Z-fixed50-police-exam-archive-r4.md`](https://github.com/Reese-max/autodev-ng/blob/bad147694c72fc98baf233634f13600607e6dcd4/docs/portfolio-audit/round-5-progress-2026-09-21-0848Z-fixed50-police-exam-archive-r4.md); repo-local report write rejected by protected `master` (HTTP 409, recorded as `REPORT_WRITE_BLOCKED`) | NOT CLEAN | Existing P2 #74 incorporated; new P2 #75; #58/#61/#69 remain |

Each round's evidence must identify its inspected default-branch SHA and
be merged to the default branch or recorded in the tracker issue. Open
PR-head content remains candidate evidence.

## Linked independent actionable findings

Each finding stays in its own issue; this tracker does not combine unrelated
root causes.

| Issue | Severity | Summary | Remediation PRs (open, unmerged at snapshot — not current-product evidence) |
|---|---|---|---|
| [#58](https://github.com/Reese-max/police-exam-archive/issues/58) | P2 | The 4 image-based answer choices are not preserved/rendered in the structured experience | [#59](https://github.com/Reese-max/police-exam-archive/pull/59), [#65](https://github.com/Reese-max/police-exam-archive/pull/65), [#71](https://github.com/Reese-max/police-exam-archive/pull/71) |
| [#61](https://github.com/Reese-max/police-exam-archive/issues/61) | P2 | Public dataset quality denominators (36,210) drift from the current 36,760-question corpus | [#64](https://github.com/Reese-max/police-exam-archive/pull/64), [#72](https://github.com/Reese-max/police-exam-archive/pull/72), [#86](https://github.com/Reese-max/police-exam-archive/pull/86) |
| [#69](https://github.com/Reese-max/police-exam-archive/issues/69) | P2 | An in-progress mock exam is lost on reload/interruption; no resumable checkpoint | [#73](https://github.com/Reese-max/police-exam-archive/pull/73), [#83](https://github.com/Reese-max/police-exam-archive/pull/83) |
| [#74](https://github.com/Reese-max/police-exam-archive/issues/74) | P2 | Analytics `analytics-chart.js` / `analytics-chart-data.js` can mix versions from independent cache fallbacks | [#77](https://github.com/Reese-max/police-exam-archive/pull/77), [#78](https://github.com/Reese-max/police-exam-archive/pull/78), [#85](https://github.com/Reese-max/police-exam-archive/pull/85) |
| [#75](https://github.com/Reese-max/police-exam-archive/issues/75) | P2 | First offline Analytics visit lacks the precached Chart.js runtime dependency | [#76](https://github.com/Reese-max/police-exam-archive/pull/76), [#79](https://github.com/Reese-max/police-exam-archive/pull/79), [#84](https://github.com/Reese-max/police-exam-archive/pull/84) |

Related P2 validation item: [#70](https://github.com/Reese-max/police-exam-archive/issues/70)
was an open VALIDATION_GAP at the snapshot for revalidating diverged PR
[#50](https://github.com/Reese-max/police-exam-archive/pull/50) against protected
`master`. It stays separate from current-product defects and remains subject
to the P0/P1/P2 CLEAN gate.

## CLEAN gate

The repository may be marked CLEAN only after all P0/P1/P2 issues are closed
or have an explicit `not_planned` rationale, required user-facing runtime
evidence exists, and the same fixed 50 personas are rerun against the latest
default-branch SHA with no new P0/P1/P2 findings for **two consecutive** rounds.
Issue closure, PR merge, or source diff alone does not mark a finding
`VERIFIED_FIXED`; the relevant path must be rerun on default.

## Evidence boundary

Exact-SHA [CI run `33989440607`](https://github.com/Reese-max/police-exam-archive/actions/runs/33989440607)
and [Pages run `33989440679`](https://github.com/Reese-max/police-exam-archive/actions/runs/33989440679) on `a0b5dbb9`
prove only the executed workflow steps. They do not prove browser reload
recovery (#69), image-choice rendering (#58), mixed-cache or first-offline
Analytics behavior (#74/#75), or assistive-technology paths.
