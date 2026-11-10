import importlib.util
import json
from pathlib import Path

from scripts.rag.build_corpus import build_corpus, question_id
from scripts.rag.query import format_results
from scripts.rag.verify_answers import (
    _alignment_location, _classify_record, _locate_question, _paper_structure_reasons,
    _question_segments, _raw_corpus, parse_answer_text, verify_corpus,
)


def _paper(number, text):
    return {"questions": [{"number": number, "text": text}]}


def test_parse_official_answer_table_and_correction_notes():
    text = """單選題數：3題
題號 第1題 第2題 第3題
答案 A # C
備註：第2題答案Ｂ或Ｄ或BD者均給分。第3題一律給分。
"""
    parsed = parse_answer_text(text)
    assert parsed["answers"] == {1: "A", 2: "#", 3: "C"}
    assert parsed["total"] == 3
    assert parsed["notes"][2] == {
        "answers": ["B", "D"], "free": False, "text": "第2題答案B或D或BD者均給分"
    }
    assert parsed["notes"][3]["free"] is True


def test_parse_preserves_multi_letter_cell_without_shifting_answers():
    parsed = parse_answer_text("題號 第1題 第2題\n答案 AB C")
    assert parsed["answers"] == {1: "AB", 2: "C"}


def test_parse_uses_exam_total_for_partial_answer_rows():
    parsed = parse_answer_text(
        "單選題數：25\n題號 第21題 第22題 第23題 第24題 第25題 "
        "第26題 第27題 第28題 第29題 第30題\n答案 A B C D A"
    )
    assert parsed["answers"] == {21: "A", 22: "B", 23: "C", 24: "D", 25: "A"}


def test_classification_catches_correction_and_wrong_archive_answer():
    url = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=S&code=106130"
    question_url = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=Q&code=106130"
    stem = "A sufficiently long question stem for official alignment."
    record = {
        "question_id": "q1", "type": "choice", "stem": stem, "answer": "C",
        "answer_status": "normal",
        "appears_in": [{"path": "甲/106年/英文", "number": 47}],
        "sources": [{"path": "甲/106年/英文", "answer_pdf_url": url,
                     "question_pdf_url": question_url}],
    }
    source = {
        "answers": {47: {"answers": ["B", "D"], "free": False,
                         "corrected": True, "unresolved": False}},
        "urls": [url, url.replace("t=S", "t=M")], "error": None,
    }
    result = _classify_record(record, {url: source}, {question_url: _paper(47, stem)})
    assert result["classification"] == "corrected"
    assert result["official"]["answers"] == ["B", "D"]
    assert result["official"]["corrected"] is True

    record["answer"] = "A"
    source["answers"][47] = {
        "answers": ["D"], "free": False, "corrected": False, "unresolved": False
    }
    assert _classify_record(record, {url: source}, {question_url: _paper(47, stem)})[
        "classification"
    ] == "mismatch"


def test_classifies_match_unparsed_and_ambiguous_source_numbers():
    url = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=S&code=106130"
    question_url = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=Q&code=106130"
    second_question_url = question_url + "&copy=2"
    stem = "A sufficiently long question stem for official alignment."
    record = {
        "question_id": "q1", "type": "choice", "stem": stem, "answer": "C",
        "answer_status": "normal",
        "appears_in": [{"path": "甲/106年/英文", "year": 106, "number": 48}],
        "sources": [{"path": "甲/106年/英文", "answer_pdf_url": url,
                     "question_pdf_url": question_url}],
    }
    parsed = {"answers": {48: {"answers": ["C"], "free": False,
                               "corrected": False, "unresolved": False}},
              "urls": [url], "error": None}
    papers = {question_url: _paper(48, stem)}
    assert _classify_record(record, {url: parsed}, papers)["classification"] == "match"
    assert _classify_record(record, {url: {"error": "PDF 解析失敗"}}, papers)[
        "classification"
    ] == "unparsed"
    assert _classify_record({**record, "sources": []}, {}, {})[
        "classification"
    ] == "no_official"
    missing = _classify_record(record, {url: {
        "answers": {47: {"answers": ["C"], "free": False,
                         "corrected": False, "unresolved": False}},
        "urls": [url], "error": None,
    }}, papers)
    assert missing["classification"] == "mismatch" and missing["verifiable"] is False
    assert missing["question_numbers"][0]["official_number"] == 48

    offset = {
        **record,
        "appears_in": [
            {"path": "甲/106年/英文", "year": 106, "number": 48},
            {"path": "乙/106年/英文", "year": 106, "number": 43},
        ],
        "sources": [
            {"path": "甲/106年/英文", "answer_pdf_url": url},
            {"path": "乙/106年/英文", "answer_pdf_url": url,
             "question_pdf_url": second_question_url},
        ],
    }
    ambiguous = _classify_record(offset, {url: {
        "answers": {
            48: {"answers": ["C"], "free": False, "corrected": False, "unresolved": False},
            43: {"answers": ["A"], "free": False, "corrected": False, "unresolved": False},
        },
        "urls": [url], "error": None,
    }}, {**papers, second_question_url: _paper(43, stem)})
    assert ambiguous["classification"] == "mismatch"
    assert ambiguous["verifiable"] is False


def test_renumbered_question_uses_official_number_and_answer():
    url = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=S&code=106130"
    question_url = url.replace("t=S", "t=Q")
    stem = "A sufficiently long question stem for official alignment."
    record = {
        "question_id": "renumbered", "type": "choice", "stem": stem, "answer": "A",
        "answer_status": "normal",
        "appears_in": [{"path": "甲/106年/英文", "number": 41}],
        "sources": [{"path": "甲/106年/英文", "answer_pdf_url": url,
                     "question_pdf_url": question_url}],
    }
    answers = {"answers": {46: {
        "answers": ["A"], "free": False, "corrected": False, "unresolved": False,
    }}, "urls": [url], "error": None}
    result = _classify_record(
        record, {url: answers}, {question_url: _paper(46, stem)}
    )
    assert result["classification"] == "renumbered"
    assert result["verifiable"] is True
    assert result["question_numbers"][0]["archive_number"] == 41
    assert result["question_numbers"][0]["official_number"] == 46

    record["answer"] = "B"
    mismatch = _classify_record(
        record, {url: answers}, {question_url: _paper(46, stem)}
    )
    assert mismatch["classification"] == "mismatch"
    assert mismatch["renumbered"] is True
    assert mismatch["official"]["answers"] == ["A"]


def test_short_stem_uses_options_for_unique_question_location():
    record = {
        "stem": "(見文章第54題空格)",
        "options": {
            "A": "the uniquely identifying alpha answer choice",
            "B": "the uniquely identifying beta answer choice",
        },
    }
    paper = {"questions": [
        {"number": 53, "text": "another question with unrelated answer choices"},
        {"number": 54, "text": "54 " + record["stem"] + " "
                               + " ".join(record["options"].values())},
    ]}
    located, method = _locate_question(record, paper)
    assert located["number"] == 54
    assert method == "options"
    aligned, reason = _alignment_location(record, paper)
    assert aligned["number"] == 54
    assert reason is None
    ambiguous, reason = _alignment_location(
        record, {"questions": [paper["questions"][1], {
            "number": 55, "text": "55 " + " ".join(record["options"].values()),
        }]}
    )
    assert ambiguous is None
    assert reason == "short_stem_options_not_unique"
    assert [item["number"] for item in _question_segments(
        "測驗題部分：\n1 first question\n\n2 second question\n\n21 內容中的第21組"
    )] == [1, 2]


def test_alignment_rejects_discontinuous_or_incomplete_question_papers():
    discontinuous = {"questions": [
        {"number": 1, "text": "1 first"},
        {"number": 2, "text": "2 second"},
        {"number": 4, "text": "4 fourth"},
    ]}
    assert "question_numbers_not_contiguous" in _paper_structure_reasons(
        discontinuous, 3
    )
    incomplete = {"questions": [
        {"number": 1, "text": "1 first"},
        {"number": 2, "text": "2 second"},
    ]}
    assert _paper_structure_reasons(incomplete, 3) == ["question_count_mismatch"]


def test_alignment_rejects_stem_that_only_appears_mid_paragraph():
    stem = "A sufficiently long question stem for official alignment."
    question = {"number": 4, "text": "4 " + ("context " * 8) + stem}
    located, reason = _alignment_location({"stem": stem}, {"questions": [question]})
    assert located is None
    assert reason == "stem_not_near_question_start"


def test_alignment_preserves_leading_year_after_removing_question_number():
    stem = "109年警察人員考試法規適用題目如下"
    question = {"number": 1, "text": "1 " + stem}
    located, reason = _alignment_location({"stem": stem}, {"questions": [question]})
    assert located is question
    assert reason is None


def test_alignment_rejects_passage_prompt_when_options_identify_another_question():
    record = {
        "stem": "Please answer questions 26 through 30 based on the following passage.",
        "options": {"A": "the unmistakable first answer choice",
                    "B": "the unmistakable second answer choice"},
    }
    paper = {"questions": [
        {"number": 25, "text": "25 prior choices " + record["stem"] + " shared passage"},
        {"number": 28, "text": "28 " + " ".join(record["options"].values())},
    ]}
    located, reason = _alignment_location(record, paper)
    assert located is None
    assert reason == "stem_options_disagree"


def _verify_synthetic_paper(
    tmp_path, monkeypatch, answers, archived_answers, *,
    archive_number_for_first=1, duplicate_last_with_answer=None,
    unverified_conflict_first=False,
):
    import scripts.rag.verify_answers as verifier

    count = len(answers)
    url = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=S&code=106130&c=507&s=0207"
    question_url = url.replace("t=S", "t=Q")
    records = []
    entries = {}
    questions = []
    for number in range(1, count + 1):
        path = f"甲/106年/科目{number}"
        stem = f"Question stem number {number} with enough identifying text."
        question_number = (archive_number_for_first if number == 1 else number)
        record = {
            "question_id": f"synthetic-{number}", "type": "choice", "stem": stem,
            "options": {"A": f"option alpha for question {number}",
                        "B": f"option beta for question {number}"},
            "answer": archived_answers[number - 1], "answer_status": "normal",
            "appears_in": [{"path": path, "number": question_number}],
            "sources": [{"path": path, "answer_pdf_url": url,
                         "question_pdf_url": question_url}],
        }
        if number == 1 and unverified_conflict_first:
            unverified_path = "乙/106年/未驗證"
            record["answer_conflicts"] = [{"value": "C", "paths": [path]}]
            record["appears_in"].append({
                "path": unverified_path, "number": question_number,
            })
            record["sources"].append({"path": unverified_path})
        records.append(record)
        entries[path] = {"answer_pdf_url": url, "question_pdf_url": question_url}
        option_text = " ".join(record["options"].values())
        questions.append({
            "number": number, "text": f"{number} {stem} {option_text}",
        })

    if duplicate_last_with_answer is not None:
        duplicate = dict(records[-1])
        duplicate["question_id"] = "synthetic-duplicate-last"
        duplicate["answer"] = duplicate_last_with_answer
        records.append(duplicate)

    class FakeClient:
        downloads = cache_hits = errors = 0

        def __init__(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(verifier, "MoexClient", FakeClient)
    monkeypatch.setattr(verifier, "_raw_corpus", lambda *_args: records)
    monkeypatch.setattr(verifier, "_official_pdf_answers", lambda *_args: {
        "answers": {
            number: {"answers": [answer], "free": False, "corrected": False,
                     "unresolved": False}
            for number, answer in enumerate(answers, 1)
        },
        "total": count, "urls": [url], "error": None,
    })
    monkeypatch.setattr(verifier, "_official_question_paper", lambda *_args: {
        "questions": questions, "parsed": True,
    })
    source_map = tmp_path / "source_map.json"
    source_map.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text("", encoding="utf-8")
    return verify_corpus(corpus, source_map, tmp_path / "cache")


def test_duplicate_question_ids_count_once_for_paper_consistency(tmp_path, monkeypatch):
    audit, _ = _verify_synthetic_paper(
        tmp_path, monkeypatch, ["A"] * 9, ["A"] * 8 + ["B"],
        duplicate_last_with_answer="A",
    )
    detail = next(item for item in audit["details"]
                  if item["question_id"] == "synthetic-9")
    assert detail["alignment_confirmed"] is False
    assert "paper_answer_consistency_below_0_9" in detail["alignment_reason_codes"]


def test_unverified_conflicting_renumbered_answer_is_not_overridden(tmp_path, monkeypatch):
    audit, overrides = _verify_synthetic_paper(
        tmp_path, monkeypatch, ["A"] * 11, ["B"] + ["A"] * 10,
        archive_number_for_first=41, unverified_conflict_first=True,
    )
    detail = next(item for item in audit["details"]
                  if item["question_id"] == "synthetic-1")
    assert detail["classification"] == "mismatch"
    assert detail["alignment_confirmed"] is True
    assert "synthetic-1" not in overrides["overrides"]
    assert "synthetic-1" in overrides["unresolved"]


def test_low_paper_answer_consistency_blocks_renumbered_override(tmp_path, monkeypatch):
    audit, overrides = _verify_synthetic_paper(
        tmp_path, monkeypatch, ["A"] * 5, ["B", "B", "A", "A", "A"],
        archive_number_for_first=41,
    )
    detail = next(item for item in audit["details"]
                  if item["question_id"] == "synthetic-1")
    assert detail["alignment_confirmed"] is False
    assert "paper_answer_consistency_below_0_9" in detail["alignment_reason_codes"]
    assert "synthetic-1" not in overrides["overrides"]
    assert "synthetic-1" in overrides["unresolved"]


def test_confirmed_renumbered_mismatch_uses_official_answer(tmp_path, monkeypatch):
    audit, overrides = _verify_synthetic_paper(
        tmp_path, monkeypatch, ["A"] * 11, ["B"] + ["A"] * 10,
        archive_number_for_first=41,
    )
    detail = next(item for item in audit["details"]
                  if item["question_id"] == "synthetic-1")
    assert detail["classification"] == "mismatch"
    assert detail["alignment_confirmed"] is True
    assert detail["alignment_reason_codes"] == []
    assert overrides["overrides"]["synthetic-1"]["answer"] == "A"
    assert "synthetic-1" not in overrides["unresolved"]
    assert audit["summary"]["new_renumbered_override_count"] == 1


def test_nonrenumbered_mismatch_override_does_not_require_alignment(tmp_path, monkeypatch):
    audit, overrides = _verify_synthetic_paper(
        tmp_path, monkeypatch, ["A"], ["B"],
    )
    detail = next(item for item in audit["details"]
                  if item["question_id"] == "synthetic-1")
    assert detail["classification"] == "mismatch"
    assert detail["renumbered"] is False
    assert detail["alignment_confirmed"] is False
    assert overrides["overrides"]["synthetic-1"]["answer"] == "A"


def test_main_does_not_retain_stale_override_from_disk(tmp_path, monkeypatch):
    import scripts.rag.verify_answers as verifier

    url = ("https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx"
           "?t=S&code=106130&c=507&s=0207")
    question_url = url.replace("t=S", "t=Q")
    path = "甲/106年/科目"
    stem = "A sufficiently long question stem for stale override testing."
    record = {
        "question_id": "stale-override", "type": "choice", "stem": stem,
        "answer": "A", "answer_status": "normal",
        "appears_in": [{"path": path, "number": 1}],
        "sources": [{"path": path, "answer_pdf_url": url,
                     "question_pdf_url": question_url}],
    }

    class FakeClient:
        downloads = cache_hits = errors = 0

        def __init__(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(verifier, "MoexClient", FakeClient)
    monkeypatch.setattr(verifier, "_raw_corpus", lambda *_args: [record])
    monkeypatch.setattr(verifier, "_official_pdf_answers", lambda *_args: {
        "answers": {1: {
            "answers": ["A"], "free": False, "corrected": False, "unresolved": False,
        }},
        "total": 1, "urls": [url], "error": None,
    })
    monkeypatch.setattr(verifier, "_official_question_paper", lambda *_args: {
        "questions": [{"number": 1, "text": f"1 {stem}"}], "parsed": True,
    })

    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text("", encoding="utf-8")
    source_map = tmp_path / "source_map.json"
    source_map.write_text(json.dumps({"entries": {path: {
        "answer_pdf_url": url, "question_pdf_url": question_url,
    }}}), encoding="utf-8")
    audit_path = tmp_path / "answer_audit.json"
    overrides_path = tmp_path / "answer_overrides.json"
    overrides_path.write_text(json.dumps({
        "overrides": {"stale-override": {"answer": "B"}},
    }), encoding="utf-8")

    verifier.main([
        "--corpus", str(corpus), "--root", str(tmp_path / "archive"),
        "--source-map", str(source_map), "--cache", str(tmp_path / "cache"),
        "--audit", str(audit_path), "--overrides", str(overrides_path), "--offline",
    ])

    written = json.loads(overrides_path.read_text(encoding="utf-8"))
    assert written["overrides"] == {}


def test_unaligned_question_is_not_overridden_and_becomes_conflict(tmp_path, monkeypatch):
    import scripts.rag.verify_answers as verifier

    url = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=S&code=106130"
    question_url = url.replace("t=S", "t=Q")
    path = "甲/106年/英文"
    record = {
        "question_id": "unaligned", "type": "choice",
        "stem": "A sufficiently long question stem for official alignment.",
        "answer": "C", "answer_status": "normal",
        "appears_in": [{"path": path, "number": 41}],
        "sources": [{"path": path, "answer_pdf_url": url,
                     "question_pdf_url": question_url}],
    }

    class FakeClient:
        downloads = cache_hits = errors = 0

        def __init__(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(verifier, "MoexClient", FakeClient)
    monkeypatch.setattr(verifier, "_raw_corpus", lambda *_args: [record])
    monkeypatch.setattr(verifier, "_official_pdf_answers", lambda *_args: {
        "answers": {46: {
            "answers": ["A"], "free": False, "corrected": False, "unresolved": False,
        }},
        "urls": [url], "error": None,
    })
    monkeypatch.setattr(verifier, "_official_question_paper", lambda *_args: _paper(
        46, "This is a different question and does not match."
    ))
    source_map = tmp_path / "source_map.json"
    source_map.write_text(json.dumps({"entries": {path: {
        "answer_pdf_url": url, "question_pdf_url": question_url,
    }}}), encoding="utf-8")
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text("", encoding="utf-8")

    audit, overrides = verify_corpus(corpus, source_map, tmp_path / "cache")
    assert audit["summary"]["counts"]["unaligned"] == 1
    assert overrides["overrides"] == {}
    assert "unaligned" in overrides["unresolved"]
    assert overrides["unresolved"]["unaligned"]["answer_conflicts"][0]["value"] == "C"

    # A located-but-renumbered mismatch is unresolved too: PDF numbering is heuristic.
    stem = "A sufficiently long question stem for official alignment."
    monkeypatch.setattr(verifier, "_official_question_paper", lambda *_args: _paper(46, stem))
    audit, overrides = verify_corpus(corpus, source_map, tmp_path / "cache")
    assert audit["summary"]["counts"]["mismatch"] == 1
    assert audit["summary"]["verifiable_question_count"] == 0
    assert overrides["overrides"] == {}
    assert "unaligned" in overrides["unresolved"]


def test_build_corpus_applies_official_multiple_answer_override(tmp_path):
    archive = tmp_path / "archive"
    path = "類別/106年/英文"
    question = {
        "number": 47, "type": "choice", "stem": "volcano question",
        "options": {"A": "a", "B": "b", "C": "c", "D": "d"}, "answer": "C",
    }
    folder = archive / path
    folder.mkdir(parents=True)
    (folder / "試題.json").write_text(
        json.dumps({"questions": [question]}, ensure_ascii=False), encoding="utf-8"
    )
    source_map = tmp_path / "source_map.json"
    source_map.write_text(json.dumps({
        "schema_version": 1,
        "entries": {path: {"answer_pdf_url": "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=S&code=106130"}},
    }), encoding="utf-8")
    identifier = question_id(question)
    override_data = {
        "summary": {"counts": {"corrected": 1}, "verifiable_question_count": 1,
                    "correct_rate": 0},
        "overrides": {identifier: {
            "answer": None, "answer_status": "multiple", "answer_values": ["B", "D"],
            "answer_source": "moex_official", "answer_correction": True,
            "answer_source_urls": ["https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=M&code=106130"],
        }},
    }
    records, stats = build_corpus(archive, source_map, answer_overrides=override_data)
    record = records[0]
    assert record["answer"] is None and record["answer_status"] == "multiple"
    assert record["answer_values"] == ["B", "D"]
    assert record["answer_source"] == "moex_official"
    assert record["answer_original"]["answer"] == "C"
    assert "answer_conflicts" not in record
    assert stats["answer_verification"]["correct_rate"] == 0
    assert stats["answer_verification"]["overrides_applied"] == 1
    disk_corpus = tmp_path / "corpus.jsonl"
    disk_corpus.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    raw = _raw_corpus(disk_corpus, source_map, archive)[0]
    assert raw["answer"] == "C" and "answer_source" not in raw

    unresolved_data = {"unresolved": {identifier: {
        "reason": "官方來源對應不一致，待核實",
        "answer_conflicts": [{"value": ["B", "D"], "paths": [path]}],
    }}}
    unresolved_records, _ = build_corpus(archive, source_map, answer_overrides=unresolved_data)
    assert unresolved_records[0]["answer_conflicts"][0]["value"] == ["B", "D"]


def test_official_multi_answer_renders_in_cli_and_space(monkeypatch):
    official = "https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=M&code=106130"
    item = {
        "rank": 1, "question_id": "q47", "type": "choice", "stem": "題目",
        "answer": None, "answer_status": "multiple", "answer_values": ["B", "D"],
        "answer_source": "moex_official", "answer_correction": True,
        "answer_source_urls": [official], "citations": [],
    }
    assert "答案：B 或 D 均給分（官方更正）" in format_results([item])

    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root))
    spec = importlib.util.spec_from_file_location("rag_answer_space_app", root / "space/app.py")
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    try:
        rendered = app.render([item])
        assert "答案：B 或 D 均給分（官方更正）" in rendered
        assert f"[開啟考選部官方答案]({official})" in rendered
    finally:
        app.executor.shutdown(wait=True)
