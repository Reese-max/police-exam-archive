#!/usr/bin/env python3
"""One-time patch: allow build_analytics.py to aggregate list answers.

The 115 MOEX correction sheet contains questions with multiple accepted answers,
represented in the repository as JSON arrays. The existing analytics builder used
those values directly as Counter keys and crashed because lists are unhashable.
"""

from pathlib import Path

PATH = Path(__file__).with_name("build_analytics.py")

OLD = '''    for q in questions:
        if q["type"] == "choice" and q["ans"]:
            answer_dist[q["ans"]] += 1
            if q["yr"]:
                answer_by_year[str(q["yr"])][q["ans"]] += 1
'''

NEW = '''    for q in questions:
        if q["type"] != "choice" or not q["ans"]:
            continue

        answer = q["ans"]
        if isinstance(answer, list):
            # Preserve all accepted options as one stable analytics bucket,
            # consistent with the repository's existing ``A或C`` convention.
            values = [
                str(value).strip()
                for value in answer
                if str(value).strip()
            ]
            answer = "或".join(dict.fromkeys(values))
        elif not isinstance(answer, str):
            answer = str(answer).strip()

        if not answer:
            continue
        answer_dist[answer] += 1
        if q["yr"]:
            answer_by_year[str(q["yr"])][answer] += 1
'''


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    if NEW in text:
        print("build_analytics.py is already compatible with list answers")
        return
    if text.count(OLD) != 1:
        raise SystemExit("Expected analytics answer-distribution block was not found exactly once")
    PATH.write_text(text.replace(OLD, NEW), encoding="utf-8")
    print("Patched build_analytics.py for multi-answer arrays")


if __name__ == "__main__":
    main()
