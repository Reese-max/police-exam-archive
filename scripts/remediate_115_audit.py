#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修復 115 年警察三等題庫匯入審查發現。

本工具同時提供兩種模式：
- 預設：唯讀檢查。若仍有待套用變更，以非零狀態結束。
- ``--apply``：套用可重現且已驗證的修補。

修補包含：共同英文題組、跨類科共同卷 membership、完整官方科名、
搜尋索引與前端題組支援、複數答案／送分計分、下載 TLS/PDF 驗證、
靜態類科頁建置、獨立唯讀稽核，以及移除一次性自動合併工作流。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "考古題庫"
SITE_DIR = ROOT / "考古題網站"

CHANGES: list[str] = []
APPLY = False

ONE_TIME_WORKFLOWS = [
    ".github/workflows/finalize-115-pipeline.yml",
    ".github/workflows/ingest-115-police.yml",
    ".github/workflows/merge-115-after-ci.yml",
    ".github/workflows/merge-verified-115.yml",
    ".github/workflows/rescue-115-pipeline.yml",
    ".github/workflows/verify-115-and-open-pr.yml",
]
HIDDEN_EXECUTABLES = [
    "scripts/audit/.finalize_115_import.py.gz.b64",
    "scripts/parse/.recover_115_missing_choices.py.gz.b64",
]

COMMON_ENGLISH_SUBJECT = "中華民國憲法與警察專業英文"

CLOZE_PASSAGE = (
    "Two Jewish men were stabbed in north London two days ago by an attacker who "
    "ran down a street [[51]] Jews in what police said was a suspected terrorist "
    "incident. Police said the two victims, aged 76 and 34, were both in a stable "
    "condition in hospital, and counter-terror officers, some of whom the suspect "
    "also attacked, had arrested a 45-year-old man after stopped him with a Taser "
    "[[52]] gun. The suspect is a British national, born in Somalia, the Metropolitan "
    "Police said in a statement. On being arrested, he was initially taken to a "
    "hospital. After examination and treatment, he was soon [[53]] and taken to "
    "London police station where he remains in custody on [[54]] of attempted murder. "
    "This stabbing incident is the latest one in a [[55]] of UK antisemitic attacks. "
    "The consecutive attacks have drawn demands for urgent action from Jewish "
    "community leaders in London. Israeli Prime Minister Benjamin Netanyahu and the "
    "Israeli president also expressed concerns over the safety of Britain's 290,000 Jews."
)

ZERO_TRUST_PASSAGE = (
    "As digital deception becomes more indistinguishable from reality, law enforcement "
    "agencies are shifting their public education strategies toward a “Zero Trust” "
    "framework. Historically, crime prevention advice focused on identifying “red "
    "flags,” such as poor grammar in an email or a strange accent on the phone. However, "
    "with the advent of AI-driven scams, these traditional markers have vanished. The "
    "“Zero Trust” protocol operates on a simple but strict principle: never trust, "
    "always verify. In a “Zero Trust” environment, the public is taught to treat every "
    "digital interaction as potentially compromised, regardless of the apparent source. "
    "For example, if a citizen receives a video call from their “bank manager” or a "
    "voice note from a “family member” requesting urgent financial assistance, the "
    "protocol dictates that they must immediately terminate the connection. Verification "
    "is then conducted through an independent, “out-of-band” channel—such as calling a "
    "trusted, officially listed phone number or visiting a physical branch. For police "
    "officers, promoting this mindset requires a delicate balance. The goal is not to "
    "create a society of paranoia, but to foster “digital skepticism.” Officers are now "
    "being trained to conduct community workshops that demonstrate how easily a “digital "
    "identity” can be faked. They emphasize that in the modern era, “seeing is no longer "
    "believing.” By teaching the public to pause and verify, police can significantly "
    "reduce the success rate of high-tech fraud without needing to trace every individual "
    "packet of data across international borders. Ultimately, the “Zero Trust” model "
    "represents a shift in responsibility. While the police continue to pursue the "
    "technical “attribution” of cybercrimes, the first line of defense has moved to the "
    "individual’s decision-making process. By adopting a “verify-first” culture, "
    "communities can create a hostile environment for scammers, making it much harder "
    "for AI-generated deceptions to result in successful thefts."
)

COMMON_ENGLISH: dict[int, dict[str, Any]] = {
    41: {
        "stem": "The officers carefully searched the area for any _____ that could help identify the suspect involved in the robbery.",
        "options": {"A": "equipment", "B": "audience", "C": "evidence", "D": "application"},
        "answer": "C",
    },
    42: {
        "stem": "Many road accidents happen because drivers are _____ by their mobile phones and fail to see the red light.",
        "options": {"A": "distracted", "B": "delivered", "C": "displayed", "D": "defeated"},
        "answer": "A",
    },
    43: {
        "stem": "During the large public festival, additional police officers were hired to provide better _____ and ensured that everyone remained safe.",
        "options": {"A": "authority", "B": "quality", "C": "evaluation", "D": "security"},
        "answer": "D",
    },
    44: {
        "stem": "When officers are driving through the neighborhood, it is important to _____ any suspicious behavior and report it to the station immediately.",
        "options": {"A": "utilize", "B": "observe", "C": "affect", "D": "involve"},
        "answer": "B",
    },
    45: {
        "stem": "According to the Domestic Violence Prevention Act, medical professionals are _____ reporters with a legal obligation to report suspected cases. Whenever they treat a patient with injuries related to domestic violence, they are duty-bound to notify the local competent authority.",
        "options": {"A": "mandatory", "B": "reliable", "C": "courageous", "D": "secret"},
        "answer": "A",
    },
    46: {
        "stem": "The main responsibility of a traffic officer is to _____ road safety laws, such as speed limits, to prevent accidents.",
        "options": {"A": "enforce", "B": "endure", "C": "encourage", "D": "enlarge"},
        "answer": "A",
    },
    47: {
        "stem": "Despite the absence of a signed treaty, Taiwanese law enforcement agencies still strived to obtain bank records from Singapore for the corruption case via mutual legal _____ channels.",
        "options": {"A": "action", "B": "assistance", "C": "obligation", "D": "advice"},
        "answer": "B",
    },
    48: {
        "stem": "In an effort to solve this criminal case as quickly as possible, the investigative team has set up a _____ for members of the public to call in and provide reports.",
        "options": {"A": "hotline", "B": "committee", "C": "security camera", "D": "service desk"},
        "answer": "A",
    },
    49: {
        "stem": "The police will set up DUI checkpoints on several main streets every holiday weekend. Once the officer smells alcohol inside the car, the driver will be requested to perform the field _____ test by the roadside.",
        "options": {"A": "blood", "B": "sobriety", "C": "road", "D": "eye"},
        "answer": "B",
    },
    50: {
        "stem": "The department decided to increase patrols in the city center to _____ potential criminals from committing robberies during the holiday season.",
        "options": {"A": "detach", "B": "declare", "C": "define", "D": "deter"},
        "answer": "D",
    },
    51: {
        "stem": "請依上文選出第 51 題空格最適當的答案。",
        "options": {"A": "targeting", "B": "haunting", "C": "ignoring", "D": "staring"},
        "answer": "A",
        "passage": CLOZE_PASSAGE,
    },
    52: {
        "stem": "請依上文選出第 52 題空格最適當的答案。",
        "options": {"A": "machine", "B": "shot", "C": "stun", "D": "flare"},
        "answer": "C",
        "passage": CLOZE_PASSAGE,
    },
    53: {
        "stem": "請依上文選出第 53 題空格最適當的答案。",
        "options": {"A": "dismissed", "B": "released", "C": "prosecuted", "D": "discharged"},
        "answer": "D",
        "passage": CLOZE_PASSAGE,
    },
    54: {
        "stem": "請依上文選出第 54 題空格最適當的答案。",
        "options": {"A": "guess", "B": "suspicion", "C": "fear", "D": "doubt"},
        "answer": "B",
        "passage": CLOZE_PASSAGE,
    },
    55: {
        "stem": "請依上文選出第 55 題空格最適當的答案。",
        "options": {"A": "spate", "B": "piece", "C": "kind", "D": "bit"},
        "answer": "A",
        "passage": CLOZE_PASSAGE,
    },
    56: {
        "stem": "What is the main purpose of this reading passage?",
        "options": {
            "A": "To criticize police departments for failing to catch international criminals.",
            "B": "To provide a technical guide on how to create deepfake videos for workshops.",
            "C": "To argue that AI technology like Deep Fake should be banned to prevent financial fraud.",
            "D": "To explain a new safety mindset that helps the public defend against modern scams.",
        },
        "answer": "D",
        "passage": ZERO_TRUST_PASSAGE,
    },
    57: {
        "stem": "How does the “Zero Trust” protocol differ from older crime prevention methods?",
        "options": {
            "A": "It relies on the police to verify every message for the citizens.",
            "B": "It focuses on “never trusting” rather than just looking for “red flags.”",
            "C": "It teaches people to ignore all emails and phone calls entirely.",
            "D": "It encourages people to trust their instincts more than technology.",
        },
        "answer": "B",
        "passage": ZERO_TRUST_PASSAGE,
    },
    58: {
        "stem": "What is an example of an “out-of-band” verification mentioned in the text?",
        "options": {
            "A": "Calling an independent, official phone number to verify.",
            "B": "Asking the caller to send a photo of their ID card.",
            "C": "Replying immediately to the suspicious video call to ask questions.",
            "D": "Sending a follow-up email to the same address that contacted you.",
        },
        "answer": "A",
        "passage": ZERO_TRUST_PASSAGE,
    },
    59: {
        "stem": "What is the meaning of the phrase “seeing is no longer believing” in this context?",
        "options": {
            "A": "People are losing their eyesight due to high-tech screen usage.",
            "B": "Officers should not collect video evidence because it is useless.",
            "C": "Digital images and videos can be faked so easily that they cannot be trusted.",
            "D": "Most crimes now happen in the dark where officers cannot see anything.",
        },
        "answer": "C",
        "passage": ZERO_TRUST_PASSAGE,
    },
    60: {
        "stem": "Why is the “Zero Trust” model considered a “shift in responsibility”?",
        "options": {
            "A": "Because the individual’s decision-making has become the first line of defense.",
            "B": "Because the police are not responsible for catching criminals any longer.",
            "C": "Because scammers are now responsible for proving they are real.",
            "D": "Because the public must now pay for their own digital protection.",
        },
        "answer": "A",
        "passage": ZERO_TRUST_PASSAGE,
    },
}

FULL_SUBJECT_NAMES = {
    "消防與災害防救法規(包括消防法及施行細則、災害防救法及施行細則、爆竹煙火管理條例及施行細則、公共危險物品及可燃性高壓氣體製造儲存處理場所設置標準暨安全管理辦法、": (
        "消防與災害防救法規（包括消防法及施行細則、災害防救法及施行細則、爆竹煙火管理條例及施行細則、"
        "公共危險物品及可燃性高壓氣體製造儲存處理場所設置標準暨安全管理辦法、緊急救護辦法、緊急醫療救護法"
        "及施行細則、直轄市縣市消防機關火場指揮及搶救作業要點）"
    ),
    "海巡法規(包括國家安全法、臺灣地區與大陸地區人民關係條例、海岸巡防法、海岸巡防機關器械使用條例、海關緝私條例、中華民國領海及鄰接區法、中華民國專屬經濟海域及大陸礁層法、": (
        "海巡法規（包括國家安全法、臺灣地區與大陸地區人民關係條例、海岸巡防法、海岸巡防機關器械使用條例、"
        "海關緝私條例、中華民國領海及鄰接區法、中華民國專屬經濟海域及大陸礁層法、海洋污染防治法、行政執行法、"
        "公務人員行政中立法）"
    ),
}

CATEGORY_NAMES = [
    "行政警察學系",
    "外事警察學系",
    "刑事警察學系",
    "公共安全學系社安組",
    "犯罪防治學系預防組",
    "消防學系",
    "交通學系交通組",
    "資訊管理學系",
    "鑑識科學學系",
    "國境警察學系境管組",
    "水上警察學系",
    "法律學系",
    "行政管理學系",
]


def note(path: Path, action: str) -> None:
    CHANGES.append(f"{action}: {path.relative_to(ROOT)}")


def write_text(path: Path, content: str) -> None:
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == content:
        return
    note(path, "更新" if path.exists() else "新增")
    if APPLY:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def delete_path(path: Path) -> None:
    if not path.exists():
        return
    note(path, "刪除")
    if APPLY:
        path.unlink()


def replace_required(path: Path, old: str, new: str, *, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text and old not in text:
        return
    if old not in text:
        raise RuntimeError(f"找不到待替換片段（{label}）：{path}")
    write_text(path, text.replace(old, new))


def regex_replace_required(
    path: Path,
    pattern: str,
    replacement: str | Callable[[re.Match[str]], str],
    *,
    label: str,
    flags: int = 0,
) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, flags=flags)
    if count == 0:
        raise RuntimeError(f"找不到待替換正則（{label}）：{path}")
    write_text(path, updated)


def patch_common_english() -> None:
    paths = sorted(DATA_DIR.glob(f"*/115年/{COMMON_ENGLISH_SUBJECT}/試題.json"))
    if not paths:
        raise RuntimeError("找不到 115 年共同英文試題 JSON")

    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        questions = payload.get("questions")
        if not isinstance(questions, list):
            raise RuntimeError(f"questions 非陣列：{path}")
        by_number = {
            q.get("number"): q
            for q in questions
            if isinstance(q, dict) and q.get("type") == "choice"
        }
        missing = sorted(set(COMMON_ENGLISH) - set(by_number))
        if missing:
            raise RuntimeError(f"共同英文缺少題號：{path}：{missing}")

        changed = False
        for number, canonical in COMMON_ENGLISH.items():
            question = by_number[number]
            desired = {
                "stem": canonical["stem"],
                "options": canonical["options"],
                "answer": canonical["answer"],
            }
            if "passage" in canonical:
                desired["passage"] = canonical["passage"]
            for key, value in desired.items():
                if question.get(key) != value:
                    question[key] = value
                    changed = True
            if "passage" not in canonical and "passage" in question:
                question.pop("passage", None)
                changed = True
            if question.pop("_recovered_from_pdf_page", None) is not None:
                changed = True

        metadata = payload.setdefault("metadata", {})
        if metadata.get("official_subject") != COMMON_ENGLISH_SUBJECT:
            metadata["official_subject"] = COMMON_ENGLISH_SUBJECT
            changed = True
        if changed:
            write_json(path, payload)



ENGLISH_TOKEN_RE = re.compile(r"[A-Za-z]{12,}")
EMBEDDED_PASSAGE_RE = re.compile(
    r"\s*請依下文回答第\s*(\d{1,3})\s*題至第\s*(\d{1,3})\s*題\s*(.+)$",
    re.DOTALL,
)


def repair_english_spacing(value: str) -> str:
    """以保守的語言模型分詞修復 PDF 抽取造成的英文黏字。"""
    import wordninja

    common = {
        "a", "an", "and", "as", "at", "before", "by", "for", "from",
        "how", "in", "into", "is", "it", "of", "on", "or", "that", "the",
        "their", "this", "to", "was", "were", "what", "when", "which",
        "who", "why", "with", "without",
    }

    def replace(match: re.Match[str]) -> str:
        original = match.group(0)
        if sum(char.isupper() for char in original) > 1:
            return original
        lower = original.lower()
        parts = wordninja.split(lower)
        if len(parts) < 2 or "".join(parts) != lower:
            return original
        if any(len(part) == 1 and part not in {"a", "i", "s"} for part in parts):
            return original
        if len(original) < 18 and len(parts) < 3 and not common.intersection(parts):
            return original

        if (
            match.start() > 0
            and match.string[match.start() - 1] in {"'", "’"}
            and parts[0] == "s"
        ):
            return "s" + (" " + " ".join(parts[1:]) if len(parts) > 1 else "")

        joined = " ".join(parts)
        if original[0].isupper():
            joined = joined[0].upper() + joined[1:]
        return joined

    previous = None
    current = value
    for _ in range(3):
        if current == previous:
            break
        previous = current
        current = ENGLISH_TOKEN_RE.sub(replace, current)
    current = re.sub(r"[ \t]{2,}", " ", current)
    return current.strip()


def patch_115_english_spacing_and_passages() -> None:
    """修復所有 115 年英文長黏字，並把誤併入選項的閱讀文章回填題組。"""
    paths = sorted(DATA_DIR.glob("*/115年/*/試題.json"))
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        questions = payload.get("questions")
        if not isinstance(questions, list):
            continue
        by_number = {
            q.get("number"): q
            for q in questions
            if isinstance(q, dict) and isinstance(q.get("number"), int)
        }
        changed = False

        for question in questions:
            if not isinstance(question, dict):
                continue
            candidates: list[tuple[str, str | None, str]] = []
            stem = question.get("stem")
            if isinstance(stem, str):
                candidates.append(("stem", None, stem))
            options = question.get("options")
            if isinstance(options, dict):
                for label, option in list(options.items()):
                    if isinstance(option, str):
                        candidates.append(("option", str(label), option))

            for kind, label, value in candidates:
                match = EMBEDDED_PASSAGE_RE.search(value)
                if not match:
                    continue
                start = int(match.group(1))
                end = int(match.group(2))
                if start > end or any(number not in by_number for number in range(start, end + 1)):
                    raise RuntimeError(f"題組範圍無法對應：{path} {start}-{end}")
                prefix = value[:match.start()].rstrip(" -、；;:")
                passage = repair_english_spacing(match.group(3))
                if not prefix or not passage:
                    raise RuntimeError(f"題組抽離結果為空：{path} {start}-{end}")
                if kind == "stem":
                    question["stem"] = prefix
                else:
                    assert isinstance(question.get("options"), dict) and label is not None
                    question["options"][label] = prefix
                for number in range(start, end + 1):
                    target = by_number[number]
                    if target.get("passage") != passage:
                        target["passage"] = passage
                changed = True

        for question in questions:
            if not isinstance(question, dict):
                continue
            for field in ("stem", "passage"):
                value = question.get(field)
                if isinstance(value, str):
                    repaired = repair_english_spacing(value)
                    if repaired != value:
                        question[field] = repaired
                        changed = True
            options = question.get("options")
            if isinstance(options, dict):
                for label, value in list(options.items()):
                    if not isinstance(value, str):
                        continue
                    repaired = repair_english_spacing(value)
                    if repaired != value:
                        options[label] = repaired
                        changed = True

        leftovers: list[tuple[object, str]] = []
        for question in questions:
            if not isinstance(question, dict):
                continue
            values = [question.get("stem"), question.get("passage")]
            options = question.get("options")
            if isinstance(options, dict):
                values.extend(options.values())
            for value in values:
                if not isinstance(value, str):
                    continue
                found = re.search(r"\b[a-z]{25,}\b", value)
                if found:
                    leftovers.append((question.get("number"), found.group(0)))
        if leftovers:
            raise RuntimeError(f"仍有英文長黏字：{path}：{leftovers[:20]}")
        if changed:
            write_json(path, payload)

def canonical_path_for(path: Path, payload: dict[str, Any]) -> str:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    duplicate_of = payload.get("_duplicate_of") or metadata.get("_duplicate_of")
    if duplicate_of:
        return str(duplicate_of).replace("\\", "/")
    return path.parent.relative_to(DATA_DIR).as_posix()


def patch_memberships_and_subject_names() -> None:
    paths = sorted(DATA_DIR.glob("*/115年/*/試題.json"))
    if len(paths) != 90:
        raise RuntimeError(f"115 年 JSON 應為 90 份，實際 {len(paths)}")

    loaded: dict[Path, dict[str, Any]] = {
        path: json.loads(path.read_text(encoding="utf-8")) for path in paths
    }
    memberships: dict[str, set[str]] = defaultdict(set)
    for path, payload in loaded.items():
        category = path.relative_to(DATA_DIR).parts[0]
        memberships[canonical_path_for(path, payload)].add(category)

    manifest_rows: list[dict[str, Any]] = []
    for canonical, categories in sorted(memberships.items()):
        manifest_rows.append({"canonical": canonical, "categories": sorted(categories)})

    for path, payload in loaded.items():
        category = path.relative_to(DATA_DIR).parts[0]
        canonical = canonical_path_for(path, payload)
        categories = sorted(memberships[canonical])
        metadata = payload.setdefault("metadata", {})
        changed = False
        if payload.get("categories") != categories:
            payload["categories"] = categories
            changed = True
        if metadata.get("categories") != categories:
            metadata["categories"] = categories
            changed = True
        official_subject = path.parent.name
        for truncated, full_name in FULL_SUBJECT_NAMES.items():
            if path.parent.name == truncated or path.parent.name.startswith(truncated[:40]):
                official_subject = full_name
                break
        if metadata.get("official_subject") != official_subject:
            metadata["official_subject"] = official_subject
            changed = True
        if metadata.get("path_subject") != path.parent.name:
            metadata["path_subject"] = path.parent.name
            changed = True
        if metadata.get("category_membership") != category:
            metadata["category_membership"] = category
            changed = True
        if changed:
            write_json(path, payload)

    write_json(
        DATA_DIR / "115_membership_manifest.json",
        {
            "schema_version": 1,
            "year": 115,
            "description": "115 年跨類科共同考卷正本與類科 membership；由唯讀稽核驗證。",
            "groups": manifest_rows,
        },
    )


def build_search_index_source() -> str:
    return '''#!/usr/bin/env python3
"""從考古題庫 JSON 生成前端搜尋索引。"""

from __future__ import annotations

import argparse
import glob
import gzip
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = ROOT / "考古題庫"
DEFAULT_OUTPUT = ROOT / "考古題網站" / "data" / "search-index.json"

FIELDS = [
    "cat", "cats", "yr", "sub", "no", "type", "passage", "stem",
    "optA", "optB", "optC", "optD", "ans",
]


def _categories(document: dict[str, Any], fallback: str) -> list[str]:
    raw = document.get("categories")
    metadata = document.get("metadata")
    if not isinstance(raw, list) and isinstance(metadata, dict):
        raw = metadata.get("categories")
    values = [str(value).strip() for value in (raw or []) if str(value).strip()]
    if fallback and fallback not in values:
        values.append(fallback)
    return sorted(set(values))


def load_exam_files(data_dir: Path) -> list[tuple]:
    files = sorted(glob.glob(str(data_dir / "**" / "試題.json"), recursive=True))
    rows: list[tuple] = []
    skipped = 0

    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as handle:
                document = json.load(handle)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            print(f"  SKIP {fp}: {exc}", file=sys.stderr)
            skipped += 1
            continue

        metadata = document.get("metadata") or {}
        if document.get("_is_duplicate") or metadata.get("_is_duplicate"):
            continue

        category = document.get("category", "")
        year = document.get("year")
        subject = document.get("subject", "")
        if not category or not year or not subject:
            rel = os.path.relpath(fp, str(data_dir))
            parts = rel.replace(os.sep, "/").split("/")
            category = category or (parts[0] if len(parts) > 0 else "")
            if not year:
                value = parts[1].replace("年", "") if len(parts) > 1 else ""
                year = int(value) if value.isdigit() else None
            subject = subject or (parts[2] if len(parts) > 2 else "")

        categories = _categories(document, category)
        for question in document.get("questions", []):
            qtype = question.get("type", "")
            options = question.get("options", {}) if qtype == "choice" else {}
            rows.append((
                category,
                categories,
                year,
                subject,
                str(question.get("number", "")),
                qtype,
                question.get("passage", ""),
                question.get("stem", ""),
                options.get("A", ""),
                options.get("B", ""),
                options.get("C", ""),
                options.get("D", ""),
                question.get("answer", "") if qtype == "choice" else "",
            ))

    if skipped:
        print(f"  跳過 {skipped} 個無法讀取的檔案", file=sys.stderr)
    return rows


def build_index(data_dir: Path) -> dict[str, Any]:
    rows = load_exam_files(data_dir)
    categories = sorted({category for row in rows for category in row[1] if category})
    subjects = sorted({row[3] for row in rows if row[3]})
    years = sorted({row[2] for row in rows if row[2]})
    columns = {field: [row[index] for row in rows] for index, field in enumerate(FIELDS)}
    return {
        "v": 2,
        "fields": FIELDS,
        "stats": {
            "total": len(rows),
            "choice": sum(1 for row in rows if row[5] == "choice"),
            "essay": sum(1 for row in rows if row[5] == "essay"),
            "categories": len(categories),
            "subjects": len(subjects),
        },
        "facets": {"categories": categories, "subjects": subjects, "years": years},
        "columns": columns,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成前端搜尋索引")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--output", "-o", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--gzip", action="store_true", help="同時產出 .gz 壓縮版")
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"資料目錄不存在: {data_dir}", file=sys.stderr)
        raise SystemExit(1)
    index = build_index(data_dir)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if args.gzip:
        with output.open("rb") as source, gzip.open(output.with_suffix(".json.gz"), "wb", compresslevel=9) as target:
            target.write(source.read())
    print(f"已產出: {output}")
    print(json.dumps(index["stats"], ensure_ascii=False))


if __name__ == "__main__":
    main()
'''


def search_engine_source() -> str:
    return '''/* === search-engine.js — 跨類科全文搜尋引擎 === */
(function (window) {
  'use strict';

  var ms = null;
  var rawData = null;
  var loading = null;
  var FIELDS = ['cat','cats','yr','sub','no','type','passage','stem','optA','optB','optC','optD','ans'];

  function loadIndex(basePath) {
    if (loading) return loading;
    loading = fetch((basePath || '') + 'data/search-index.json')
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        if (!data.columns || !data.columns.passage || !data.columns.cats) {
          throw new Error('搜尋索引版本過舊，請重新部署');
        }
        rawData = data;
        buildIndex(data);
        return data.stats;
      })
      .catch(function (error) {
        loading = null;
        throw error;
      });
    return loading;
  }

  function buildIndex(data) {
    var columns = data.columns;
    var documents = new Array(columns.cat.length);
    for (var i = 0; i < documents.length; i++) {
      var document = { id: i };
      FIELDS.forEach(function (field) { document[field] = columns[field][i]; });
      documents[i] = document;
    }
    ms = new MiniSearch({
      fields: ['passage','stem','optA','optB','optC','optD','sub'],
      storeFields: ['cat','cats','yr','sub','no','type','ans'],
      searchOptions: {
        boost: { stem: 3, passage: 2, sub: 1 },
        prefix: true,
        fuzzy: 0.15,
        tokenize: function (text) {
          text = String(text || '');
          return text
            .replace(/[\\s\\-_,.;:!?()（）\\[\\]{}「」『』【】《》〈〉、。，；：！？\\n\\r]+/g, ' ')
            .split(/\\s+/)
            .filter(Boolean)
            .concat(charTokens(text));
        }
      }
    });
    ms.addAll(documents);
  }

  function charTokens(text) {
    var chars = [];
    for (var i = 0; i < text.length; i++) {
      var code = text.charCodeAt(i);
      if (code >= 0x4e00 && code <= 0x9fff) chars.push(text[i]);
    }
    return chars;
  }

  function belongs(categories, category) {
    if (!category) return true;
    return Array.isArray(categories) && categories.indexOf(category) !== -1;
  }

  function answerMatches(answer, filterAnswer) {
    if (!filterAnswer) return true;
    if (answer === '送分') return filterAnswer === '送分';
    return String(answer || '').split('或').indexOf(filterAnswer) !== -1;
  }

  function passes(result, filters) {
    if (!filters) return true;
    if (filters.yr && result.yr !== filters.yr) return false;
    if (filters.cat && !belongs(result.cats, filters.cat)) return false;
    if (filters.sub && result.sub !== filters.sub) return false;
    if (filters.type && result.type !== filters.type) return false;
    if (filters.ans && !answerMatches(result.ans, filters.ans)) return false;
    return true;
  }

  function search(query, filters, limit) {
    if (!ms || !rawData) return [];
    var max = limit || 100;
    var results;
    if (query && query.trim()) {
      results = ms.search(query.trim(), { limit: max, filter: function (result) { return passes(result, filters); } });
    } else {
      results = [];
      var columns = rawData.columns;
      for (var i = 0; i < columns.cat.length && results.length < max; i++) {
        var candidate = {
          id: i,
          cat: columns.cat[i], cats: columns.cats[i], yr: columns.yr[i], sub: columns.sub[i],
          type: columns.type[i], ans: columns.ans[i]
        };
        if (passes(candidate, filters)) results.push({ id: i, score: 0 });
      }
    }
    var columns = rawData.columns;
    return results.map(function (result) {
      var id = result.id;
      return {
        idx: id, score: result.score || 0,
        cat: columns.cat[id], cats: columns.cats[id], yr: columns.yr[id], sub: columns.sub[id],
        no: columns.no[id], type: columns.type[id], passage: columns.passage[id], stem: columns.stem[id],
        optA: columns.optA[id], optB: columns.optB[id], optC: columns.optC[id], optD: columns.optD[id],
        ans: columns.ans[id]
      };
    });
  }

  function getFacets() { return rawData ? rawData.facets : null; }
  function getStats() { return rawData ? rawData.stats : null; }

  window.SearchEngine = { loadIndex: loadIndex, search: search, getFacets: getFacets, getStats: getStats };
})(window);
'''


def answer_utils_source() -> str:
    return '''/* === answer-utils.js — 官方答案契約 === */
(function (window) {
  'use strict';

  function parse(raw) {
    var value = String(raw || '').trim().toUpperCase();
    if (value === '送分') return { accepted: ['A','B','C','D'], bonus: true };
    var accepted = [];
    value.split('或').forEach(function (letter) {
      if ('ABCD'.indexOf(letter) !== -1 && accepted.indexOf(letter) === -1) accepted.push(letter);
    });
    return { accepted: accepted, bonus: false };
  }

  function accepts(raw, chosen) {
    var contract = parse(raw);
    return contract.bonus || contract.accepted.indexOf(String(chosen || '').toUpperCase()) !== -1;
  }

  window.AnswerUtils = { parse: parse, accepts: accepts };
})(window);
'''


def quiz_engine_source() -> str:
    return '''/* === quiz-engine.js — 模擬考試引擎 === */
(function (window) {
  'use strict';

  var state = {
    questions: [], answers: {}, marked: {}, current: 0,
    timer: null, secondsLeft: 0, totalSeconds: 0, started: false, finished: false
  };

  function prepareQuiz(opts) {
    var filters = {
      cat: opts.cat || '', yr: opts.yr ? parseInt(opts.yr, 10) : null,
      sub: opts.sub || '', type: 'choice', ans: ''
    };
    var pool = SearchEngine.search('', filters, 99999).filter(function (question) {
      return question.optA && question.optB && question.optC && question.optD &&
        AnswerUtils.parse(question.ans).accepted.length > 0;
    });
    var count = Math.min(opts.count || 20, pool.length);
    var shuffled = pool.slice();
    for (var i = shuffled.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var temporary = shuffled[i]; shuffled[i] = shuffled[j]; shuffled[j] = temporary;
    }
    state.questions = shuffled.slice(0, count);
    state.answers = {}; state.marked = {}; state.current = 0;
    state.started = false; state.finished = false;
    return { total: state.questions.length, poolSize: pool.length };
  }

  function startQuiz(minutes) {
    state.started = true; state.finished = false;
    state.totalSeconds = minutes * 60; state.secondsLeft = state.totalSeconds;
    startTimer();
  }

  function startTimer() {
    if (state.timer) clearInterval(state.timer);
    state.timer = setInterval(function () {
      state.secondsLeft--;
      if (state.secondsLeft <= 0) {
        state.secondsLeft = 0; clearInterval(state.timer); state.timer = null; finishQuiz();
      }
      if (typeof window.onTick === 'function') window.onTick(state.secondsLeft, state.totalSeconds);
    }, 1000);
  }

  function answer(index, letter) { if (!state.finished) state.answers[index] = letter; }
  function toggleMark(index) { if (state.marked[index]) delete state.marked[index]; else state.marked[index] = true; }
  function goTo(index) { if (index >= 0 && index < state.questions.length) state.current = index; }
  function next() { goTo(state.current + 1); }
  function prev() { goTo(state.current - 1); }

  function finishQuiz() {
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    state.finished = true;
    var correct = 0, wrong = 0, unanswered = 0, wrongList = [];
    state.questions.forEach(function (question, index) {
      var chosen = state.answers[index];
      var contract = AnswerUtils.parse(question.ans);
      if (contract.bonus) { correct++; return; }
      if (!chosen) { unanswered++; return; }
      if (AnswerUtils.accepts(question.ans, chosen)) correct++;
      else { wrong++; wrongList.push({ idx: index, question: question, chosen: chosen }); }
    });
    var elapsed = state.totalSeconds - state.secondsLeft;
    return {
      correct: correct, wrong: wrong, unanswered: unanswered, total: state.questions.length,
      pct: state.questions.length ? Math.round(correct / state.questions.length * 100) : 0,
      elapsed: elapsed, wrongList: wrongList
    };
  }

  function getState() { return state; }
  function getQuestion(index) { return state.questions[index] || null; }
  function getCurrentQuestion() { return state.questions[state.current] || null; }
  function getAnswer(index) { return state.answers[index]; }
  function isMarked(index) { return !!state.marked[index]; }

  function saveHistory(result) {
    try {
      var history = JSON.parse(localStorage.getItem('exam-quiz-history') || '[]');
      history.unshift({ date: new Date().toISOString(), correct: result.correct, total: result.total, pct: result.pct, elapsed: result.elapsed });
      localStorage.setItem('exam-quiz-history', JSON.stringify(history.slice(0, 50)));
    } catch (error) {}
  }
  function getHistory() { try { return JSON.parse(localStorage.getItem('exam-quiz-history') || '[]'); } catch (error) { return []; } }

  window.QuizEngine = {
    prepareQuiz: prepareQuiz, startQuiz: startQuiz, answer: answer, toggleMark: toggleMark,
    goTo: goTo, next: next, prev: prev, finishQuiz: finishQuiz,
    getState: getState, getQuestion: getQuestion, getCurrentQuestion: getCurrentQuestion,
    getAnswer: getAnswer, isMarked: isMarked, saveHistory: saveHistory, getHistory: getHistory
  };
})(window);
'''


def patch_frontend_sources() -> None:
    write_text(ROOT / "scripts/build_search_index.py", build_search_index_source())
    write_text(SITE_DIR / "js/search-engine.js", search_engine_source())
    write_text(SITE_DIR / "js/answer-utils.js", answer_utils_source())
    write_text(SITE_DIR / "js/quiz-engine.js", quiz_engine_source())

    quiz = SITE_DIR / "quiz.html"
    text = quiz.read_text(encoding="utf-8")
    if ".q-passage{" not in text:
        text = text.replace(
            ".q-stem{font-size:17px;font-weight:600;line-height:1.7;margin-bottom:20px}",
            ".q-passage{font-size:15.5px;line-height:1.85;margin-bottom:20px;padding:18px;background:var(--card-2);border:1px solid var(--border);border-radius:var(--radius);white-space:pre-wrap}.q-passage mark{font-weight:800;color:var(--primary);background:var(--primary-soft);padding:1px 4px;border-radius:4px}.q-stem{font-size:17px;font-weight:600;line-height:1.7;margin-bottom:20px}",
        )
    if 'id="qPassage"' not in text:
        text = text.replace(
            '<p class="q-stem" id="qStem"></p>',
            '<div class="q-passage" id="qPassage" hidden></div>\n      <p class="q-stem" id="qStem"></p>',
        )
    if '<script src="js/answer-utils.js"></script>' not in text:
        text = text.replace(
            '<script src="js/search-engine.js"></script>',
            '<script src="js/search-engine.js"></script>\n<script src="js/answer-utils.js"></script>',
        )
    text = text.replace(
        ").filter(q => q.optA && q.optB && q.optC && q.optD && 'ABCD'.indexOf(q.ans) >= 0);",
        ").filter(q => q.optA && q.optB && q.optC && q.optD && AnswerUtils.parse(q.ans).accepted.length > 0);",
    )
    old_build = """  questions = pool.slice(0,n).map(q=>({
    subj: q.yr + '年 ' + _esc(_short(q.sub,14)),
    stem: _esc(q.stem),
    opts: [q.optA,q.optB,q.optC,q.optD].map(_esc),
    ans: 'ABCD'.indexOf(q.ans),
  }));"""
    new_build = """  questions = pool.slice(0,n).map(q=>{
    const contract = AnswerUtils.parse(q.ans);
    return {
      subj: q.yr + '年 ' + _esc(_short(q.sub,14)),
      passage: _esc(q.passage || ''),
      stem: _esc(q.stem),
      opts: [q.optA,q.optB,q.optC,q.optD].map(_esc),
      accepted: contract.accepted.map(letter=>'ABCD'.indexOf(letter)),
      bonus: contract.bonus,
      answerLabel: q.ans,
    };
  });"""
    if old_build in text:
        text = text.replace(old_build, new_build)
    elif "accepted: contract.accepted" not in text:
        raise RuntimeError("quiz.html 找不到 buildQuestions 契約")
    old_render = """  $('qMeta').textContent = q.subj + ' · 選擇題';
  $('qStem').innerHTML = q.stem; // 題幹於 buildQuestions 已 escape"""
    new_render = """  $('qMeta').textContent = q.subj + ' · 選擇題';
  const passage = $('qPassage');
  passage.hidden = !q.passage;
  passage.innerHTML = q.passage.replace(/\\[\\[(\\d+)\\]\\]/g, '<mark>[$1]</mark>');
  $('qStem').innerHTML = q.stem; // 題幹與文章於 buildQuestions 已 escape"""
    if old_render in text:
        text = text.replace(old_render, new_render)
    elif "passage.hidden = !q.passage" not in text:
        raise RuntimeError("quiz.html 找不到 renderQuestion 契約")
    old_finish = """  questions.forEach((q,i)=>{
    if(answers[i]===null) skip++;
    else if(answers[i]===q.ans) ok++;
    else no++;
  });"""
    new_finish = """  questions.forEach((q,i)=>{
    if(q.bonus) ok++;
    else if(answers[i]===null) skip++;
    else if(q.accepted.includes(answers[i])) ok++;
    else no++;
  });"""
    if old_finish in text:
        text = text.replace(old_finish, new_finish)
    elif "if(q.bonus) ok++" not in text:
        raise RuntimeError("quiz.html 找不到 finish 契約")
    old_wrong = "const wrong = questions.map((q,i)=>({q,i})).filter(({q,i})=>answers[i]!==q.ans);"
    new_wrong = "const wrong = questions.map((q,i)=>({q,i})).filter(({q,i})=>!q.bonus && (answers[i]===null || !q.accepted.includes(answers[i])));"
    text = text.replace(old_wrong, new_wrong)
    text = text.replace("const isCorrect = j===q.ans;", "const isCorrect = q.accepted.includes(j) || q.bonus;")
    text = text.replace("const isWrong = answers[i]===j && j!==q.ans;", "const isWrong = answers[i]===j && !isCorrect;")
    if "${q.passage ? `<div class=\"q-passage\">" not in text:
        text = text.replace(
            '<p class="rv-stem">${q.stem}</p>',
            '${q.passage ? `<div class="q-passage">${q.passage.replace(/\\[\\[(\\d+)\\]\\]/g, \'<mark>[$1]</mark>\')}</div>` : \'\'}<p class="rv-stem">${q.stem}</p>',
        )
    write_text(quiz, text)

    search = SITE_DIR / "search.html"
    text = search.read_text(encoding="utf-8")
    text = text.replace("跨部門搜尋 41,811 道警察特考考古題。", "跨類科搜尋歷年警察特考考古題與閱讀題組。")
    if ".passage{" not in text:
        text = text.replace(
            ".options{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:14px}",
            ".passage{margin:12px 0;padding:14px;background:var(--card-2);border:1px solid var(--border);border-radius:var(--radius-sm);line-height:1.8;white-space:pre-wrap}.passage mark{font-weight:800;color:var(--primary);background:var(--primary-soft);padding:1px 4px;border-radius:4px}.options{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:14px}",
        )
    if '<script src="js/answer-utils.js"></script>' not in text:
        text = text.replace(
            '<script src="js/search-engine.js"></script>',
            '<script src="js/search-engine.js"></script>\n<script src="js/answer-utils.js"></script>',
        )
    old_card = """    var html = '<article class="result"><div class="tags">' + tags + '</div>' +
      '<p class="stem">' + _highlight(_esc(q.type==='essay' ? q.stem.substring(0,300) : q.stem)) + '</p>';"""
    new_card = """    var passage = q.passage ? '<div class="passage">' + _highlight(_esc(q.passage)).replace(/\\[\\[(\\d+)\\]\\]/g,'<mark>[$1]</mark>') + '</div>' : '';
    var html = '<article class="result"><div class="tags">' + tags + '</div>' + passage +
      '<p class="stem">' + _highlight(_esc(q.type==='essay' ? q.stem.substring(0,300) : q.stem)) + '</p>';"""
    if old_card in text:
        text = text.replace(old_card, new_card)
    elif "var passage = q.passage" not in text:
        raise RuntimeError("search.html 找不到 card 契約")
    text = text.replace(
        "(q.ans===L?' correct':'')",
        "(AnswerUtils.accepts(q.ans,L)?' correct':'')",
    )
    write_text(search, text)

    sw = SITE_DIR / "sw.js"
    text = sw.read_text(encoding="utf-8")
    text = re.sub(r"var CACHE_VERSION = 'v[^']+';", "var CACHE_VERSION = 'v1.5.0';", text, count=1)
    if "'./js/answer-utils.js'" not in text:
        text = text.replace("'./js/app.js',", "'./js/app.js',\n  './js/answer-utils.js',")
    write_text(sw, text)


def patch_downloader() -> None:
    path = ROOT / "scripts/download/download_115_police.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace("import urllib3\n", "")
    text = text.replace("\nurllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)\n", "\n")
    text = text.replace("verify=False", "verify=True")

    pattern = r"def safe_component\(value: str\) -> str:\n.*?\n\ndef sha256_bytes"
    replacement = '''def normalize_subject(value: str) -> str:
    value = html.unescape(value).strip()
    value = re.sub(r'[\\\\/:*?"<>|]', "", value)
    value = re.sub(r"\\s+", " ", value).rstrip(" .")
    if not value:
        raise ValueError("空白科目名稱")
    return value


def safe_component(value: str) -> str:
    """建立可追溯且不碰撞的安全路徑；完整名稱另存 official_subject。"""
    value = normalize_subject(value)
    if len(value.encode("utf-8")) <= 240:
        return value
    suffix = "__" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    prefix = value
    while prefix and len((prefix.rstrip(" .") + suffix).encode("utf-8")) > 240:
        prefix = prefix[:-1]
    prefix = prefix.rstrip(" .")
    if not prefix:
        raise ValueError("科目名稱無法建立安全路徑")
    return prefix + suffix


def sha256_bytes'''
    if "def normalize_subject(value: str)" not in text:
        text, count = re.subn(pattern, lambda _match: replacement, text, count=1, flags=re.DOTALL)
        if count != 1:
            raise RuntimeError("下載器 safe_component 區塊替換失敗")

    text = text.replace("return safe_component(subject)", "return normalize_subject(subject)")
    old = '''        subject = subject_from_link(link)
        absolute_url = urljoin(BASE_URL, html.unescape(href))'''
    new = '''        official_subject = subject_from_link(link)
        subject = safe_component(official_subject)
        absolute_url = urljoin(BASE_URL, html.unescape(href))'''
    if old in text:
        text = text.replace(old, new)
    if '"official_subject": official_subject,' not in text:
        text = text.replace('"subject": subject,\n            "file_type": file_type,', '"subject": subject,\n            "official_subject": official_subject,\n            "file_type": file_type,')

    marker = '''def make_session() -> requests.Session:
'''
    validator = '''def validate_pdf_bytes(data: bytes, source: str, content_type: str = "") -> None:
    normalized_type = content_type.lower().split(";", 1)[0].strip()
    if normalized_type and normalized_type not in {
        "application/pdf", "application/octet-stream", "application/x-download"
    }:
        raise RuntimeError(f"下載 Content-Type 非 PDF：{source}：{content_type}")
    if not data.startswith(b"%PDF-"):
        raise RuntimeError(f"內容缺少 PDF 檔頭：{source}")
    if len(data) <= 1024:
        raise RuntimeError(f"PDF 檔案過小（{len(data)} bytes）：{source}")
    if not data.rstrip().endswith(b"%%EOF"):
        raise RuntimeError(f"PDF 缺少 EOF 標記，可能截斷：{source}")
    try:
        import fitz
        with fitz.open(stream=data, filetype="pdf") as document:
            if document.page_count < 1:
                raise RuntimeError("頁數為 0")
            document.load_page(0)
    except Exception as exc:
        raise RuntimeError(f"PDF 無法解析：{source}：{exc}") from exc


'''
    if "def validate_pdf_bytes(" not in text:
        text = text.replace(marker, validator + marker)

    old_cache = '''        data = destination.read_bytes()
        if data.startswith(b"%PDF-") and len(data) > 1024:
            return data, True'''
    new_cache = '''        data = destination.read_bytes()
        validate_pdf_bytes(data, str(destination))
        return data, True'''
    text = text.replace(old_cache, new_cache)

    old_validation = '''    content_type = response.headers.get("Content-Type", "").lower()
    if not data.startswith(b"%PDF-"):
        preview = data[:120].decode("utf-8", errors="replace")
        raise RuntimeError(
            f"下載內容不是 PDF（{content_type or '無 Content-Type'}）：{url}；"
            f"前綴={preview!r}"
        )
    if len(data) <= 1024:
        raise RuntimeError(f"PDF 檔案過小（{len(data)} bytes）：{url}")'''
    new_validation = '''    content_type = response.headers.get("Content-Type", "")
    validate_pdf_bytes(data, url, content_type)'''
    text = text.replace(old_validation, new_validation)
    write_text(path, text)

    write_text(
        ROOT / "scripts/download/run_115_police_import.py",
        '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""115 年官方匯入器執行入口。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.download import download_115_police as importer  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(importer.main())
''',
    )


def patch_choice_repair_and_finalizer() -> None:
    path = ROOT / "scripts/parse/repair_115_choice_blocks.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "from scripts.parse.answer_extractor import parse_answer_pdf  # noqa: E402",
        "from scripts.parse.answer_extractor import find_answer_pdf, parse_answer_pdf  # noqa: E402",
    )
    text = text.replace('f"____({number})____",', 'f"[[{number}]]",')
    text = text.replace(
        '    answer_path = json_path.parent / "答案.pdf"',
        '    answer_path = find_answer_pdf(pdf_path, prefer_corrected=True)',
    )
    text = text.replace(
        "    if answer_path.exists():\n        answers = {",
        "    if answer_path is not None and answer_path.exists():\n        answers = {",
    )
    text = text.replace(
        '        payload["_answer_source"] = answer_path.name',
        '        payload["_answer_source"] = (answer_path.name if answer_path is not None else "")',
    )
    write_text(path, text)

    path = ROOT / "scripts/audit/finalize_115_import.py"
    text = path.read_text(encoding="utf-8")
    if '"official_subject": manifest_item.get("official_subject") or subject,' not in text:
        text = text.replace(
            '                    "official_category": info["official"],\n                    "source_url": manifest_item.get("url"),',
            '                    "official_category": info["official"],\n                    "official_subject": manifest_item.get("official_subject") or subject,\n                    "path_subject": subject,\n                    "source_url": manifest_item.get("url"),',
        )
    if 'categories = sorted({str(record["folder"]) for record in group})' not in text:
        text = text.replace(
            '        canonical = group[0]\n        if len(group) > 1:',
            '        canonical = group[0]\n        categories = sorted({str(record["folder"]) for record in group})\n        if len(group) > 1:',
        )
        text = text.replace(
            '            metadata = payload.setdefault("metadata", {})\n            # 清掉可能由重跑留下的舊標記。',
            '            metadata = payload.setdefault("metadata", {})\n            payload["categories"] = categories\n            metadata["categories"] = categories\n            metadata["category_membership"] = str(record["folder"])\n            # 清掉可能由重跑留下的舊標記。',
        )
    write_text(path, text)


def build_category_pages_source() -> str:
    categories = json.dumps(CATEGORY_NAMES, ensure_ascii=False, indent=4)
    return f'''#!/usr/bin/env python3
"""從題庫 JSON 重建類科總覽頁，不覆蓋首頁與現有共用 CSS/JS。"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "archive" / "misc" / "generate_html.py"
CATEGORIES = {categories}


def load_generator():
    spec = importlib.util.spec_from_file_location("exam_generate_html", GENERATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"無法載入生成器：{{GENERATOR_PATH}}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=ROOT / "考古題庫")
    parser.add_argument("--output", type=Path, default=ROOT / "考古題網站")
    args = parser.parse_args()
    generator = load_generator()
    all_data = generator.collect_json_data(args.data_dir)
    missing = [category for category in CATEGORIES if category not in all_data]
    if missing:
        raise RuntimeError("缺少類科資料：" + ", ".join(missing))
    for category in CATEGORIES:
        path = generator.generate_category_page(category, all_data[category], args.output)
        if not path:
            raise RuntimeError(f"類科頁生成失敗：{{category}}")
        content = Path(path).read_text(encoding="utf-8")
        if "115年" not in content:
            raise RuntimeError(f"類科頁未包含 115 年：{{path}}")
        print(path)


if __name__ == "__main__":
    main()
'''


def patch_generator_and_pages() -> None:
    path = ROOT / "archive/misc/generate_html.py"
    text = path.read_text(encoding="utf-8")
    replacements = {
        "刑事警察學系學系": "刑事警察學系",
        "鑑識科學學系學系": "鑑識科學學系",
        "水上警察學系學系": "水上警察學系",
        "資訊管理學系學系": "資訊管理學系",
        "行政警察學系學系": "行政警察學系",
        "外事警察學系學系": "外事警察學系",
        "公共安全學系社安組學系社安組": "公共安全學系社安組",
        "公共安全學系社安組學系情報組": "公共安全學系情報組",
        "國境警察學系境管組學系境管組": "國境警察學系境管組",
        "國境警察學系境管組學系移民組": "國境警察學系移民組",
        "行政管理學系學系": "行政管理學系",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    if "explicit_placeholder" not in text:
        needle = "    escaped = html_module.escape(str(text), quote=False)\n"
        insertion = '''    escaped = html_module.escape(str(text), quote=False)

    # 新格式以 [[題號]] 明確保存填空位置，不依賴 PDF 空白寬度。
    explicit_placeholder = re.compile(r"\\[\\[(\\d{1,3})\\]\\]")
    escaped = explicit_placeholder.sub(
        lambda match: f'<strong class="passage-qnum">[{match.group(1)}]</strong>',
        escaped,
    )
'''
        if needle not in text:
            raise RuntimeError("generate_html.py 找不到 passage escape 標記")
        text = text.replace(needle, insertion, 1)
    write_text(path, text)
    write_text(ROOT / "scripts/build_category_pages.py", build_category_pages_source())

    pages = ROOT / ".github/workflows/pages.yml"
    text = pages.read_text(encoding="utf-8")
    if "Generate category overview pages" not in text:
        text = text.replace(
            "      - name: Generate analytics\n        run: python scripts/build_analytics.py\n",
            "      - name: Generate analytics\n        run: python scripts/build_analytics.py\n\n      - name: Generate category overview pages\n        run: python scripts/build_category_pages.py\n",
        )
    write_text(pages, text)


def verifier_source() -> str:
    return '''#!/usr/bin/env python3
"""115 年匯入的獨立、唯讀完整性稽核。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

EXPECTED_CATEGORIES = {
    "行政警察學系", "外事警察學系", "刑事警察學系", "公共安全學系社安組",
    "犯罪防治學系預防組", "消防學系", "交通學系交通組", "資訊管理學系",
    "鑑識科學學系", "國境警察學系境管組", "水上警察學系", "法律學系", "行政管理學系",
}
REMOVED_WORKFLOWS = {
    "finalize-115-pipeline.yml", "ingest-115-police.yml", "merge-115-after-ci.yml",
    "merge-verified-115.yml", "rescue-115-pipeline.yml", "verify-115-and-open-pr.yml",
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    root = args.root.resolve()
    data = root / "考古題庫"
    errors: list[str] = []

    paths = sorted(data.glob("*/115年/*/試題.json"))
    categories = {path.relative_to(data).parts[0] for path in paths}
    if categories != EXPECTED_CATEGORIES:
        fail(errors, f"115 類科不符：{sorted(categories)}")
    if len(paths) != 90:
        fail(errors, f"115 JSON 應為 90，實際 {len(paths)}")

    manifest_path = data / "115_import_manifest.json"
    manifest = load(manifest_path)
    if manifest.get("exam_code") != "115060":
        fail(errors, "官方考試代碼不是 115060")
    if len(manifest.get("files") or []) != 153:
        fail(errors, "官方檔案清單不是 153 筆")
    for item in manifest.get("files") or []:
        rel = str(item.get("relative_path") or "")
        target = root / rel
        if not target.is_file():
            fail(errors, f"官方檔案缺漏：{rel}")
            continue
        if sha256(target) != item.get("sha256"):
            fail(errors, f"官方檔案 SHA 不符：{rel}")

    common = sorted(data.glob("*/115年/中華民國憲法與警察專業英文/試題.json"))
    if not common:
        fail(errors, "找不到共同英文卷")
    for path in common:
        document = load(path)
        by_number = {q.get("number"): q for q in document.get("questions", []) if q.get("type") == "choice"}
        q50 = by_number.get(50) or {}
        if (q50.get("options") or {}).get("D") != "deter":
            fail(errors, f"共同英文第 50 題仍受污染：{path}")
        p1 = (by_number.get(51) or {}).get("passage", "")
        for number in range(51, 56):
            question = by_number.get(number) or {}
            if question.get("passage") != p1 or p1.count(f"[[{number}]]") != 1:
                fail(errors, f"共同英文 {number} 題占位符／文章錯誤：{path}")
        p2 = (by_number.get(56) or {}).get("passage", "")
        if not p2 or "Zero Trust" not in p2:
            fail(errors, f"共同英文 56–60 題文章缺漏：{path}")
        for number in range(56, 61):
            if (by_number.get(number) or {}).get("passage") != p2:
                fail(errors, f"共同英文 {number} 題文章不一致：{path}")
        for number in range(41, 61):
            question = by_number.get(number) or {}
            for value in [question.get("stem", ""), *(question.get("options") or {}).values()]:
                if re.search(r"\\b[a-z]{25,}\\b", str(value)):
                    fail(errors, f"共同英文仍有異常黏字：{path} #{number}: {value}")

    membership = load(data / "115_membership_manifest.json")
    groups = membership.get("groups") or []
    by_canonical = {row["canonical"]: row["categories"] for row in groups}
    for path in paths:
        document = load(path)
        metadata = document.get("metadata") or {}
        canonical = document.get("_duplicate_of") or metadata.get("_duplicate_of") or path.parent.relative_to(data).as_posix()
        expected = by_canonical.get(canonical)
        if not expected:
            fail(errors, f"membership 缺 canonical：{canonical}")
        elif document.get("categories") != expected or metadata.get("categories") != expected:
            fail(errors, f"membership 未寫回：{path}")
        if not metadata.get("official_subject"):
            fail(errors, f"缺完整官方科名：{path}")

    workflow_dir = root / ".github/workflows"
    present = {path.name for path in workflow_dir.glob("*.yml")}
    remaining = sorted(present & REMOVED_WORKFLOWS)
    if remaining:
        fail(errors, "一次性自動合併工作流仍存在：" + ", ".join(remaining))
    for hidden in [
        root / "scripts/audit/.finalize_115_import.py.gz.b64",
        root / "scripts/parse/.recover_115_missing_choices.py.gz.b64",
    ]:
        if hidden.exists():
            fail(errors, f"隱藏可執行 payload 仍存在：{hidden.relative_to(root)}")

    downloader = (root / "scripts/download/download_115_police.py").read_text(encoding="utf-8")
    if "verify=False" in downloader or "disable_warnings" in downloader:
        fail(errors, "下載器仍關閉 TLS 驗證")
    for marker in ["%%EOF", "fitz.open", "official_subject"]:
        if marker not in downloader:
            fail(errors, f"下載器缺安全／追溯控制：{marker}")

    builder = (root / "scripts/build_search_index.py").read_text(encoding="utf-8")
    for marker in ['"cats"', '"passage"']:
        if marker not in builder:
            fail(errors, f"搜尋索引缺欄位：{marker}")
    quiz = (root / "考古題網站/quiz.html").read_text(encoding="utf-8")
    for marker in ["AnswerUtils.parse", "qPassage", "q.accepted.includes"]:
        if marker not in quiz:
            fail(errors, f"模擬考缺答案／文章契約：{marker}")

    if errors:
        raise SystemExit("115 唯讀稽核失敗（%d 項）：\\n- %s" % (len(errors), "\\n- ".join(errors)))
    print("115 唯讀稽核通過：13 類科、90 科次、官方清單、題組、membership、前端與治理契約均正確。")


if __name__ == "__main__":
    main()
'''


def test_115_source() -> str:
    return '''#!/usr/bin/env python3
"""115 年修補回歸測試。"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.build_search_index import build_index

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "考古題庫"


def test_search_index_preserves_passages_and_memberships(tmp_path):
    index = build_index(DATA)
    assert index["v"] == 2
    assert "passage" in index["fields"]
    assert "cats" in index["fields"]
    columns = index["columns"]
    rows = [
        i for i, (year, subject, number) in enumerate(zip(columns["yr"], columns["sub"], columns["no"]))
        if year == 115 and subject == "中華民國憲法與警察專業英文" and number == "51"
    ]
    assert len(rows) == 1
    row = rows[0]
    assert "[[51]]" in columns["passage"][row]
    assert len(columns["cats"][row]) > 1


def test_all_115_documents_have_official_subject_and_categories():
    paths = sorted(DATA.glob("*/115年/*/試題.json"))
    assert len(paths) == 90
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        metadata = document["metadata"]
        assert metadata["official_subject"]
        assert document["categories"] == metadata["categories"]
        assert path.relative_to(DATA).parts[0] in document["categories"]


def test_common_english_contract():
    paths = sorted(DATA.glob("*/115年/中華民國憲法與警察專業英文/試題.json"))
    assert paths
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        by_number = {q["number"]: q for q in document["questions"] if q.get("type") == "choice"}
        assert by_number[50]["options"]["D"] == "deter"
        for number in range(51, 56):
            assert by_number[number]["passage"].count(f"[[{number}]]") == 1
        for number in range(56, 61):
            assert "Zero Trust" in by_number[number]["passage"]
'''


def node_test_source() -> str:
    return '''const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const root = path.resolve(__dirname, '..');
global.window = {};
global.localStorage = { getItem: () => null, setItem: () => {} };
vm.runInThisContext(fs.readFileSync(path.join(root, 'js', 'answer-utils.js'), 'utf8'));
vm.runInThisContext(fs.readFileSync(path.join(root, 'js', 'quiz-engine.js'), 'utf8'));

assert.deepStrictEqual(window.AnswerUtils.parse('A或C').accepted, ['A', 'C']);
assert.strictEqual(window.AnswerUtils.accepts('A或C', 'A'), true);
assert.strictEqual(window.AnswerUtils.accepts('A或C', 'C'), true);
assert.strictEqual(window.AnswerUtils.accepts('A或C', 'B'), false);
assert.strictEqual(window.AnswerUtils.parse('送分').bonus, true);

function grade(answer, chosen) {
  const state = window.QuizEngine.getState();
  state.questions = [{ ans: answer }];
  state.answers = {};
  state.secondsLeft = 0;
  state.totalSeconds = 0;
  state.finished = false;
  if (chosen) state.answers[0] = chosen;
  return window.QuizEngine.finishQuiz();
}

assert.strictEqual(grade('A或C', 'A').correct, 1);
assert.strictEqual(grade('A或C', 'C').correct, 1);
assert.strictEqual(grade('A或C', 'B').wrong, 1);
assert.strictEqual(grade('送分').correct, 1);
console.log('quiz answer contract: ok');
'''


def maintenance_doc() -> str:
    return '''# 115 年題庫維護與驗收

## 正式流程

1. 下載器必須使用 TLS 憑證驗證，並檢查 PDF 檔頭、EOF、頁數與可解析性。
2. 修復工具只處理可由官方原卷確認的內容；答案一律透過「更正答案優先」入口。
3. `scripts/audit/finalize_115_import.py` 為資料遷移工具，會寫入資料；不得當成獨立驗證器。
4. CI 與合併前驗收只使用 `scripts/audit/verify_115_integrity.py`，該工具唯讀且不得產生 git diff。
5. 跨類科共同卷保留各類科副本供瀏覽，但搜尋索引只收正本，並以 `categories` 保存所有 membership。
6. 類科總覽頁在 Pages 建置時由 `scripts/build_category_pages.py` 重建。

## 合併門檻

- Python 全測試通過。
- Node 模擬考答案契約測試通過。
- 搜尋與分析資料可重建。
- 13 個 115 年類科頁可重建，且每頁可見 115 年。
- 唯讀稽核通過，執行後工作樹不得出現任何變更。
- PR 由維護者人工審查與合併；Repository 內不得保留自動 `gh pr merge` 工作流。

## Repository 設定

程式碼已移除所有自動合併工作流。Repository 管理員仍應在 GitHub Settings → Branches／Rulesets
對 `master` 啟用：禁止直接推送、要求 PR、至少一位核准者、要求 CI 與 Data Quality Check 通過。
'''




def node_test_source() -> str:
    return r"""'use strict';
// AnswerUtils contract loaded before QuizEngine.
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const storage = new Map();
const context = {
  console,
  setInterval: function () { return 1; },
  clearInterval: function () {},
  localStorage: {
    getItem: function (key) { return storage.has(key) ? storage.get(key) : null; },
    setItem: function (key, value) { storage.set(key, String(value)); },
  },
};
context.window = context;
vm.createContext(context);
vm.runInContext(
  fs.readFileSync('考古題網站/js/answer-utils.js', 'utf8'),
  context,
  { filename: 'answer-utils.js' }
);
vm.runInContext(
  fs.readFileSync('考古題網站/js/quiz-engine.js', 'utf8'),
  context,
  { filename: 'quiz-engine.js' }
);

assert.ok(context.AnswerUtils, 'AnswerUtils must be exported');
assert.ok(context.QuizEngine, 'QuizEngine must be exported');

function grade(answer, chosen) {
  const state = context.QuizEngine.getState();
  state.questions = [{ ans: answer }];
  state.answers = chosen ? { 0: chosen } : {};
  state.marked = {};
  state.current = 0;
  state.timer = null;
  state.secondsLeft = 30;
  state.totalSeconds = 60;
  state.started = true;
  state.finished = false;
  return context.QuizEngine.finishQuiz();
}

assert.deepStrictEqual(
  Array.from(context.AnswerUtils.parse('A或C').accepted),
  ['A', 'C']
);
assert.strictEqual(grade('A或C', 'A').correct, 1);
assert.strictEqual(grade('A或C', 'C').correct, 1);
assert.strictEqual(grade('A或C', 'B').wrong, 1);
assert.strictEqual(grade('A或C或D', 'D').correct, 1);
assert.strictEqual(grade('送分', 'B').correct, 1);
console.log('quiz answer contract passed');
"""

def patch_tests_docs_and_ci() -> None:
    write_text(ROOT / "scripts/audit/verify_115_integrity.py", verifier_source())
    write_text(ROOT / "tests/test_115_remediation.py", test_115_source())
    write_text(SITE_DIR / "tests/quiz-answer-contract.js", node_test_source())
    write_text(ROOT / "docs/115-maintenance.md", maintenance_doc())

    test_data = ROOT / "tests/test_data_quality.py"
    text = test_data.read_text(encoding="utf-8")
    if "test_no_suspicious_lowercase_concat_in_115" not in text:
        insertion = '''\n    def test_no_suspicious_lowercase_concat_in_115(self):
        """115 年英文題不得含 25 字以上全小寫黏字。"""
        issues = []
        for fp, q in ALL_QUESTIONS:
            if f"{os.sep}115年{os.sep}" not in fp:
                continue
            for value in _all_text_fields(q):
                match = re.search(r"\\b[a-z]{25,}\\b", value)
                if match:
                    issues.append((fp, q.get("number"), match.group(0)))
        assert not issues, f"115 年仍有異常英文黏字: {issues[:10]}"
'''
        anchor = "    def test_no_control_characters(self):"
        if anchor not in text:
            raise RuntimeError("test_data_quality 找不到插入點")
        text = text.replace(anchor, insertion + "\n" + anchor)
    write_text(test_data, text)

    ci = ROOT / ".github/workflows/ci.yml"
    text = ci.read_text(encoding="utf-8")
    if "Run independent 115 integrity audit" not in text:
        text = text.replace(
            "      - name: Run all tests\n        run: python -m pytest tests/ -v --tb=short\n",
            "      - name: Run independent 115 integrity audit\n        run: python scripts/audit/verify_115_integrity.py\n\n      - name: Run all tests\n        run: python -m pytest tests/ -v --tb=short\n",
        )
        text = text.replace(
            "      - name: Verify analytics generation\n        run: python scripts/build_analytics.py --output /tmp/analytics.json\n",
            "      - name: Verify analytics generation\n        run: python scripts/build_analytics.py --output /tmp/analytics.json\n\n      - name: Verify category overview generation\n        run: python scripts/build_category_pages.py --output /tmp/category-pages\n\n      - name: Verify quiz answer contract\n        run: node 考古題網站/tests/quiz-answer-contract.js\n",
        )
    write_text(ci, text)

    quality = ROOT / ".github/workflows/data-quality.yml"
    text = quality.read_text(encoding="utf-8").replace("\r\n", "\n")
    if "Verify 115 import integrity" not in text:
        text = text.replace(
            "      - name: Run data quality tests\n        run: python -m pytest tests/test_data_quality.py -v\n",
            "      - name: Verify 115 import integrity\n        run: python scripts/audit/verify_115_integrity.py\n\n      - name: Run data quality tests\n        run: python -m pytest tests/test_data_quality.py tests/test_115_remediation.py -v\n",
        )
    write_text(quality, text)


def patch_gitignore_and_remove_unsafe_files() -> None:
    path = ROOT / ".gitignore"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "# 允許正式考古題庫內的官方 PDF\n!考古題庫/**/*.pdf",
        "# 僅允許正式題庫中具有固定官方名稱的 PDF\n!考古題庫/**/試題.pdf\n!考古題庫/**/答案.pdf\n!考古題庫/**/更正答案.pdf\n!考古題庫/**/參考答案.pdf",
    )
    write_text(path, text)
    for relative in ONE_TIME_WORKFLOWS + HIDDEN_EXECUTABLES:
        delete_path(ROOT / relative)


def main() -> int:
    global APPLY
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="套用修補；省略時只檢查")
    args = parser.parse_args()
    APPLY = args.apply

    patch_common_english()
    patch_115_english_spacing_and_passages()
    patch_memberships_and_subject_names()
    patch_frontend_sources()
    patch_downloader()
    patch_choice_repair_and_finalizer()
    patch_generator_and_pages()
    patch_tests_docs_and_ci()
    patch_gitignore_and_remove_unsafe_files()

    if CHANGES:
        print("需要變更：")
        for change in CHANGES:
            print(f"- {change}")
        if not APPLY:
            return 1
        print(f"已套用 {len(CHANGES)} 項檔案變更。")
    else:
        print("115 年修補已完整套用，沒有待變更項目。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
