# -*- coding: utf-8 -*-
"""
解析結果品質評估。

每份 parse_result 經過 8 項檢查 → quality_score (0.0~1.0) + issues list。
低於 threshold 的視為 suspicious，會觸發 retry。

設計目標：把過去 archive/fixes/ 那些事後修復的判定邏輯前置到解析時，
讓壞資料不要默默寫進 JSON。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


# 各檢查的罰分（總分 1.0）
_PENALTY_EMPTY_STEM = 0.20
_PENALTY_MISSING_OPTIONS = 0.20
_PENALTY_DISCONTINUOUS_NUMBERS = 0.10
_PENALTY_TOO_FEW_QUESTIONS = 0.15
_PENALTY_METADATA_IN_STEM = 0.10
_PENALTY_MERGED_QUESTION = 0.10
_PENALTY_TRUNCATED_STEM = 0.05
_PENALTY_NO_METADATA = 0.10


# 題幹含這些字串視為「metadata 滲入」
_METADATA_LEAK_KEYWORDS = (
    "代號：", "代號:",
    "等　別：", "等別：",
    "科　目：", "科目：",
    "座號：", "頁次：",
    "考試別：",
    "請接背面", "背面尚有",
)

# 合併題判定：stem 字元數 + 含 2+ 個分數標記
_MERGED_STEM_LEN = 800
_SCORE_MARKER_RE = re.compile(r"[(（]\s*\d+\s*分\s*[)）]")

# 題幹被截斷的尾部字元（中文）
_TRUNCATED_TAILS = ("，", "、", "的", "是", "之", "與", "及")

# 題數低於此值視為異常少（純申論卷 3-4 題很常見，不該扣分）
_MIN_REASONABLE_QUESTIONS = 3


@dataclass
class QualityReport:
    score: float = 1.0
    issues: List[str] = field(default_factory=list)
    total_questions: int = 0
    choice_questions: int = 0
    essay_questions: int = 0
    empty_stems: int = 0
    missing_options: int = 0
    metadata_leaks: int = 0
    merged_questions: int = 0
    truncated_stems: int = 0
    discontinuous: bool = False
    has_metadata: bool = True

    def is_good(self, threshold: float = 0.7) -> bool:
        return self.score >= threshold

    def summary(self) -> str:
        return (
            f"score={self.score:.2f} "
            f"Q={self.total_questions}(c={self.choice_questions}/e={self.essay_questions}) "
            f"issues={len(self.issues)}"
        )


def _is_choice(q: dict) -> bool:
    return q.get("type") == "choice"


def _is_essay(q: dict) -> bool:
    return q.get("type") == "essay"


def _has_metadata_leak(stem: str) -> bool:
    return any(kw in stem for kw in _METADATA_LEAK_KEYWORDS)


def _is_truncated(stem: str) -> bool:
    s = stem.rstrip()
    if not s:
        return False
    last_char = s[-1]
    # 句末應該是 。 ？ ! ） ） . ?
    if last_char in "。？！?!.…":
        return False
    if last_char in ")）]":
        return False
    return last_char in _TRUNCATED_TAILS


def _check_number_continuity(choices: List[dict]) -> bool:
    """選擇題題號是否連續（1, 2, 3, ...）。允許從非 1 起始（少數考卷）。"""
    nums = [q.get("number") for q in choices if isinstance(q.get("number"), int)]
    if len(nums) < 2:
        return False
    nums_sorted = sorted(nums)
    expected = list(range(nums_sorted[0], nums_sorted[0] + len(nums_sorted)))
    return nums_sorted != expected


def assess_quality(result: dict, threshold: float = 0.7) -> QualityReport:
    """評估解析結果品質。

    Args:
        result: parse_questions 的回傳 dict
        threshold: 視為 suspicious 的最低分數（給 is_good 用，本函數不主動套用）
    """
    report = QualityReport()
    qs = result.get("questions") or []

    if not qs:
        report.score = 0.0
        report.issues.append("no_questions_extracted")
        return report

    choices = [q for q in qs if _is_choice(q)]
    essays = [q for q in qs if _is_essay(q)]

    report.total_questions = len(qs)
    report.choice_questions = len(choices)
    report.essay_questions = len(essays)

    score = 1.0

    # 1. 空題幹比例（純空白也算空）
    empty = sum(1 for q in qs if not (q.get("stem") or "").strip())
    report.empty_stems = empty
    if empty > 0:
        ratio = empty / len(qs)
        if ratio > 0.05:  # 5% 以上才扣
            score -= _PENALTY_EMPTY_STEM * min(1.0, ratio * 5)
            report.issues.append(f"empty_stems={empty}/{len(qs)}")

    # 2. 選擇題缺選項比例
    if choices:
        missing = sum(
            1
            for q in choices
            if set((q.get("options") or {}).keys()) < {"A", "B", "C", "D"}
        )
        report.missing_options = missing
        ratio = missing / len(choices)
        if ratio > 0.10:
            score -= _PENALTY_MISSING_OPTIONS * min(1.0, ratio * 3)
            report.issues.append(f"missing_options={missing}/{len(choices)}")

    # 3. 題號不連續
    if _check_number_continuity(choices):
        report.discontinuous = True
        score -= _PENALTY_DISCONTINUOUS_NUMBERS
        report.issues.append("discontinuous_numbers")

    # 4. 題數異常少
    if len(qs) < _MIN_REASONABLE_QUESTIONS:
        score -= _PENALTY_TOO_FEW_QUESTIONS
        report.issues.append(f"too_few_questions={len(qs)}")

    # 5. metadata 滲入題幹
    leaks = sum(1 for q in qs if _has_metadata_leak(q.get("stem") or ""))
    report.metadata_leaks = leaks
    if leaks > 0:
        score -= _PENALTY_METADATA_IN_STEM * min(1.0, leaks / len(qs) * 5)
        report.issues.append(f"metadata_leaks={leaks}")

    # 6. 合併題：stem 超長 且 含 2+ 個分數標記才算（避免長表格 essay 誤判）
    merged = sum(
        1
        for q in qs
        if len(q.get("stem") or "") > _MERGED_STEM_LEN
        and len(_SCORE_MARKER_RE.findall(q.get("stem") or "")) >= 2
    )
    report.merged_questions = merged
    if merged > 0:
        score -= _PENALTY_MERGED_QUESTION
        report.issues.append(f"merged_questions={merged}")

    # 7. 截斷題幹
    truncated = sum(1 for q in qs if _is_truncated(q.get("stem") or ""))
    report.truncated_stems = truncated
    if truncated > 0:
        score -= _PENALTY_TRUNCATED_STEM * min(1.0, truncated / len(qs) * 10)
        report.issues.append(f"truncated_stems={truncated}")

    # 8. 完全沒抽到 metadata
    if not result.get("metadata"):
        report.has_metadata = False
        score -= _PENALTY_NO_METADATA
        report.issues.append("no_metadata")

    report.score = max(0.0, score)
    return report
