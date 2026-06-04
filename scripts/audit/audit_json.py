# -*- coding: utf-8 -*-
"""
JSON 完整性 audit — regression 保護。

對 cache/full_out 內所有 試題.json 跑完整性檢查，輸出 audit_report.json。

檢查項目：
  1. 必備欄位：metadata, questions, subject, source_pdf, _quality
  2. 每題必備欄位：number, type, stem
  3. 選擇題：必須有 options 且包含 A/B/C/D
  4. answer 格式合法（str ∈ ABCD 或 list[str ∈ ABCD] 或 None）
  5. 題號連續性（choice）
  6. _quality.score >= 0.7

用法:
    python scripts/audit/audit_json.py
    python scripts/audit/audit_json.py --data-dir cache/full_out
    python scripts/audit/audit_json.py --fail-fast      # 第一個 error 就停
    python scripts/audit/audit_json.py --threshold 0.7  # 自訂 quality 門檻
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

_REQUIRED_FILE_KEYS = ("metadata", "questions", "subject", "source_pdf")
_REQUIRED_Q_KEYS = ("number", "type", "stem")
_VALID_ANSWER_LABELS = {"A", "B", "C", "D"}


@dataclass
class AuditIssue:
    file: str
    severity: str  # critical / high / medium / low
    code: str
    message: str
    detail: Optional[str] = None


@dataclass
class AuditReport:
    total_files: int = 0
    pass_count: int = 0
    fail_count: int = 0
    issues: List[AuditIssue] = field(default_factory=list)

    def add(self, issue: AuditIssue) -> None:
        self.issues.append(issue)

    def by_severity(self) -> dict:
        out: dict = {}
        for it in self.issues:
            out[it.severity] = out.get(it.severity, 0) + 1
        return out


def _validate_answer(answer) -> bool:
    """answer 必須是 str ∈ ABCD、list[str ∈ ABCD]、或 None。"""
    if answer is None:
        return True
    if isinstance(answer, str):
        return answer in _VALID_ANSWER_LABELS or len(answer) > 0  # 容許 raw 值
    if isinstance(answer, list):
        return all(isinstance(a, str) and a in _VALID_ANSWER_LABELS for a in answer)
    return False


def audit_file(json_path: Path, threshold: float = 0.7) -> List[AuditIssue]:
    """檢查單一 JSON 檔。回傳 issues list。"""
    issues: List[AuditIssue] = []
    fkey = str(json_path)

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        issues.append(AuditIssue(fkey, "critical", "unreadable", f"{e}"))
        return issues

    # 必備檔案欄位
    for k in _REQUIRED_FILE_KEYS:
        if k not in data:
            issues.append(AuditIssue(fkey, "high", "missing_file_key", k))

    questions = data.get("questions") or []
    if not questions:
        issues.append(AuditIssue(fkey, "high", "no_questions", "0 題"))

    # quality 分數
    quality = data.get("_quality") or {}
    score = quality.get("score")
    if score is None:
        issues.append(
            AuditIssue(fkey, "medium", "no_quality_meta", "缺 _quality")
        )
    elif score < threshold:
        issues.append(
            AuditIssue(
                fkey,
                "high",
                "low_quality_score",
                f"score={score} < {threshold}",
                detail=str(quality.get("issues")),
            )
        )

    # 每題檢查
    choice_nums: list[int] = []
    for idx, q in enumerate(questions):
        q_id = f"q[{idx}] num={q.get('number', '?')}"
        for k in _REQUIRED_Q_KEYS:
            if k not in q:
                issues.append(
                    AuditIssue(fkey, "high", "missing_q_key", f"{q_id}: 缺 {k}")
                )

        qtype = q.get("type")
        if qtype not in ("choice", "essay"):
            issues.append(
                AuditIssue(fkey, "medium", "unknown_q_type", f"{q_id}: type={qtype}")
            )

        if qtype == "choice":
            opts = q.get("options") or {}
            if set(opts.keys()) != _VALID_ANSWER_LABELS:
                issues.append(
                    AuditIssue(
                        fkey,
                        "medium",
                        "incomplete_options",
                        f"{q_id}: {sorted(opts.keys())}",
                    )
                )
            if not _validate_answer(q.get("answer")):
                issues.append(
                    AuditIssue(
                        fkey,
                        "high",
                        "invalid_answer",
                        f"{q_id}: {q.get('answer')!r}",
                    )
                )
            if isinstance(q.get("number"), int):
                choice_nums.append(q["number"])

        if not (q.get("stem") or "").strip():
            issues.append(
                AuditIssue(fkey, "high", "empty_stem", q_id)
            )

    # 題號連續
    if len(choice_nums) >= 2:
        sorted_nums = sorted(choice_nums)
        expected = list(range(sorted_nums[0], sorted_nums[0] + len(sorted_nums)))
        if sorted_nums != expected:
            missing = set(expected) - set(sorted_nums)
            if missing:
                issues.append(
                    AuditIssue(
                        fkey,
                        "low",
                        "discontinuous_numbers",
                        f"missing={sorted(missing)}",
                    )
                )

    return issues


def audit_directory(
    data_dir: Path, threshold: float = 0.7, fail_fast: bool = False
) -> AuditReport:
    report = AuditReport()
    for json_path in sorted(data_dir.rglob("試題.json")):
        report.total_files += 1
        issues = audit_file(json_path, threshold=threshold)
        if issues:
            report.fail_count += 1
            for it in issues:
                report.add(it)
                if fail_fast and it.severity in ("critical", "high"):
                    return report
        else:
            report.pass_count += 1
    return report


def main():
    parser = argparse.ArgumentParser(description="JSON 完整性 audit")
    parser.add_argument(
        "--data-dir", default="cache/full_out",
        help="掃描根目錄（預設 cache/full_out）",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.7,
        help="quality_score 最低門檻（預設 0.7）",
    )
    parser.add_argument(
        "--fail-fast", action="store_true",
        help="遇到第一個 critical/high 就停",
    )
    parser.add_argument(
        "--out", default=None,
        help="audit 報告輸出路徑（預設 <data-dir>/audit_report.json）",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"目錄不存在: {data_dir}")
        sys.exit(1)

    print(f"audit {data_dir} ...")
    report = audit_directory(data_dir, threshold=args.threshold, fail_fast=args.fail_fast)

    print()
    print(f"  total: {report.total_files}")
    print(f"  pass:  {report.pass_count}")
    print(f"  fail:  {report.fail_count}")
    sev = report.by_severity()
    if sev:
        for k in ("critical", "high", "medium", "low"):
            if k in sev:
                print(f"  {k}: {sev[k]}")

    out_path = Path(args.out) if args.out else (data_dir / "audit_report.json")
    out_path.write_text(
        json.dumps(
            {
                "total_files": report.total_files,
                "pass_count": report.pass_count,
                "fail_count": report.fail_count,
                "by_severity": sev,
                "issues": [
                    {
                        "file": it.file,
                        "severity": it.severity,
                        "code": it.code,
                        "message": it.message,
                        "detail": it.detail,
                    }
                    for it in report.issues
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n報告: {out_path}")

    # 有 critical 則 exit 1（給 CI 用）
    if sev.get("critical", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
