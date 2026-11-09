import hashlib
import json

import pytest

from scripts.rag.build_corpus import (
    answer_fields, build_corpus, folder_aliases, main, merge_passages, normalize_text, question_id,
)


def write_exam(root, path, questions):
    file = root / path / "試題.json"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps({"metadata": {"subject": "截斷"}, "questions": questions},
                               ensure_ascii=False), encoding="utf-8")


def choice(number=1, **fields):
    return {"number": number, "type": "choice", "stem": "甲,乙?",
            "options": dict(zip("ABCD", ("選項一", "選項二", "選項三", "選項四"))),
            "answer": "A", **fields}


def test_deduplication_sources_and_original_text(tmp_path):
    root = tmp_path / "archive"
    first = choice(10)
    second = choice(2, stem=" 甲，乙？\n", options=dict(reversed(list(first["options"].items()))))
    write_exam(root, "乙/107年/完整科目", [second])
    write_exam(root, "甲/106年/完整科目", [first, choice(2)])
    source_map = tmp_path / "sources.json"
    source_map.write_text(json.dumps({"schema_version": 1, "entries": {
        "甲/106年/完整科目": {"question_pdf_url": "https://example.org/q.pdf",
                            "answer_pdf_url": None}}}), encoding="utf-8")
    records, stats = build_corpus(root, source_map)
    assert len(records) == 1
    record = records[0]
    # Unicode path order puts 乙 before 甲; preserve that occurrence's original.
    assert record["stem"] == second["stem"]
    assert record["options"] == first["options"]
    assert [item["number"] for item in record["appears_in"]] == [2, 2, 10]
    assert all(item["subject"] == "完整科目" for item in record["appears_in"])
    assert {item["year"] for item in record["appears_in"]} == {106, 107}
    assert record["sources"] == [{"path": "甲/106年/完整科目",
        "question_pdf_url": "https://example.org/q.pdf", "answer_pdf_url": None}]
    assert record["text"].startswith("甲，乙？ (A)選項一")
    assert stats["file_count"] == 2
    assert stats["raw_questions_by_type"]["choice"] == 3
    assert stats["max_duplicate_count"] == 3
    assert stats["questions_with_sources"] == 1


@pytest.mark.parametrize("answer,status,raw", [
    ("送分", "free", None), (None, "none", None), ("", "none", None),
    ("A或B", "other", "A或B"), ("a", "other", "a"), ("AB", "other", "AB"),
])
def test_answer_status(answer, status, raw):
    fields = answer_fields(answer)
    assert fields["answer"] is None
    assert fields["answer_status"] == status
    assert fields.get("answer_raw") == raw


def test_missing_source_map(tmp_path):
    write_exam(tmp_path, "類別/106年/科目", [choice(answer="送分")])
    records, stats = build_corpus(tmp_path, tmp_path / "missing.json")
    assert records[0]["answer"] is None
    assert records[0]["answer_status"] == "free"
    assert records[0]["sources"] == []
    assert stats["answer_status"]["free"] == 1


def test_source_coverage_counts_local_sources_and_each_pdf_url_type(tmp_path):
    entries = {
        "甲/106年/選擇甲": {"question_pdf_url": "https://example.org/q1.pdf",
                           "answer_pdf_url": "https://example.org/a1.pdf"},
        "甲/106年/選擇乙": {"question_pdf_url": "https://example.org/q2.pdf",
                           "answer_pdf_url": None},
        "甲/106年/申論甲": {"question_pdf_url": None,
                           "answer_pdf_url": "https://example.org/a2.pdf"},
        "甲/106年/申論乙": {"question_pdf_url": None, "answer_pdf_url": None},
    }
    write_exam(tmp_path, "甲/106年/選擇甲", [choice(stem="選擇題甲")])
    write_exam(tmp_path, "甲/106年/選擇乙", [choice(stem="選擇題乙")])
    write_exam(tmp_path, "甲/106年/申論甲", [{"number": 1, "type": "essay", "stem": "申論題甲"}])
    write_exam(tmp_path, "甲/106年/申論乙", [{"number": 1, "type": "essay", "stem": "申論題乙"}])
    source_map = tmp_path / "sources.json"
    source_map.write_text(json.dumps({"schema_version": 1, "entries": entries}), encoding="utf-8")

    _, stats = build_corpus(tmp_path, source_map)

    assert stats["questions_with_sources"] == 4
    assert stats["questions_with_question_pdf_url"] == 2
    assert stats["questions_with_answer_pdf_url"] == 2
    assert stats["choice_questions_with_question_pdf_url"] == 2
    assert stats["choice_questions_with_answer_pdf_url"] == 1


@pytest.mark.parametrize("field,value", [
    ("passage_group", "group-1"), ("passage_group", "1-2"),
    ("passage_question_range", "1-2"), ("passage_intro", "請依下文回答第1題至第2題"),
])
def test_group_passage_is_shared(tmp_path, field, value):
    first = choice(1, **{field: value}, passage="共同文章,內容")
    second = choice(2, stem="第二題")
    if field == "passage_group" and value == "group-1":
        second[field] = value
    if field != "passage_intro":
        first["passage_intro"] = "請依下文回答第1題至第2題"
    unrelated = choice(3, stem="第三題")
    essay = {"number": 2, "type": "essay", "stem": "申論", "answer": "A"}
    write_exam(tmp_path, "類別/106年/科目", [first, second, unrelated, essay])
    records, _ = build_corpus(tmp_path, tmp_path / "missing.json")
    by_stem = {record["stem"]: record for record in records}
    for stem in (first["stem"], second["stem"]):
        assert "共同文章,內容" in by_stem[stem]["passage"]
        assert "請依下文回答第1題至第2題" in by_stem[stem]["passage"]
        assert "共同文章，內容" in by_stem[stem]["text"]
    assert by_stem["第三題"]["passage"] == ""
    assert by_stem["申論"]["passage"] == ""
    assert by_stem["申論"]["answer_status"] == "none"
    assert "options" not in by_stem["申論"]


def test_answer_conflicts_majority_and_tie(tmp_path):
    for category, answer in (("a", "B"), ("b", "A"), ("c", "B")):
        write_exam(tmp_path, f"{category}/106年/科目", [choice(answer=answer),
                   choice(2, stem="平票", answer="B" if category == "a" else "A")]
                   if category != "c" else [choice(answer=answer)])
    records, stats = build_corpus(tmp_path, tmp_path / "missing.json")
    by_stem = {record["stem"]: record for record in records}
    assert by_stem["甲,乙?"]["answer"] == "B"
    assert by_stem["甲,乙?"]["answer_conflicts"] == [
        {"value": "B", "paths": ["a/106年/科目", "c/106年/科目"]},
        {"value": "A", "paths": ["b/106年/科目"]},
    ]
    assert by_stem["平票"]["answer"] == "A"
    assert stats["answer_conflict_count"] == 2


def test_normalization_and_identity():
    assert normalize_text("甲,乙;丙:丁?戊!己(庚)辛") == "甲，乙；丙：丁？戊！己（庚）辛"
    assert normalize_text(" English,  text; (x)?!\n  1.5 ") == "English, text; (x)?! 1.5"
    question = choice(stem="甲，乙？")
    identity = ["choice", "甲，乙？", [[key, question["options"][key]] for key in "ABCD"], ""]
    encoded = json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode()
    assert question_id(question) == hashlib.sha1(encoded).hexdigest()[:16]
    assert question_id(question) == question_id(choice(stem=" 甲,乙?\n"))
    assert question_id(question) != question_id({**question, "type": "essay"})
    assert question_id(question, "文章甲") != question_id(question, "文章乙")
    assert question_id(question, "甲,乙?\n") == question_id(question, "甲，乙？")


def test_passage_scope_and_ambiguous_ranges_without_io():
    questions = [
        choice(1, passage_question_range="1-2", passage_intro="第一組", passage="文章一"),
        choice(2),
        choice(3, passage_question_range="2-3", passage="文章二"),
        choice(2, section="另一節"),
        {"number": 1, "type": "essay", "stem": "申論"},
    ]
    assert merge_passages(questions) == ["第一組\n文章一", "", "文章二", "", ""]
    questions.pop(2)
    assert merge_passages(questions) == ["第一組\n文章一", "第一組\n文章一", "", ""]


def test_cli_output_is_byte_stable(tmp_path):
    root = tmp_path / "archive"
    write_exam(root, "b/107年/科目", [choice(answer="B", passage="文章乙")])
    write_exam(root, "a/106年/科目", [choice(passage="文章甲"),
        {"number": 2, "type": "essay", "stem": "申論"}])
    output, stats = tmp_path / "rag/corpus.jsonl", tmp_path / "rag/stats.json"
    args = ["--root", str(root), "--source-map", str(tmp_path / "missing.json"),
            "--out", str(output), "--stats", str(stats)]
    main(args)
    issues = stats.with_name("corpus_issues.json")
    before = output.read_bytes(), stats.read_bytes(), issues.read_bytes()
    main(args)
    assert before == (output.read_bytes(), stats.read_bytes(), issues.read_bytes())
    assert b"\r" not in b"".join(before)
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [record["question_id"] for record in records] == sorted(record["question_id"] for record in records)
    choices = [record for record in records if record["type"] == "choice"]
    assert len(choices) == 2
    assert {record["passage"] for record in choices} == {"文章甲", "文章乙"}
    record = choices[0]
    assert record["stem"] == "甲,乙?"
    assert "甲，乙？ (A)選項一" in record["text"]


def test_invalid_inputs_fail_instead_of_silent_empty_output(tmp_path):
    with pytest.raises(ValueError, match="not a directory"):
        build_corpus(tmp_path / "missing", tmp_path / "source.json")
    source_map = tmp_path / "source.json"
    source_map.write_text('{"schema_version": 2, "entries": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        build_corpus(tmp_path, source_map)


@pytest.mark.parametrize("answers", [("A", "B"), ("A", None), (None, None)])
def test_cloze_collision_ordinals_match_across_files(tmp_path, answers):
    # Include a non-colliding subquestion: ordinals are within the whole passage,
    # not just within the collision group, and remain independent of answer value.
    questions = [choice(37, passage_group="37-39", passage="Fill __ and __.", answer=answers[0]),
                 choice(38, passage_group="37-39", stem="Another prompt"),
                 choice(39, passage_group="37-39", answer=answers[1])]
    for category in ("甲", "乙"):
        write_exam(tmp_path, f"{category}/106年/英文", questions)
    issues = {}
    records, stats = build_corpus(tmp_path, tmp_path / "missing.json", issues=issues)
    assert len(records) == 3
    assert all(len(record["appears_in"]) == 2 for record in records)
    assert all(len({item["path"] for item in record["appears_in"]}) == 2 for record in records)
    assert not any("answer_conflicts" in record for record in records)
    assert stats["disambiguated_collision_groups"] == 2
    assert issues["in_file_duplicates"] == []
    passage = merge_passages(questions)[0]
    assert question_id(questions[0], passage, ["passage_ordinal", 1]) in {r["question_id"] for r in records}
    assert question_id(questions[2], passage, ["passage_ordinal", 3]) in {r["question_id"] for r in records}


def test_in_file_duplicates_are_recorded_without_extra_answer_votes(tmp_path):
    write_exam(tmp_path, "甲/106年/科目", [choice(49), choice(50)])
    write_exam(tmp_path, "乙/106年/科目", [choice(49, answer="B")])
    issues = {}
    records, stats = build_corpus(tmp_path, tmp_path / "missing.json", issues=issues)
    assert len(records) == 1
    record = records[0]
    assert len(record["appears_in"]) == 3  # Preserve both original question numbers.
    assert issues["in_file_duplicates"] == [{"path": "甲/106年/科目",
        "numbers": [49, 50], "question_id": record["question_id"]}]
    assert stats["in_file_duplicate_count"] == 1
    assert stats["disambiguated_collision_groups"] == 0
    assert all(len(vote["paths"]) == 1 for vote in record["answer_conflicts"])


def test_collision_without_passage_uses_question_number(tmp_path):
    for category in ("甲", "乙"):
        write_exam(tmp_path, f"{category}/106年/科目", [choice(49), choice(50, answer="B")])
    records, stats = build_corpus(tmp_path, tmp_path / "missing.json")
    assert len(records) == 2
    assert all(len(record["appears_in"]) == 2 for record in records)
    assert all(len({item["number"] for item in record["appears_in"]}) == 1 for record in records)
    assert stats["disambiguated_collision_groups"] == 2


def test_folder_aliases():
    from pathlib import Path
    paths = [Path("犯罪防治矯治組/106年/數學(甲)"),
             Path("犯罪防治學系矯治組/107年/數學（甲）"),
             Path("犯罪防治矯治組/108年/數學(乙)")]
    aliases = folder_aliases(paths)
    assert aliases == folder_aliases(list(reversed(paths)))
    assert {tuple(item["names"]) for item in aliases} == {
        tuple(sorted(["犯罪防治矯治組", "犯罪防治學系矯治組"])),
        tuple(sorted(["數學(甲)", "數學（甲）"])),
    }


def test_folder_aliases_are_in_issues(tmp_path):
    write_exam(tmp_path, "犯罪防治矯治組/106年/科目(甲)", [choice()])
    write_exam(tmp_path, "犯罪防治學系矯治組/106年/科目（甲）", [choice()])
    issues = {}
    build_corpus(tmp_path, tmp_path / "missing.json", issues=issues)
    assert {item["kind"] for item in issues["folder_aliases"]} == {"category", "subject"}
