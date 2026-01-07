import pytest

from auto_generate_form import detect_columns


def test_detect_columns_handles_case_and_aliases():
    headers = [
        "Year",
        "試題編號",
        "題幹",
        "選項A",
        "選項B",
        "選項C",
        "選項D",
        "正確答案",
    ]

    mapping = detect_columns(headers)

    assert mapping["year"] == "Year"
    assert mapping["number"] == "試題編號"
    assert mapping["title"] == "題幹"
    assert mapping["answer"] == "正確答案"
    assert mapping["option_a"] == "選項A"
    assert mapping["option_d"] == "選項D"


def test_detect_columns_requires_core_headers():
    with pytest.raises(ValueError):
        detect_columns(["年份", "標準答案"])
