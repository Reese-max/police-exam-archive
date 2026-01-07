from pathlib import Path

import auto_generate_form as agf


def make_question():
    return agf.Question(
        year="2025",
        number="1",
        title="題目敘述",
        answer="A",
        option_a="甲",
        option_b="乙",
        option_c="丙",
        option_d="丁",
    )


def test_render_gas_contains_title_description():
    gas = agf.render_gas(
        [make_question()],
        form_title="自動化測試表單",
        form_description="描述",
        questions_per_page=7,
    )
    assert "自動化測試表單" in gas
    assert "描述" in gas
    assert "QUESTIONS = [" in gas
    assert "questions_per_page" not in gas  # ensure formatting works


def test_write_file_creates_directories(tmp_path):
    nested = tmp_path / "deep/nesting/output.txt"
    agf.write_file(nested, "content")
    assert nested.exists()
    assert nested.read_text(encoding="utf-8") == "content"
