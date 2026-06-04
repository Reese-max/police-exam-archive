# -*- coding: utf-8 -*-
"""
patterns.py 單元測試（pytest）

跑法:
    pytest tests/test_patterns.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

# 讓 tests/ 能直接 import scripts/parse 模組
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.parse import patterns as p  # noqa: E402


class TestChoiceQuestion:
    def test_basic_number_dot(self):
        m = p.CHOICE_Q_PATTERN.match("1. 依憲法規定")
        assert m and m.group(1) == "1" and "依憲法" in m.group(2)

    def test_full_width_paren(self):
        m = p.CHOICE_Q_PATTERN.match("12、下列何者正確?")
        assert m and m.group(1) == "12"

    def test_three_digit(self):
        m = p.CHOICE_Q_PATTERN.match("100. 最後一題")
        assert m and m.group(1) == "100"

    def test_numeric_sequence_not_a_question(self):
        # 申論題內的數據序列「81、76、79、72」不應被當成題號 81
        assert p.CHOICE_Q_PATTERN.match("81、76、79、72、71、60、40") is None

    def test_numeric_sequence_with_space_not_a_question(self):
        # 題號後若是空白再接數字，也不應匹配
        assert p.CHOICE_Q_PATTERN.match("81 76 79 72") is None

    def test_circuit_symbols_not_a_question(self):
        # 電路圖符號「3 A 3Ω」「t = 0」不應被誤判為題號
        assert p.CHOICE_Q_PATTERN.match("3 A 3Ω") is None
        assert p.CHOICE_Q_PATTERN.match("6Ω 3 Ω") is None
        assert p.CHOICE_Q_PATTERN.match("4:1") is None

    def test_no_separator_chinese_ok(self):
        # 「1 依憲法」這種空白分隔但接中文的格式仍應匹配
        m = p.CHOICE_Q_PATTERN.match("1 依憲法規定")
        assert m and m.group(1) == "1"

    def test_english_question_ok(self):
        # 「1 What is...」英文題幹應匹配
        m = p.CHOICE_Q_PATTERN.match("1 What is the most important?")
        assert m and m.group(1) == "1"

    def test_short_letter_not_question(self):
        # 「3 A 3Ω」單個字母不該匹配
        assert p.CHOICE_Q_PATTERN.match("3 A 3Ω") is None

    def test_year_unit_not_a_question(self):
        # 「107年特種考試」不該被當題號
        assert p.CHOICE_Q_PATTERN.match("107年特種考試") is None
        assert p.CHOICE_Q_PATTERN.match("107 年特種考試") is None

    def test_distance_unit_not_a_question(self):
        # 「12浬處遭海巡」「50公尺處」不該被當題號
        assert p.CHOICE_Q_PATTERN.match("12浬處遭海巡人員查獲") is None
        assert p.CHOICE_Q_PATTERN.match("50 公尺處") is None

    def test_age_unit_not_a_question(self):
        # 「30歲以上」不該匹配
        assert p.CHOICE_Q_PATTERN.match("30歲以上") is None

    def test_chinese_quote_question(self):
        # 「2 「樹上的花是小說...」」應視為題號 2
        m = p.CHOICE_Q_PATTERN.match("2 「樹上的花是小說")
        assert m and m.group(1) == "2"


class TestEssayQuestion:
    def test_chinese_one(self):
        m = p.ESSAY_Q_PATTERN.match("一、試說明")
        assert m and m.group(1) == "一"

    def test_chinese_ten_plus(self):
        m = p.ESSAY_Q_PATTERN.match("十一、申論題")
        assert m and m.group(1) == "十一"


class TestOptions:
    def test_inline_four_options(self):
        text = "(A) 總統 (B) 立法院 (C) 考試院 (D) 監察院"
        matches = p.INLINE_OPTIONS_PATTERN.findall(text)
        labels = {m[0].upper() for m in matches}
        assert labels == {"A", "B", "C", "D"}

    def test_full_width_paren_options(self):
        text = "（A）甲 （B）乙 （C）丙 （D）丁"
        matches = p.INLINE_OPTIONS_PATTERN.findall(text)
        assert len(matches) == 4


class TestSection:
    def test_section_essay(self):
        m = p.SECTION_PATTERN.match("甲、申論題")
        assert m and m.group(1) == "甲"

    def test_section_choice(self):
        m = p.SECTION_PATTERN.match("乙、測驗題")
        assert m and m.group(2) == "測驗題"


class TestHeaderLine:
    def test_page_number(self):
        assert p.is_header_line("- 1 -")
        assert p.is_header_line("50110")

    def test_subject_line(self):
        assert p.is_header_line("科 目：中華民國憲法")

    def test_real_content_kept(self):
        assert not p.is_header_line("下列何者屬於警察職務?")

    def test_cross_page_markers(self):
        assert p.is_header_line("全九頁")
        assert p.is_header_line("第三頁")
        assert p.is_header_line("第 7 頁")
        assert p.is_header_line("(請接第三頁)")

    def test_appendix_header(self):
        assert p.is_header_line("附表四：F 分配表")
        assert p.is_header_line("Critical values of the f-Distribution")

    def test_repeated_exam_title(self):
        assert p.is_header_line("107年特種考試交通事業鐵路人員")

    def test_option_content_with_exam_keyword_not_header(self):
        # 選項內容含「人員考試」不該被當 header
        assert not p.is_header_line(
            "(D)司法院釋字第760號指出「公務人員特種考試警察人員考試錄取人員訓練計畫」係針對考試筆"
        )

    def test_question_content_with_keyword_not_header(self):
        # 題目本身含「人員考試」也不該被當 header
        assert not p.is_header_line("9 下列關於公務人員考試之敘述,何者正確?")


class TestNoteLine:
    def test_note_keyword(self):
        assert p.is_note_line("注意：禁止使用電子計算器")
        assert p.is_note_line("（一）不必抄題")

    def test_normal_question_not_note(self):
        assert not p.is_note_line("1. 警察的職務為何?")


class TestCjkCollapse:
    def test_basic(self):
        assert p.collapse_spaced_cjk("交 通 事 業") == "交通事業"

    def test_preserve_alpha_gap(self):
        assert p.collapse_spaced_cjk("ABC 通 事") == "ABC 通事"


class TestScorePattern:
    def test_full_width(self):
        assert p.SCORE_PATTERN.search("試說明本案性質。（25 分）")

    def test_half_width(self):
        assert p.SCORE_PATTERN.search("題目 (10 分)")


class TestCnNumber:
    def test_in_range(self):
        assert p.cn_number(0) == "一"
        assert p.cn_number(14) == "十五"

    def test_out_of_range(self):
        assert p.cn_number(15) == "16"


class TestSplitUnmarkedOptions:
    def test_four_chinese_tokens(self):
        out = p.split_unmarked_options("巡邏部署 登檢部署 警戒部署 戰鬥部署")
        assert out == {
            "A": "巡邏部署",
            "B": "登檢部署",
            "C": "警戒部署",
            "D": "戰鬥部署",
        }

    def test_reject_two_tokens(self):
        # 2 個太少
        assert p.split_unmarked_options("甲 乙") is None

    def test_reject_five_tokens(self):
        # 5 個太多（A-D + 1）
        assert p.split_unmarked_options("甲 乙 丙 丁 戊") is None

    def test_reject_too_long(self):
        # 超過 25 字應拒絕
        long_token = "x" * 30
        assert p.split_unmarked_options(f"甲 乙 丙 {long_token}") is None

    def test_reject_with_question_mark(self):
        assert p.split_unmarked_options("甲 乙 丙? 丁") is None

    def test_accept_digits_now(self):
        # MMSI 9 位數選項應該被接受
        out = p.split_unmarked_options("412004523 416002759 533453000 564443000")
        assert out and len(out) == 4

    def test_reject_year_sequence(self):
        # 連續年份序列不該被當選項
        assert p.split_unmarked_options("2018 2019 2020 2021") is None

    def test_accept_three_tokens(self):
        # 3 個選項應接受
        out = p.split_unmarked_options("巡邏 登檢 警戒")
        assert out == {"A": "巡邏", "B": "登檢", "C": "警戒"}

    def test_accept_range_tokens(self):
        out = p.split_unmarked_options("23~27節 22~26節 48~60節 30~40節")
        assert out and len(out) == 4

    def test_accept_long_token(self):
        # 超過原 15 字但 ≤25 字應接受
        out = p.split_unmarked_options(
            "發出求救遇難信號或燈號 緊急下錨避免擱淺 安撫艇員情緒沉著鎮靜 準備求生救生器材設備"
        )
        assert out and len(out) == 4

    def test_accept_multiline(self):
        # 跨行統一視為空白
        out = p.split_unmarked_options("甲 乙\n丙 丁")
        assert out == {"A": "甲", "B": "乙", "C": "丙", "D": "丁"}


class TestSplitUnmarkedByLines:
    def test_four_long_options(self):
        # 偵查法學那種「每行一個長選項」格式
        lines = [
            "毒品係指具有成癮性、濫用性及對社會危害性之麻醉藥品",
            "持有或施用第三級或第四級毒品者施以罰鍰並令其參加毒品危害講習",
            "直轄市、縣（市）政府為執行毒品防制工作，應由專責組織辦理",
            "毒品轉讓之未遂犯負有刑事責任",
        ]
        out = p.split_unmarked_options_by_lines(lines)
        assert out and len(out) == 4
        assert out["D"] == "毒品轉讓之未遂犯負有刑事責任"

    def test_three_lines_ok(self):
        out = p.split_unmarked_options_by_lines(["甲", "乙", "丙"])
        assert out == {"A": "甲", "B": "乙", "C": "丙"}

    def test_two_lines_too_few(self):
        assert p.split_unmarked_options_by_lines(["甲", "乙"]) is None

    def test_five_lines_too_many(self):
        assert p.split_unmarked_options_by_lines(["甲", "乙", "丙", "丁", "戊"]) is None

    def test_reject_with_question_mark(self):
        # 含 ? 表示題幹混入，拒絕
        assert p.split_unmarked_options_by_lines(["甲?", "乙", "丙", "丁"]) is None

    def test_empty_or_too_short(self):
        assert p.split_unmarked_options_by_lines([]) is None
        assert p.split_unmarked_options_by_lines(["甲", "乙", "丙", "丁", ""]) == {
            "A": "甲", "B": "乙", "C": "丙", "D": "丁"
        }

    def test_empty_input(self):
        assert p.split_unmarked_options("") is None
        assert p.split_unmarked_options("   ") is None


class TestPuaReplace:
    def test_options_abcd(self):
        text = "總統 立法院 考試院 監察院"
        out = p.replace_pua_chars(text)
        assert out == "(A)總統 (B)立法院 (C)考試院 (D)監察院"

    def test_bullet_chars(self):
        text = "不必抄題請以"
        out = p.replace_pua_chars(text)
        # bullet 替換為空字串
        assert "" not in out and "" not in out

    def test_empty_input(self):
        assert p.replace_pua_chars("") == ""
        assert p.replace_pua_chars(None) is None

    def test_no_pua_unchanged(self):
        text = "依憲法規定,考試院副院長人選"
        assert p.replace_pua_chars(text) == text

    def test_with_inline_options_pattern(self):
        """確認 PUA 替換後，INLINE_OPTIONS_PATTERN 能抽出選項。"""
        raw = "總統 立法院 考試院 監察院"
        normalized = p.replace_pua_chars(raw)
        matches = p.INLINE_OPTIONS_PATTERN.findall(normalized)
        labels = {m[0].upper() for m in matches}
        assert labels == {"A", "B", "C", "D"}
