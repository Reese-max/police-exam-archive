import importlib.util
import json
from pathlib import Path

from scripts.rag.build_corpus import build_corpus, question_id
from scripts.rag.query import format_results
from scripts.rag.verify_answers import (
    _classify_record, _locate_question, _question_segments, _raw_corpus, parse_answer_text,
    verify_corpus,
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
    assert [item["number"] for item in _question_segments(
        "測驗題部分：\n1 first question\n\n2 second question\n\n21 內容中的第21組"
    )] == [1, 2]


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
