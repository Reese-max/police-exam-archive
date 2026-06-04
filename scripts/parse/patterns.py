# -*- coding: utf-8 -*-
"""
PDF 解析用的正則與分類模式集中地。
從 pdf_to_questions.py 抽出，便於單元測試與重用。

全形字元一律用 unicode escape 寫，避免 IDE/工具 normalize：
  （ = (    ） = )    、 = 、    ． = .
  分 = 分    ※ = ※    ＊ = *
  CJK 範圍：一-鿿
"""

from __future__ import annotations

import re


# 半形 + 全形括號 char class
_L = "[(（]"  # ( or （
_R = "[)）]"  # ) or ）


# ===== PUA（Private Use Area）字元映射 =====
# 考選部 PDF 字型把 (A)(B)(C)(D) 編碼成 PUA 字元。
# 原本的 archive/fixes/fix_pdf_text_quality.py 是事後修復；
# 整合進 normalize 階段後，原始解析就能直接抽出選項標記。
PUA_MAP = {
    "": "(A)",
    "": "(B)",
    "": "(C)",
    "": "(D)",
    # 裝飾性 bullet 符號（注意事項前的方塊），替成空白避免干擾
    "": "",
    "": "",
    "": "",
    "": "",
}
_PUA_RE = re.compile("[" + "".join(PUA_MAP.keys()) + "]")


def replace_pua_chars(text: str) -> str:
    """把 PDF 字型 PUA 字元替換成可讀標記。"""
    if not text:
        return text
    return _PUA_RE.sub(lambda m: PUA_MAP.get(m.group(0), ""), text)


# ===== 考卷標頭欄位（從文字頭部抽出 metadata）=====
HEADER_PATTERNS = {
    "exam_type": re.compile(r"(\d{2,3})\s*年\s*(特種考試|公務人員特種考試)"),
    "exam_name": re.compile(r"(警察人員考試|一般警察人員考試)"),
    "level": re.compile(r"(三等|四等)考試"),
    "category": re.compile(r"類\s*科[:：]\s*(.+)"),
    "subject": re.compile(r"科\s*目[:：]\s*(.+)"),
    "exam_time": re.compile(r"考試時間[:：]\s*(.+)"),
    "code": re.compile(r"代號[:：]\s*(\d{5})"),
}


# ===== 結構辨識 =====
CHOICE_Q_PATTERN = re.compile(
    # 題號 1-999 後必須是下列之一：
    #   (a) `.、．)` 分隔符 + 後面不接另一個數字（避免 "81、76、79" 數據序列）
    #   (b) 直接接 CJK 字元、中文標點符號（適用「1 依憲法」「2 「樹上...」」等格式）
    #   (c) 直接接至少 3 個英文字母（適用「1 What is...」英文題幹）
    # 並且整行不可為「數字+量詞」表達式（避免「107年」「12浬」「50公尺」被誤判）
    r"^[\s]*"
    r"(?!\d+\s*[年月日歲個位點分時秒浬里份名公])"
    r"(\d{1,3})\s*"
    r"(?:[.、．)](?!\s*\d)|(?=[一-鿿「『《【（〔]|[A-Za-z]{3}))"
    r"\s*(.+)",
    re.DOTALL,
)

OPTION_PATTERN = re.compile(
    _L + r"([A-Da-d])" + _R + r"\s*(.+?)(?=" + _L + r"[A-Da-d]" + _R + r"|$)",
    re.DOTALL,
)

INLINE_OPTIONS_PATTERN = re.compile(
    _L + r"([A-Da-d])" + _R + r"\s*(.+?)(?=\s*" + _L + r"[A-Da-d]" + _R + r"|\s*$)"
)

# 申論題題號：一、 二、 ... 十五、
ESSAY_Q_PATTERN = re.compile(
    r"^[\s]*([一-鿿]+)\s*[、．.]\s*(.+)", re.DOTALL
)
# 但只接受常見中文數字
_CN_NUM_CHARS = set("一二三四五六七八九十")


def match_essay(line: str):
    """嚴格匹配申論題題號（避免一般中文文句被誤判）。"""
    m = ESSAY_Q_PATTERN.match(line)
    if not m:
        return None
    num_str = m.group(1)
    if not all(c in _CN_NUM_CHARS for c in num_str):
        return None
    return m


SECTION_PATTERN = re.compile(
    r"^[\s]*([甲乙])\s*[、．.]\s*(申論題|測驗題|選擇題)"
)

NOTE_PATTERN = re.compile(r"^[\s]*[※＊*]?\s*注意\s*[:：]")

# 含分數標記，例：(25 分)、（25 分） — fallback 申論題偵測
SCORE_PATTERN = re.compile(_L + r"\s*\d+\s*分\s*" + _R)

# 純 5 位數整行（考卷代號）
EXAM_CODE_LINE = re.compile(r"^\d{5}$")


# ===== 應整行剔除的標頭/印刷標記 =====
HEADER_LINE_PATTERNS = [
    re.compile(r"^\d{2,3}年(公務|特種)"),
    re.compile(r"^代號[:：]"),
    re.compile(r"^頁次[:：]"),
    re.compile(r"^考試(別|時間)"),
    re.compile(r"^等\s*別[:：]"),
    re.compile(r"^類\s*科"),
    re.compile(r"^科\s*目[:：]"),
    re.compile(r"^座號"),
    re.compile(r"^(全一張|全一頁)"),
    re.compile(r"^全\s*[一二三四五六七八九十百\d]+\s*頁$"),  # 全九頁、全 12 頁
    re.compile(r"^第\s*[一二三四五六七八九十百\d]+\s*頁$"),  # 第三頁、第 7 頁
    # 頁碼：可能含空白如 "- 1 -"
    re.compile(r"^-?\s*\d+\s*-?$"),
    re.compile(r"^\d{5}$"),
    # 跨頁標記：「(請接背面)」「（請接第三頁）」「請接背面」「（背面）」（裸字 / 半形 / 全形括號）
    re.compile(r"^[（(]?\s*(?:請接|請以)\s*(?:背面|第[一二三四五六七八九十\d]+頁)\s*[）)]?$"),
    re.compile(r"^[（(]\s*背面\s*[）)]$"),
    re.compile(r"^(背面尚有|請翻頁)"),
    re.compile(r"^附表\s*[一二三四五六七八九十\d]+[:：]"),  # 附表四：F 分配表
    re.compile(r"^Critical values"),  # 英文統計表頭
    re.compile(r"^\d{1,3}年特?\s*種?\s*考\s*試"),  # 跨頁標頭「107年特種考試」
]

NOTE_KEYWORDS = (
    "不必抄題",        # 不必抄題
    "不予計分",        # 不予計分
    "禁止使用電子計算器",  # 禁止使用電子計算器
    "本試題為單一選擇題",  # 本試題為單一選擇題
    "鋼筆或原子筆",  # 鋼筆或原子筆
    "2B鉄筆",                  # 2B鉛筆 (用「鉛」/「鐵」常見替換需更寬)
    "2B鉛筆",                  # 2B鉛筆
    "應使用本國文字",  # 應使用本國文字
    "可以使用電子計算器",  # 可以使用電子計算器
)

HEADER_INLINE_KEYWORDS = (
    "人員考試",        # 人員考試
    "考試別",              # 考試別
    "退除役軍人",  # 退除役軍人
)


# ===== 中文編號（fallback 用）=====
CN_NUMS = (
    "一", "二", "三", "四", "五",
    "六", "七", "八", "九", "十",
    "十一", "十二", "十三", "十四", "十五",
)


def is_header_line(line: str) -> bool:
    """整行視為標頭/分頁標記、可剔除。"""
    line = line.strip()
    if not line:
        return True
    for pat in HEADER_LINE_PATTERNS:
        if pat.match(line):
            return True
    # keyword 判定：只在「不是題目樣式行」時套用
    # 題目樣式 = CHOICE_Q 開頭 / (A)(B)(C)(D) 開頭 / 中文數字+、 開頭
    looks_like_question = (
        CHOICE_Q_PATTERN.match(line)
        or re.match(r"^[\s]*[(（][A-Da-d][)）]", line)
        or re.match(r"^[\s]*[一二三四五六七八九十]+\s*[、．.]", line)
    )
    if not looks_like_question:
        if any(kw in line for kw in HEADER_INLINE_KEYWORDS) and len(line) < 80:
            return True
    return False


def is_note_line(line: str) -> bool:
    """注意事項行（會收進 notes 而非 questions）。"""
    line = line.strip()
    return bool(NOTE_PATTERN.match(line)) or any(kw in line for kw in NOTE_KEYWORDS)


def collapse_spaced_cjk(text: str) -> str:
    """移除 CJK 字元間因 PDF 排版產生的多餘空格。例：「交 通 事 業」→「交通事業」。"""
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"([一-鿿])\s+([一-鿿])", r"\1\2", text)
    return text


def cn_number(idx: int) -> str:
    """回傳中文數字（超出範圍則 fallback 阿拉伯數字）。"""
    if 0 <= idx < len(CN_NUMS):
        return CN_NUMS[idx]
    return str(idx + 1)


def split_unmarked_options_by_lines(lines: list[str]) -> dict | None:
    """直接收 N 行（每行一選項）切 ABCD。

    用於：「題幹? \\n 選項1 \\n 選項2 \\n 選項3 \\n 選項4」格式
    （選項各佔一行、可能很長 30-80 字，不適合 token-split 版本）。

    判定：
      * 3 或 4 行
      * 每行非空、不含 ? ? ! !（防誤把題幹當選項）
      * 每行字數 2-200
    """
    if not lines:
        return None
    cleaned = [ln.strip() for ln in lines if ln and ln.strip()]
    if not (3 <= len(cleaned) <= 4):
        return None
    bad_chars = set("?？!！")
    for ln in cleaned:
        if not (1 <= len(ln) <= 200):
            return None
        if any(c in ln for c in bad_chars):
            return None
    return dict(zip("ABCDE"[: len(cleaned)], cleaned))


def split_unmarked_options(
    text: str,
    min_count: int = 3,
    max_count: int = 4,
    max_token_len: int = 25,
) -> dict | None:
    """偵測無 (A)(B)(C)(D) 標記、以空白/換行分隔的選項格式。

    支援三種排版：
      a) 一行四個：「巡邏部署 登檢部署 警戒部署 戰鬥部署」
      b) 兩行各兩個：「發出求救遇難信號或燈號 緊急下錨避免擱淺\n安撫... 準備...」
      c) 純數字 / 範圍符號：「412004523 416002759 533453000 564443000」「23~27節 22~26節 ...」

    判定條件（放寬版）：
      * 跨行統一視為空白分隔
      * 必須切出 min_count..max_count 個 token（預設 3-4）
      * 每個 token 字元數 1-25
      * token 內不含 ? ？ ! ！ ; ； 等句末符號
      * 整段不可全為相近的「年份序列」（4 個連續年份）
    """
    if not text or not text.strip():
        return None

    # 跨行視為空白分隔
    normalized = re.sub(r"\s+", " ", text.strip())
    tokens = [t for t in normalized.split(" ") if t]
    if not (min_count <= len(tokens) <= max_count):
        return None

    bad_chars = set("?？!！;；")
    for t in tokens:
        if len(t) < 1 or len(t) > max_token_len:
            return None
        if any(c in bad_chars for c in t):
            return None

    # 防誤判「年份序列」：tokens 全為 4 位數 + 相鄰差 1 → 拒絕
    if all(re.fullmatch(r"\d{4}", t) for t in tokens):
        nums = [int(t) for t in tokens]
        if all(nums[i + 1] - nums[i] == 1 for i in range(len(nums) - 1)):
            return None

    return dict(zip("ABCDE"[: len(tokens)], tokens))
