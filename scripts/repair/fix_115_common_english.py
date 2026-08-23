#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""依考選部 115 年共同英文原卷修復第 41–60 題。

官方來源：
https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=Q&code=115060&c=201&s=0205&q=1

此卷由 11 個三等警察類科共用。本工具只修改可由官方 PDF 逐字確認的
題幹、選項、答案及閱讀文章，並支援唯讀 ``--check`` 模式供 CI 使用。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "考古題庫"
SUBJECT = "中華民國憲法與警察專業英文"

CATEGORIES = [
    "行政警察學系",
    "外事警察學系",
    "刑事警察學系",
    "公共安全學系社安組",
    "犯罪防治學系預防組",
    "交通學系交通組",
    "資訊管理學系",
    "鑑識科學學系",
    "國境警察學系境管組",
    "法律學系",
    "行政管理學系",
]

PASSAGE_51_55 = (
    "Two Jewish men were stabbed in north London two days ago by an attacker who ran down a "
    "street [[51]] Jews in what police said was a suspected terrorist incident. Police said the "
    "two victims, aged 76 and 34, were both in a stable condition in hospital, and counter-terror "
    "officers, some of whom the suspect also attacked, had arrested a 45-year-old man after "
    "stopped him with a Taser [[52]] gun. The suspect is a British national, born in Somalia, the "
    "Metropolitan Police said in a statement. On being arrested, he was initially taken to a "
    "hospital. After examination and treatment, he was soon [[53]] and taken to London police "
    "station where he remains in custody on [[54]] of attempted murder. This stabbing incident "
    "is the latest one in a [[55]] of UK antisemitic attacks. The consecutive attacks have drawn "
    "demands for urgent action from Jewish community leaders in London. Israeli Prime Minister "
    "Benjamin Netanyahu and the Israeli president also expressed concerns over the safety of "
    "Britain’s 290,000 Jews."
)

PASSAGE_56_60 = (
    "As digital deception becomes more indistinguishable from reality, law enforcement agencies "
    "are shifting their public education strategies toward a “Zero Trust” framework. Historically, "
    "crime prevention advice focused on identifying “red flags,” such as poor grammar in an email "
    "or a strange accent on the phone. However, with the advent of AI-driven scams, these "
    "traditional markers have vanished. The “Zero Trust” protocol operates on a simple but strict "
    "principle: never trust, always verify.\n\n"
    "In a “Zero Trust” environment, the public is taught to treat every digital interaction as "
    "potentially compromised, regardless of the apparent source. For example, if a citizen receives "
    "a video call from their “bank manager” or a voice note from a “family member” requesting urgent "
    "financial assistance, the protocol dictates that they must immediately terminate the "
    "connection. Verification is then conducted through an independent, “out-of-band” channel—such "
    "as calling a trusted, officially listed phone number or visiting a physical branch.\n\n"
    "For police officers, promoting this mindset requires a delicate balance. The goal is not to "
    "create a society of paranoia, but to foster “digital skepticism.” Officers are now being trained "
    "to conduct community workshops that demonstrate how easily a “digital identity” can be faked. "
    "They emphasize that in the modern era, “seeing is no longer believing.” By teaching the public "
    "to pause and verify, police can significantly reduce the success rate of high-tech fraud without "
    "needing to trace every individual packet of data across international borders.\n\n"
    "Ultimately, the “Zero Trust” model represents a shift in responsibility. While the police "
    "continue to pursue the technical “attribution” of cybercrimes, the first line of defense has "
    "moved to the individual’s decision-making process. By adopting a “verify-first” culture, "
    "communities can create a hostile environment for scammers, making it much harder for "
    "AI-generated deceptions to result in successful thefts."
)


def choice(
    number: int,
    stem: str,
    options: dict[str, str],
    answer: str,
    passage: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "number": number,
        "type": "choice",
        "stem": stem,
        "section": "乙、測驗題",
        "options": options,
        "answer": answer,
    }
    if passage:
        item["passage"] = passage
    return item


OFFICIAL: dict[int, dict[str, Any]] = {
    41: choice(
        41,
        "The officers carefully searched the area for any ____ that could help identify the suspect involved in the robbery.",
        {"A": "equipment", "B": "audience", "C": "evidence", "D": "application"},
        "C",
    ),
    42: choice(
        42,
        "Many road accidents happen because drivers are ____ by their mobile phones and fail to see the red light.",
        {"A": "distracted", "B": "delivered", "C": "displayed", "D": "defeated"},
        "A",
    ),
    43: choice(
        43,
        "During the large public festival, additional police officers were hired to provide better ____ and ensured that everyone remained safe.",
        {"A": "authority", "B": "quality", "C": "evaluation", "D": "security"},
        "D",
    ),
    44: choice(
        44,
        "When officers are driving through the neighborhood, it is important to ____ any suspicious behavior and report it to the station immediately.",
        {"A": "utilize", "B": "observe", "C": "affect", "D": "involve"},
        "B",
    ),
    45: choice(
        45,
        "According to the Domestic Violence Prevention Act, medical professionals are ____ reporters with a legal obligation to report suspected cases. Whenever they treat a patient with injuries related to domestic violence, they are duty-bound to notify the local competent authority.",
        {"A": "mandatory", "B": "reliable", "C": "courageous", "D": "secret"},
        "A",
    ),
    46: choice(
        46,
        "The main responsibility of a traffic officer is to ____ road safety laws, such as speed limits, to prevent accidents.",
        {"A": "enforce", "B": "endure", "C": "encourage", "D": "enlarge"},
        "A",
    ),
    47: choice(
        47,
        "Despite the absence of a signed treaty, Taiwanese law enforcement agencies still strived to obtain bank records from Singapore for the corruption case via mutual legal ____ channels.",
        {"A": "action", "B": "assistance", "C": "obligation", "D": "advice"},
        "B",
    ),
    48: choice(
        48,
        "In an effort to solve this criminal case as quickly as possible, the investigative team has set up a ____ for members of the public to call in and provide reports.",
        {"A": "hotline", "B": "committee", "C": "security camera", "D": "service desk"},
        "A",
    ),
    49: choice(
        49,
        "The police will set up DUI checkpoints on several main streets every holiday weekend. Once the officer smells alcohol inside the car, the driver will be requested to perform the field ____ test by the roadside.",
        {"A": "blood", "B": "sobriety", "C": "road", "D": "eye"},
        "B",
    ),
    50: choice(
        50,
        "The department decided to increase patrols in the city center to ____ potential criminals from committing robberies during the holiday season.",
        {"A": "detach", "B": "declare", "C": "define", "D": "deter"},
        "D",
    ),
    51: choice(51, "請依上文選出第 51 題空格最適當的答案。", {"A": "targeting", "B": "haunting", "C": "ignoring", "D": "staring"}, "A", PASSAGE_51_55),
    52: choice(52, "請依上文選出第 52 題空格最適當的答案。", {"A": "machine", "B": "shot", "C": "stun", "D": "flare"}, "C", PASSAGE_51_55),
    53: choice(53, "請依上文選出第 53 題空格最適當的答案。", {"A": "dismissed", "B": "released", "C": "prosecuted", "D": "discharged"}, "D", PASSAGE_51_55),
    54: choice(54, "請依上文選出第 54 題空格最適當的答案。", {"A": "guess", "B": "suspicion", "C": "fear", "D": "doubt"}, "B", PASSAGE_51_55),
    55: choice(55, "請依上文選出第 55 題空格最適當的答案。", {"A": "spate", "B": "piece", "C": "kind", "D": "bit"}, "A", PASSAGE_51_55),
    56: choice(
        56,
        "What is the main purpose of this reading passage?",
        {
            "A": "To criticize police departments for failing to catch international criminals.",
            "B": "To provide a technical guide on how to create deepfake videos for workshops.",
            "C": "To argue that AI technology like Deep Fake should be banned to prevent financial fraud.",
            "D": "To explain a new safety mindset that helps the public defend against modern scams.",
        },
        "D",
        PASSAGE_56_60,
    ),
    57: choice(
        57,
        "How does the “Zero Trust” protocol differ from older crime prevention methods?",
        {
            "A": "It relies on the police to verify every message for the citizens.",
            "B": "It focuses on “never trusting” rather than just looking for “red flags.”",
            "C": "It teaches people to ignore all emails and phone calls entirely.",
            "D": "It encourages people to trust their instincts more than technology.",
        },
        "B",
        PASSAGE_56_60,
    ),
    58: choice(
        58,
        "What is an example of an “out-of-band” verification mentioned in the text?",
        {
            "A": "Calling an independent, official phone number to verify.",
            "B": "Asking the caller to send a photo of their ID card.",
            "C": "Replying immediately to the suspicious video call to ask questions.",
            "D": "Sending a follow-up email to the same address that contacted you.",
        },
        "A",
        PASSAGE_56_60,
    ),
    59: choice(
        59,
        "What is the meaning of the phrase “seeing is no longer believing” in this context?",
        {
            "A": "People are losing their eyesight due to high-tech screen usage.",
            "B": "Officers should not collect video evidence because it is useless.",
            "C": "Digital images and videos can be faked so easily that they cannot be trusted.",
            "D": "Most crimes now happen in the dark where officers cannot see anything.",
        },
        "C",
        PASSAGE_56_60,
    ),
    60: choice(
        60,
        "Why is the “Zero Trust” model considered a “shift in responsibility”?",
        {
            "A": "Because the individual’s decision-making has become the first line of defense.",
            "B": "Because the police are not responsible for catching criminals any longer.",
            "C": "Because scammers are now responsible for proving they are real.",
            "D": "Because the public must now pay for their own digital protection.",
        },
        "A",
        PASSAGE_56_60,
    ),
}


def normalized_projection(question: dict[str, Any]) -> dict[str, Any]:
    return {
        key: question.get(key)
        for key in ("number", "type", "stem", "section", "options", "answer", "passage")
        if key in question
    }


def repair_file(path: Path, *, check: bool) -> bool:
    payload = json.loads(path.read_text(encoding="utf-8"))
    questions = payload.get("questions")
    if not isinstance(questions, list):
        raise RuntimeError(f"questions 非陣列：{path}")

    by_number = {
        question.get("number"): index
        for index, question in enumerate(questions)
        if isinstance(question, dict) and isinstance(question.get("number"), int)
    }
    missing = sorted(set(OFFICIAL) - set(by_number))
    if missing:
        raise RuntimeError(f"缺少官方題號 {missing}：{path}")

    changed = False
    for number, expected in OFFICIAL.items():
        index = by_number[number]
        current = questions[index]
        if normalized_projection(current) != expected:
            changed = True
            if not check:
                questions[index] = dict(expected)

    if changed and not check:
        payload["questions"] = questions
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return changed


def run(*, check: bool) -> int:
    paths = [DATA_DIR / category / "115年" / SUBJECT / "試題.json" for category in CATEGORIES]
    missing_paths = [path for path in paths if not path.is_file()]
    if missing_paths:
        raise RuntimeError("缺少共同英文 JSON：\n- " + "\n- ".join(map(str, missing_paths)))

    changed = [path for path in paths if repair_file(path, check=check)]
    if check and changed:
        print("下列共同英文資料尚未符合官方原卷：")
        for path in changed:
            print(f"- {path.relative_to(ROOT)}")
        return 1

    action = "需要修復" if check else "已修復"
    print(f"{action}：{len(changed)} / {len(paths)} 份共同英文 JSON")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只驗證，不修改檔案")
    args = parser.parse_args()
    try:
        return run(check=args.check)
    except Exception as exc:
        print(f"錯誤：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
