#!/usr/bin/env python3
"""Verify archived choice answers against official MOEX answer PDFs."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


ALLOWED_HOSTS = {"wwwq.moex.gov.tw", "wwwc.moex.gov.tw"}
PDF_PATH = "/exam/wHandExamQandA_File.ashx"
ANSWER_CHOICES = set("ABCD")
CLASSES = ("match", "corrected", "renumbered", "mismatch", "unaligned", "unparsed",
           "no_official")


def _normal_text(text):
    return unicodedata.normalize("NFKC", text or "")


def _answer_tokens(text):
    return re.findall(r"(?<![A-Z])[ABCD#]+(?![A-Z])", _normal_text(text).upper())


def _normalize_question_text(text):
    text = unicodedata.normalize("NFKC", text or "").casefold()
    return re.sub(r"[\W_]+", "", text)


def _question_segments(text):
    expected = 1
    starts = []
    for match in re.finditer(r"(?m)^[ \t]*(\d{1,3})[ \t]+(?=\S)", text):
        if int(match.group(1)) == expected:
            starts.append(match)
            expected += 1
    return [
        {"number": int(match.group(1)),
         "text": text[match.start():starts[index + 1].start()
                      if index + 1 < len(starts) else len(text)]}
        for index, match in enumerate(starts)
    ]


def parse_question_pdf(source):
    """Extract numbered test questions from an official question PDF."""
    try:
        import fitz

        document = (fitz.open(stream=source, filetype="pdf") if isinstance(source, bytes)
                    else fitz.open(str(source)))
        with document:
            text = "\n".join(page.get_text(sort=True) for page in document)
        questions = _question_segments(_normal_text(text))
        return {"questions": questions, "parsed": bool(questions)}
    except Exception:
        return {"questions": [], "parsed": False}


def _locate_question(record, paper):
    stem = _normalize_question_text(record.get("stem", ""))
    option_keys = [
        _normalize_question_text(value)
        for value in record.get("options", {}).values()
        if isinstance(value, str)
    ]
    option_keys = [key for key in option_keys if len(key) >= 8]
    stem_candidates = []
    option_candidates = []
    for question in paper.get("questions", []):
        body = _normalize_question_text(question.get("text", ""))
        if len(stem) >= 12 and stem in body:
            stem_candidates.append(question)
        hits = [key for key in option_keys if key in body]
        if (any(len(key) >= 20 for key in hits)
                or sum(len(key) >= 8 for key in hits) >= 2):
            option_candidates.append(question)

    if len(stem_candidates) == 1:
        return stem_candidates[0], "stem"
    if len(stem_candidates) > 1:
        narrowed = [item for item in stem_candidates if item in option_candidates]
        return (narrowed[0], "stem+options") if len(narrowed) == 1 else (None, None)
    if len(option_candidates) == 1:
        return option_candidates[0], "options"
    return None, None


def _parse_notes(text):
    notes = {}
    normalized = _normal_text(text)
    for match in re.finditer(r"第\s*(\d+)\s*題([^。\n；;]*)", normalized):
        number = int(match.group(1))
        clause = match.group(2)
        if "送分" in clause or "一律給分" in clause:
            notes[number] = {"answers": [], "free": True, "text": match.group(0)}
            continue
        if not re.search(r"給分|均給|皆給", clause):
            continue
        answer_part = re.search(r"答(?:案)?\s*(.*)", clause)
        if not answer_part:
            continue
        groups = re.findall(r"[A-D]+", answer_part.group(1).upper())
        accepted = sorted({letter for group in groups for letter in group if letter in ANSWER_CHOICES})
        if accepted:
            notes[number] = {"answers": accepted, "free": False, "text": match.group(0)}
    return notes


def parse_answer_text(text):
    """Parse MOEX's sorted text extraction into answers and per-question notes."""
    text = _normal_text(text)
    single_count = next((int(value) for value in re.findall(
        r"單選題數\s*[:：]\s*(\d+)", text
    )), 0)
    multiple_count = next((int(value) for value in re.findall(
        r"複選題數\s*[:：]\s*(\d+)", text
    )), 0)
    total = single_count + multiple_count or None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    answers = {}
    pending_numbers = None
    for line in lines:
        if "題號" in line:
            numbers = [int(value) for value in re.findall(r"第\s*(\d+)\s*題", line)]
            if total:
                numbers = [number for number in numbers if number <= total]
            pending_numbers = numbers or None
        elif pending_numbers and line.startswith("答案"):
            values = _answer_tokens(line[len("答案"):])
            if values and len(values) <= len(pending_numbers):
                answers.update(zip(pending_numbers, values))
            pending_numbers = None
        else:
            single = re.match(r"第\s*(\d+)\s*題\s*[:：]?\s*([A-D#])\b", line, re.I)
            if single:
                answers[int(single.group(1))] = single.group(2).upper()
    notes = _parse_notes(text)
    return {
        "answers": answers,
        "notes": notes,
        "total": total,
        "parsed": bool(answers or notes),
    }


def parse_answer_pdf(source):
    """Read a PDF path or its bytes with the repository's existing PyMuPDF."""
    try:
        import fitz

        document = (fitz.open(stream=source, filetype="pdf") if isinstance(source, bytes)
                    else fitz.open(str(source)))
        with document:
            text = "\n".join(page.get_text(sort=True) for page in document)
        return parse_answer_text(text)
    except Exception:
        return parse_answer_text("")


def _safe_official_url(url):
    try:
        parsed = urlsplit(url)
    except (TypeError, ValueError):
        return False
    return (parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS
            and parsed.path == PDF_PATH)


def _safe_question_url(url):
    if not _safe_official_url(url):
        return False
    return parse_qs(urlsplit(url).query, keep_blank_values=True).get("t") == ["Q"]


def _modified_url(url):
    if not _safe_official_url(url):
        raise ValueError(f"非考選部答案 PDF URL: {url!r}")
    parsed = urlsplit(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if query.get("t") != ["S"]:
        raise ValueError(f"標準答案 URL 必須使用 t=S: {url!r}")
    query["t"] = ["M"]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query, doseq=True), ""))


def _question_url(url):
    if not _safe_official_url(url):
        raise ValueError(f"非考選部答案 PDF URL: {url!r}")
    parsed = urlsplit(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if query.get("t") != ["S"]:
        raise ValueError(f"標準答案 URL 必須使用 t=S: {url!r}")
    query["t"] = ["Q"]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query, doseq=True), ""))


def _answer_record(number, standard, modified):
    base = (modified or {}).get("answers", {}).get(number)
    if base is None:
        base = standard.get("answers", {}).get(number)
    note = ((modified or {}).get("notes", {}).get(number)
            or standard.get("notes", {}).get(number))
    if note:
        choices, free = note["answers"], note["free"]
    elif base in ANSWER_CHOICES:
        choices, free = [base], False
    else:
        choices, free = [], False
    changed = bool(note) or (
        modified is not None and number in modified.get("answers", {})
        and modified["answers"][number] != standard.get("answers", {}).get(number)
    )
    return {
        "answers": choices,
        "free": free,
        "corrected": changed,
        "unresolved": not free and not choices,
    }


class _OfficialRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        target = urlsplit(new_url)
        if target.scheme != "https" or target.hostname not in ALLOWED_HOSTS:
            raise URLError("考選部 PDF 重新導向至允許網域外")
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


class MoexClient:
    """Rate-limited downloader; successful PDFs and not-found responses are cached."""

    def __init__(self, cache_dir, *, interval=0.5, timeout=30):
        self.cache_dir = Path(cache_dir)
        self.interval = interval
        self.timeout = timeout
        self.last_request = None
        self.downloads = 0
        self.cache_hits = 0
        self.errors = 0
        self.opener = build_opener(_OfficialRedirects())

    def fetch_pdf(self, url):
        if not _safe_official_url(url):
            return None, "非考選部官方 PDF URL"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        pdf_path = self.cache_dir / f"{key}.pdf"
        response_path = self.cache_dir / f"{key}.not_pdf.json"
        if pdf_path.is_file():
            self.cache_hits += 1
            return pdf_path.read_bytes(), None
        if response_path.is_file():
            self.cache_hits += 1
            response = json.loads(response_path.read_text(encoding="utf-8"))
            return None, response.get("reason", "官方端點未回傳 PDF")

        error = None
        for attempt in range(4):
            if self.last_request is not None:
                time.sleep(max(0, self.interval - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            request = Request(url, headers={"User-Agent": "police-exam-archive answer audit"})
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    data = response.read()
                    final_url = response.geturl()
                self.downloads += 1
                if data.startswith(b"%PDF-"):
                    pdf_path.write_bytes(data)
                    return data, None
                final_path = urlsplit(final_url).path.lower()
                expected_missing = (final_path.endswith("htmnotfoundpage.htm")
                                    or b"aspxerrorpath=" in data.lower())
                reason = "沒有考選部更正答案 PDF" if expected_missing else "官方端點未回傳 PDF"
                response_path.write_text(json.dumps(
                    {"reason": reason, "final_url": final_url}, ensure_ascii=False
                ) + "\n", encoding="utf-8")
                return None, reason
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                error = f"{type(exc).__name__}: {exc}"
                self.errors += 1
                if attempt < 3:
                    continue
        return None, f"下載重試 3 次仍失敗：{error}"


def _official_pdf_answers(url, client):
    standard_bytes, error = client.fetch_pdf(url)
    if standard_bytes is None:
        return {"error": f"標準答案 PDF 無法取得：{error}", "urls": [url]}
    standard = parse_answer_pdf(standard_bytes)
    if not standard["parsed"]:
        return {"error": "標準答案 PDF 無法解析", "urls": [url]}

    modified_url = _modified_url(url)
    modified_bytes, modified_error = client.fetch_pdf(modified_url)
    modified = None
    urls = [url]
    if modified_bytes is not None:
        modified = parse_answer_pdf(modified_bytes)
        if not modified["parsed"]:
            return {"error": "更正答案 PDF 無法解析", "urls": [url, modified_url]}
        urls.append(modified_url)
    elif modified_error != "沒有考選部更正答案 PDF":
        return {"error": f"更正答案狀態無法確認：{modified_error}", "urls": [url, modified_url]}

    numbers = set(standard["answers"]) | set(standard["notes"])
    if modified:
        numbers.update(modified["answers"])
        numbers.update(modified["notes"])
    return {
        "answers": {number: _answer_record(number, standard, modified) for number in numbers},
        "urls": urls,
        "error": None,
    }


def _official_question_paper(url, client):
    data, error = client.fetch_pdf(url)
    if data is None:
        return {"error": f"官方試題 PDF 無法取得：{error}", "questions": []}
    paper = parse_question_pdf(data)
    if not paper["parsed"]:
        return {"error": "官方試題 PDF 無法解析題號", "questions": []}
    return paper


def _archive_answers(record):
    if record.get("answer_conflicts"):
        values = [item.get("value") for item in record["answer_conflicts"]]
    elif record.get("answer_status") == "free":
        values = ["送分"]
    else:
        values = [record.get("answer")]
    return values


def _archive_matches(values, official):
    if official["free"]:
        return bool(values) and all(value == "送分" for value in values)
    return bool(values) and all(
        isinstance(value, str) and value.upper() in official["answers"] for value in values
    )


def _classify_record(record, source_answers, question_papers):
    occurrences = record.get("appears_in", [])
    source_map = {item["path"]: item for item in record.get("sources", [])}
    available = []
    question_numbers = []
    parse_errors = []
    unaligned_errors = []
    answer_errors = []
    for occurrence in occurrences:
        source = source_map.get(occurrence.get("path"), {})
        url = source.get("answer_pdf_url")
        if not url:
            continue
        archive_number = occurrence.get("number")
        if isinstance(archive_number, str) and archive_number.isdigit():
            archive_number = int(archive_number)
        if type(archive_number) is not int:
            unaligned_errors.append(f"題庫沒有有效題號：{occurrence.get('path')}")
            continue
        try:
            question_url = source.get("question_pdf_url") or _question_url(url)
        except ValueError as exc:
            unaligned_errors.append(str(exc))
            continue
        if not _safe_question_url(question_url):
            unaligned_errors.append(f"非考選部官方試題 PDF URL：{question_url!r}")
            continue
        paper = question_papers.get(question_url)
        if not paper or paper.get("error"):
            unaligned_errors.append(
                (paper or {}).get("error", "官方試題 PDF 未解析")
            )
            continue
        located, method = _locate_question(record, paper)
        if located is None:
            unaligned_errors.append(
                f"無法在官方試題 PDF 唯一定位題幹／選項：{question_url}"
            )
            continue
        number = located["number"]
        question_numbers.append({
            "path": occurrence.get("path"), "archive_number": archive_number,
            "official_number": number, "match_method": method,
            "question_url": question_url,
        })
        parsed = source_answers.get(url)
        if not parsed or parsed.get("error"):
            parse_errors.append((parsed or {}).get("error", "來源答案 PDF 未解析"))
            continue
        answer = parsed["answers"].get(number)
        if not answer or answer["unresolved"]:
            answer_errors.append(f"官方答案 PDF 未提供第 {number} 題答案：{url}")
            continue
        available.append({
            **answer, "url": url, "urls": parsed["urls"], "path": occurrence.get("path"),
            "archive_number": archive_number, "number": number, "match_method": method,
            "question_url": question_url,
        })

    urls = sorted({url for item in record.get("sources", [])
                   if (url := item.get("answer_pdf_url"))})
    if not urls:
        return {"classification": "no_official", "reason": "來源映射沒有標準答案 PDF",
                "urls": [], "verifiable": False}
    renumbered = any(
        item["archive_number"] != item["official_number"] for item in question_numbers
    )
    if unaligned_errors:
        return {
            "classification": "unaligned",
            "reason": "；".join(sorted(set(unaligned_errors))),
            "official_sources": [{
                "answers": item["answers"], "free": item["free"], "url": item["url"],
                "path": item["path"], "archive_number": item["archive_number"],
                "number": item["number"],
            } for item in available],
            "question_numbers": question_numbers, "renumbered": renumbered,
            "urls": urls, "verifiable": False,
        }
    if parse_errors:
        return {
            "classification": "unparsed", "reason": "；".join(sorted(set(parse_errors))),
            "question_numbers": question_numbers, "renumbered": renumbered,
            "urls": urls, "verifiable": False,
        }
    if answer_errors:
        return {
            "classification": "mismatch",
            "reason": "官方試題已定位，但答案表缺少題號：" + "；".join(sorted(set(answer_errors))),
            "official_sources": [{
                "answers": item["answers"], "free": item["free"], "url": item["url"],
                "path": item["path"], "archive_number": item["archive_number"],
                "number": item["number"],
            } for item in available],
            "question_numbers": question_numbers, "renumbered": renumbered,
            "urls": urls, "verifiable": False,
        }
    if not available:
        return {"classification": "mismatch", "reason": "未能將題庫來源題號對應至官方答案",
                "official_sources": [], "question_numbers": [], "renumbered": False,
                "urls": urls, "verifiable": False}

    official_sources = [{
        "answers": item["answers"], "free": item["free"], "url": item["url"],
        "path": item["path"], "archive_number": item["archive_number"],
        "number": item["number"], "question_url": item["question_url"],
    } for item in available]

    signatures = {(tuple(item["answers"]), item["free"]) for item in available}
    if len(signatures) != 1:
        return {
            "classification": "mismatch",
            "reason": "相同題目在實際官方題號對應到不同答案，無法安全判定",
            "official_sources": official_sources, "question_numbers": question_numbers,
            "renumbered": renumbered, "urls": urls, "verifiable": False,
        }

    official = {
        "answers": list(next(iter(signatures))[0]),
        "free": next(iter(signatures))[1],
        "corrected": any(item["corrected"] for item in available),
    }
    archive_values = _archive_answers(record)
    matches = _archive_matches(archive_values, official)
    if renumbered and matches:
        classification = "renumbered"
    elif renumbered:
        classification = "mismatch"
    elif len(official["answers"]) > 1:
        classification = "corrected"
    elif matches:
        classification = "match"
    elif official["corrected"]:
        classification = "corrected"
    else:
        classification = "mismatch"
    official["urls"] = sorted({url for item in available for url in item["urls"]})
    reason = ("題庫題號錯位，但答案與官方真實題號相符" if classification == "renumbered"
              else "題庫題號錯位，答案與官方真實題號不符" if classification == "mismatch"
              and renumbered else
              "官方更正含多個可接受答案" if classification == "corrected"
              and len(official["answers"]) > 1 else
              "官方更正答案與題庫答案不同" if classification == "corrected" else
              "題庫答案與考選部標準答案不同" if classification == "mismatch" else "")
    return {
        "classification": classification, "reason": reason, "official": official,
        "official_sources": official_sources, "archive_values": archive_values,
        "question_numbers": question_numbers, "renumbered": renumbered,
        "urls": official["urls"], "verifiable": True,
    }


def _conflicts_for_unresolved(record, result):
    conflicts = list(record.get("answer_conflicts", []))
    if not conflicts:
        value = "送分" if record.get("answer_status") == "free" else record.get("answer")
        conflicts.append({
            "value": value,
            "paths": sorted({item.get("path") for item in record.get("appears_in", [])
                             if item.get("path")}),
        })
    for source in result.get("official_sources", []):
        value = "送分" if source["free"] else (
            source["answers"][0] if len(source["answers"]) == 1 else source["answers"]
        )
        conflicts.append({"value": value, "paths": [source["path"]]})
    unique = {}
    for item in conflicts:
        unique[json.dumps(item, ensure_ascii=False, sort_keys=True)] = item
    return [unique[key] for key in sorted(unique)]


def _raw_corpus(corpus_path, source_map_path, root):
    if __package__:
        from .build_corpus import build_corpus
    else:
        from build_corpus import build_corpus
    corpus, _ = build_corpus(root, source_map_path, answer_overrides={})
    raw = {record["question_id"]: record for record in corpus}
    saved = {
        json.loads(line)["question_id"]: json.loads(line)
        for line in Path(corpus_path).read_text(encoding="utf-8").splitlines() if line.strip()
    }
    if raw.keys() != saved.keys():
        raise ValueError("corpus.jsonl 與原始題庫重建出的題目 ID 不一致")
    for identifier, record in raw.items():
        record["appears_in"] = saved[identifier].get("appears_in", record["appears_in"])
        record["sources"] = saved[identifier].get("sources", record["sources"])
    return list(raw.values())


def verify_corpus(corpus_path, source_map_path, cache_dir, root=Path("考古題庫")):
    corpus_path, source_map_path = Path(corpus_path), Path(source_map_path)
    corpus = _raw_corpus(corpus_path, source_map_path, root)
    source_map = json.loads(source_map_path.read_text(encoding="utf-8-sig"))
    entries = source_map.get("entries", {})
    for record in corpus:
        sources = {item["path"]: item for item in record.get("sources", [])}
        for appearance in record.get("appears_in", []):
            path = appearance.get("path")
            if path not in entries:
                continue
            source = sources.setdefault(path, {"path": path})
            source["answer_pdf_url"] = entries[path].get("answer_pdf_url")
            source["question_pdf_url"] = entries[path].get("question_pdf_url")
        record["sources"] = list(sources.values())
    choices = [record for record in corpus if record.get("type") == "choice"]
    urls = sorted({source.get("answer_pdf_url") for record in choices
                   for source in record.get("sources", []) if source.get("answer_pdf_url")})
    client = MoexClient(cache_dir)
    source_answers = {}
    for index, url in enumerate(urls, 1):
        try:
            source_answers[url] = _official_pdf_answers(url, client)
        except (ValueError, OSError) as exc:
            source_answers[url] = {"error": str(exc), "urls": [url]}
        if index % 25 == 0 or index == len(urls):
            print(f"[MOEX] 已檢查答案 PDF {index}/{len(urls)}", flush=True)

    question_urls = set()
    for record in choices:
        for source in record.get("sources", []):
            answer_url = source.get("answer_pdf_url")
            if not answer_url:
                continue
            question_url = source.get("question_pdf_url")
            if not question_url:
                try:
                    question_url = _question_url(answer_url)
                except ValueError:
                    continue
            if _safe_question_url(question_url):
                question_urls.add(question_url)
    question_papers = {}
    for index, url in enumerate(sorted(question_urls), 1):
        try:
            question_papers[url] = _official_question_paper(url, client)
        except (ValueError, OSError) as exc:
            question_papers[url] = {"error": str(exc), "questions": []}
        if index % 25 == 0 or index == len(question_urls):
            print(f"[MOEX] 已檢查試題 PDF {index}/{len(question_urls)}", flush=True)

    details, overrides, unresolved = [], {}, {}
    counts = Counter()
    renumbered_count = 0
    renumbered_occurrence_count = 0
    verifiable = 0
    correct = 0
    for record in choices:
        result = _classify_record(record, source_answers, question_papers)
        classification = result["classification"]
        counts[classification] += 1
        renumbered_count += bool(result.get("renumbered"))
        renumbered_occurrence_count += sum(
            item["archive_number"] != item["official_number"]
            for item in result.get("question_numbers", [])
        )
        # shortcut: question-number alignment from PDF text is heuristic (group/page headers
        # mislead it), so renumbered records never count as verified nor get overridden.
        if result.get("verifiable") and not result.get("renumbered"):
            verifiable += 1
            correct += classification in ("match", "renumbered")
        if classification == "match" and not result.get("renumbered"):
            continue
        official = result.get("official")
        detail = {
            "question_id": record["question_id"],
            "classification": classification,
            "renumbered": bool(result.get("renumbered")),
            "question_numbers": result.get("question_numbers", []),
            "archive_answer": {
                "answer": record.get("answer"),
                "answer_status": record.get("answer_status"),
                "answer_conflicts": record.get("answer_conflicts", []),
            },
            "official_answer": ({
                "answers": official["answers"], "free": official["free"],
                "corrected": official["corrected"],
            } if official else result.get("official_sources")),
            "urls": result["urls"],
            "reason": result["reason"],
        }
        details.append(detail)
        if classification in ("corrected", "mismatch") and official and not result.get("renumbered"):
            overrides[record["question_id"]] = {
                "answer": (official["answers"][0] if len(official["answers"]) == 1 else None),
                "answer_status": ("free" if official["free"] else
                                  "multiple" if len(official["answers"]) > 1 else "normal"),
                "answer_values": official["answers"],
                "answer_source": "moex_official",
                "answer_correction": official["corrected"],
                "answer_source_urls": official["urls"],
                "original_answer": record.get("answer"),
                "original_answer_status": record.get("answer_status"),
                "original_answer_conflicts": record.get("answer_conflicts", []),
            }
        elif classification in ("mismatch", "unaligned"):
            unresolved[record["question_id"]] = {
                "reason": result["reason"],
                "answer_conflicts": _conflicts_for_unresolved(record, result),
            }

    summary = {
        "choice_question_count": len(choices),
        "counts": {name: counts[name] for name in CLASSES},
        "verifiable_question_count": verifiable,
        "correct_rate": (correct / verifiable if verifiable else None),
        "renumbered_count": renumbered_count,
        "renumbered_occurrence_count": renumbered_occurrence_count,
        "override_count": len(overrides),
        "unresolved_mismatch_count": sum(
            item["classification"] == "mismatch"
            for item in details if item["question_id"] in unresolved
        ),
        "unresolved_question_count": len(unresolved),
        "source_pdf_count": len(urls),
        "question_pdf_count": len(question_urls),
        "downloaded_responses": client.downloads,
        "cache_hits": client.cache_hits,
        "request_errors": client.errors,
    }
    audit = {
        "schema_version": 1,
        "source": "考選部官方標準答案及更正答案 PDF",
        "summary": summary,
        "details": details,
    }
    override_data = {
        "schema_version": 1,
        "answer_source": "moex_official",
        "summary": summary,
        "overrides": overrides,
        "unresolved": unresolved,
    }
    return audit, override_data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("rag/corpus.jsonl"))
    parser.add_argument("--root", type=Path, default=Path("考古題庫"))
    parser.add_argument("--source-map", type=Path, default=Path("rag/source_map.json"))
    parser.add_argument("--cache", type=Path, default=Path("rag/.answer_cache"))
    parser.add_argument("--audit", type=Path, default=Path("rag/answer_audit.json"))
    parser.add_argument("--overrides", type=Path, default=Path("rag/answer_overrides.json"))
    args = parser.parse_args(argv)
    if not args.corpus.exists():
        if __package__:
            from .build_corpus import main as build_corpus_main
        else:
            from build_corpus import main as build_corpus_main
        build_corpus_main(["--out", str(args.corpus), "--source-map", str(args.source_map)])
    audit, overrides = verify_corpus(args.corpus, args.source_map, args.cache, args.root)
    for path, data in ((args.audit, audit), (args.overrides, overrides)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
