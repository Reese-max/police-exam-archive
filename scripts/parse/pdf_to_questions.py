# -*- coding: utf-8 -*-
"""
PDF → 結構化題目提取器（v2，優化版）

新增：
  * 解析併發化（ProcessPoolExecutor + tqdm）
  * 增量 manifest：未變更檔案自動跳過
  * OCR fallback：pdfplumber 抽不到文字時轉 OCR（PyMuPDF + rapidocr）
  * wordninja 修復英文 OCR 斷字

用法:
  python pdf_to_questions.py                     # 處理整個 考古題庫/
  python pdf_to_questions.py --input <dir>       # 指定目錄
  python pdf_to_questions.py --input <pdf>       # 處理單一 PDF
  python pdf_to_questions.py --force             # 忽略 manifest 強制重跑
  python pdf_to_questions.py --workers 8         # 自訂併發數
  python pdf_to_questions.py --no-ocr            # 停用 OCR fallback
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from multiprocessing import cpu_count
from pathlib import Path
from typing import List, Optional

# scripts/parse 內部模組
_THIS = Path(__file__).resolve()
_ROOT = _THIS.parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.parse import patterns as P  # noqa: E402
from scripts.parse.answer_extractor import (  # noqa: E402
    find_answer_pdf,
    merge_answers_into_questions,
    parse_answer_pdf,
)
from scripts.parse.extractors import EXTRACTORS, ExtractorFn, get_extractor  # noqa: E402
from scripts.parse.manifest import ParseManifest  # noqa: E402
from scripts.parse.ocr_fallback import extract_text_with_fallback  # noqa: E402
from scripts.parse.ocr_repair import normalize_with_ocr_repair  # noqa: E402
from scripts.parse.quality import QualityReport, assess_quality  # noqa: E402

# pdfplumber 仍用於 fallback_extract_essays（需 page.extract_words 取 Y 座標）
import pdfplumber  # noqa: E402

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(it, **kw):  # type: ignore
        return it


logger = logging.getLogger(__name__)


CATEGORIES = (
    "行政警察學系", "外事警察學系", "刑事警察學系", "公共安全學系社安組",
    "犯罪防治學系預防組", "犯罪防治學系矯治組", "犯罪防治",
    "消防學系", "交通學系交通組", "交通學系電訊組", "交通警察",
    "資訊管理學系", "鑑識科學學系", "國境警察學系境管組",
    "水上警察學系", "法律學系", "行政管理學系",
)


# ============================================================
# 文字抽取（預設 PyMuPDF + OCR fallback）
# ============================================================
def extract_pdf_text(
    pdf_path: Path,
    enable_ocr: bool = True,
    extractor: ExtractorFn | None = None,
) -> tuple[List[str], bool]:
    """抽 PDF 文字，必要時走 OCR fallback。回傳 (pages_text, used_ocr)。

    Args:
        pdf_path: PDF 路徑
        enable_ocr: 是否啟用 OCR fallback
        extractor: 主抽器 callable；None 則用預設（PyMuPDF）
    """
    extractor = extractor or get_extractor("pymupdf")
    return extract_text_with_fallback(pdf_path, extractor, enable_ocr=enable_ocr)


# ============================================================
# 解析
# ============================================================
@dataclass
class ParseResult:
    metadata: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    sections: list = field(default_factory=list)
    questions: list = field(default_factory=list)
    year: Optional[int] = None
    category: Optional[str] = None
    subject: Optional[str] = None
    source_pdf: Optional[str] = None
    file_type: Optional[str] = None
    used_ocr: bool = False

    def to_dict(self) -> dict:
        d = {
            "metadata": self.metadata,
            "notes": self.notes,
            "sections": self.sections,
            "questions": self.questions,
        }
        for k in ("year", "category", "subject", "source_pdf", "file_type"):
            v = getattr(self, k)
            if v is not None:
                d[k] = v
        if self.used_ocr:
            d["used_ocr"] = True
        return d


def parse_metadata(text: str) -> dict:
    metadata = {}
    head = text[:500]
    for key, pattern in P.HEADER_PATTERNS.items():
        m = pattern.search(head)
        if m:
            metadata[key] = m.group(1) if m.lastindex else m.group(0)
    return metadata


def parse_questions(pages_text: List[str]) -> dict:
    # 先把 PUA 字元（）替換為 (A)(B)(C)(D)，讓後續解析能認出選項
    pages_text = [P.replace_pua_chars(p) for p in pages_text]
    full_text = "\n".join(pages_text)
    metadata = parse_metadata(full_text)

    # 第一輪：分離 notes / content
    content_lines: list[str] = []
    notes: list[str] = []
    in_note = False

    for page_text in pages_text:
        for line in page_text.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if P.is_header_line(stripped):
                continue
            if P.is_note_line(stripped):
                notes.append(stripped)
                in_note = True
                continue
            if (
                in_note
                and not P.CHOICE_Q_PATTERN.match(stripped)
                and not P.match_essay(stripped)
                and not P.SECTION_PATTERN.match(stripped)
            ):
                notes.append(stripped)
                continue
            in_note = False
            content_lines.append(stripped)

    # 第二輪：解析題目結構
    questions: list[dict] = []
    sections: list[str] = []
    current_section: Optional[str] = None

    i = 0
    while i < len(content_lines):
        line = content_lines[i]

        # 分段
        sec = P.SECTION_PATTERN.match(line)
        if sec:
            current_section = f"{sec.group(1)}、{sec.group(2)}"
            sections.append(current_section)
            i += 1
            continue

        # 申論題
        essay = P.match_essay(line)
        if essay:
            num_str = essay.group(1)
            stem = essay.group(2).strip()
            i += 1
            while i < len(content_lines):
                nxt = content_lines[i]
                if (
                    P.match_essay(nxt)
                    or P.CHOICE_Q_PATTERN.match(nxt)
                    or P.SECTION_PATTERN.match(nxt)
                ):
                    break
                stem += "\n" + nxt
                i += 1
            questions.append({
                "number": num_str,
                "type": "essay",
                "stem": normalize_with_ocr_repair(stem),
                "section": current_section,
            })
            continue

        # 選擇題
        choice = P.CHOICE_Q_PATTERN.match(line)
        if choice:
            num = int(choice.group(1))
            stem_lines: list[str] = [choice.group(2).strip()]
            unmarked_lines: list[str] = []  # 題幹 ? 後續行（可能是 unmarked options）
            stem_ended = any(c in stem_lines[0] for c in "?？")
            i += 1
            options_text = ""
            in_options_block = False
            while i < len(content_lines):
                nxt = content_lines[i]
                if (
                    P.CHOICE_Q_PATTERN.match(nxt)
                    or P.match_essay(nxt)
                    or P.SECTION_PATTERN.match(nxt)
                ):
                    break
                if re.match(r"\s*[(（][A-Da-d][)）]", nxt):
                    options_text += " " + nxt
                    in_options_block = True
                elif in_options_block:
                    options_text += " " + nxt
                elif stem_ended:
                    # 題幹 ? 結尾後的行視為 unmarked options 候選
                    unmarked_lines.append(nxt)
                else:
                    stem_lines.append(nxt)
                    if any(c in nxt for c in "?？"):
                        stem_ended = True
                i += 1

            options: dict[str, str] = {}
            if options_text:
                for label, text in P.INLINE_OPTIONS_PATTERN.findall(options_text):
                    options[label.upper()] = normalize_with_ocr_repair(text.strip())

            # 嘗試從 unmarked_lines 切 ABCD（每行一選項版本，適合長選項）
            if not options and unmarked_lines:
                unmarked = P.split_unmarked_options_by_lines(unmarked_lines)
                if unmarked:
                    options = {
                        k: normalize_with_ocr_repair(v)
                        for k, v in unmarked.items()
                    }

            # 仍無 options：試 token-split 版（4 個短語並排在 stem_lines 末尾）
            if not options and len(stem_lines) >= 2:
                for n in range(min(3, len(stem_lines) - 1), 0, -1):
                    tail = " ".join(stem_lines[-n:])
                    unmarked = P.split_unmarked_options(tail)
                    if unmarked:
                        options = {
                            k: normalize_with_ocr_repair(v)
                            for k, v in unmarked.items()
                        }
                        stem_lines = stem_lines[:-n]
                        break

            # 仍無 options 但 unmarked_lines 有資料 → 至少當作備援放回 stem
            if not options and unmarked_lines:
                stem_lines.extend(unmarked_lines)

            stem = " ".join(stem_lines)

            if not options:
                # 嘗試從題幹末尾抽選項
                first_opt_pos = max(stem.find("(A)"), stem.find("（A）"))
                if first_opt_pos > 0:
                    options_part = stem[first_opt_pos:]
                    stem = stem[:first_opt_pos].strip()
                    for label, text in P.INLINE_OPTIONS_PATTERN.findall(options_part):
                        options[label.upper()] = normalize_with_ocr_repair(text.strip())

            q = {
                "number": num,
                "type": "choice",
                "stem": normalize_with_ocr_repair(stem),
                "section": current_section,
            }
            if options:
                q["options"] = options
            questions.append(q)
            continue

        i += 1

    return {
        "metadata": metadata,
        "notes": notes,
        "sections": sections,
        "questions": questions,
    }


# ============================================================
# Fallback：Y 座標間距偵測純申論題
# ============================================================
def fallback_extract_essays(pdf_path: Path) -> list[dict]:
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            all_lines: list[tuple[float, str]] = []
            page_offset = 0.0
            for page in pdf.pages:
                words = page.extract_words(y_tolerance=3)
                if not words:
                    continue
                current = [words[0]]
                for w in words[1:]:
                    if abs(w["top"] - current[-1]["top"]) < 5:
                        current.append(w)
                    else:
                        text = " ".join(cw["text"] for cw in current)
                        all_lines.append(
                            (page_offset + current[0]["top"], text)
                        )
                        current = [w]
                if current:
                    text = " ".join(cw["text"] for cw in current)
                    all_lines.append((page_offset + current[0]["top"], text))
                page_offset += page.height
    except Exception:
        return []

    if not all_lines:
        return []

    filtered = [
        (y, t)
        for y, t in all_lines
        if not P.is_header_line(P.collapse_spaced_cjk(t))
        and not P.is_note_line(P.collapse_spaced_cjk(t))
    ]
    if not filtered:
        return []

    gaps = [filtered[i][0] - filtered[i - 1][0] for i in range(1, len(filtered))]
    if gaps:
        sg = sorted(gaps)
        threshold = max(sg[len(sg) // 2] * 1.5, 30)
    else:
        threshold = 30

    paragraphs = [[filtered[0][1]]]
    for i in range(1, len(filtered)):
        gap = filtered[i][0] - filtered[i - 1][0]
        if gap > threshold:
            paragraphs.append([])
        paragraphs[-1].append(filtered[i][1])

    questions = []
    for para in paragraphs:
        stem = normalize_with_ocr_repair("\n".join(para))
        if stem and P.SCORE_PATTERN.search(stem):
            questions.append({
                "number": P.cn_number(len(questions)),
                "type": "essay",
                "stem": stem,
                "section": None,
            })
    return questions


# ============================================================
# 單檔處理
# ============================================================
def _infer_year_category(pdf_path: Path) -> tuple[Optional[int], Optional[str]]:
    year, category = None, None
    parts = pdf_path.parts
    for i, part in enumerate(parts):
        if re.match(r"\d{3}年$", part):
            try:
                year = int(part.replace("年", ""))
            except ValueError:
                pass
        if i > 0 and any(c in parts[i - 1] for c in CATEGORIES):
            category = parts[i - 1]
    return year, category


def _try_parse(
    pdf_path: Path,
    extractor_name: str,
    enable_ocr: bool,
    force_ocr: bool = False,
) -> tuple[Optional[dict], bool, Optional[str]]:
    """嘗試用指定 extractor 解析。回 (result, used_ocr, error)。

    Args:
        force_ocr: 強制 OCR（跳過 needs_ocr 判斷，給最後 retry 用）
    """
    try:
        if force_ocr:
            from scripts.parse.ocr_fallback import ocr_pdf_pages
            pages_text = ocr_pdf_pages(pdf_path)
            used_ocr = True
        else:
            pages_text, used_ocr = extract_pdf_text(
                pdf_path,
                enable_ocr=enable_ocr,
                extractor=get_extractor(extractor_name),
            )
    except Exception as e:
        return None, False, f"extract_failed: {e}"

    if not pages_text:
        return None, False, "no_text"

    result = parse_questions(pages_text)
    if not result.get("questions"):
        fb = fallback_extract_essays(pdf_path)
        if fb:
            result["questions"] = fb
    return result, used_ocr, None


def process_single_pdf(
    pdf_path: Path,
    output_dir: Optional[Path] = None,
    enable_ocr: bool = True,
    extractor_name: str = "pdfplumber",
    auto_retry: bool = True,
    quality_threshold: float = 0.7,
    retry_extractors: tuple = ("pymupdf-columns",),
) -> Optional[dict]:
    """處理單一 PDF，回傳結果 dict（含 used_ocr / quality）；失敗回 None。

    Retry 策略順序：
      1. extractor_name（預設 pdfplumber）+ 不啟用 OCR
      2. retry_extractors 內每個 extractor + 不啟用 OCR
      3. extractor_name + 強制 OCR fallback（救純圖文 PDF）
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return None

    # 第一次嘗試（不強制 OCR）
    result, used_ocr, err = _try_parse(pdf_path, extractor_name, enable_ocr=False)
    best_result = result
    best_used_ocr = used_ocr
    best_quality = assess_quality(result) if result else QualityReport(score=0.0)
    strategies_tried = [extractor_name]

    # quality 太低 → retry 其他 extractor（仍不 OCR）
    if auto_retry and not best_quality.is_good(quality_threshold):
        for retry_ext in retry_extractors:
            if retry_ext == extractor_name:
                continue
            strategies_tried.append(retry_ext)
            r, ocr, _ = _try_parse(pdf_path, retry_ext, enable_ocr=False)
            if not r:
                continue
            q = assess_quality(r)
            if q.score > best_quality.score:
                best_result = r
                best_used_ocr = ocr
                best_quality = q
            if best_quality.is_good(quality_threshold):
                break

    # 仍 quality 低且允許 OCR → 強制 OCR 再試（救純圖文 PDF）
    if (
        auto_retry
        and enable_ocr
        and not best_quality.is_good(quality_threshold)
    ):
        strategies_tried.append("force_ocr")
        r, ocr, _ = _try_parse(
            pdf_path, extractor_name, enable_ocr=True, force_ocr=True
        )
        if r:
            q = assess_quality(r)
            if q.score > best_quality.score:
                best_result = r
                best_used_ocr = ocr
                best_quality = q

    result = best_result
    used_ocr = best_used_ocr
    if not result:
        logger.warning(f"PDF 解析全失敗 {pdf_path.name}: {err}")
        return None

    year, category = _infer_year_category(pdf_path)
    if year is not None:
        result["year"] = year
    if category:
        result["category"] = category
    result["subject"] = pdf_path.parent.name
    result["source_pdf"] = str(pdf_path)
    result["file_type"] = pdf_path.stem
    if used_ocr:
        result["used_ocr"] = True

    # 合併同目錄答案 PDF（更正答案優先）
    answer_pdf = find_answer_pdf(pdf_path, prefer_corrected=True)
    if answer_pdf:
        answers = parse_answer_pdf(answer_pdf)
        if answers:
            merged = merge_answers_into_questions(result["questions"], answers)
            result["_answer_source"] = answer_pdf.name
            result["_answers_merged"] = merged

    # 寫入 quality 摘要（給 audit / 增量重跑用）
    result["_quality"] = {
        "score": round(best_quality.score, 3),
        "issues": best_quality.issues,
        "strategies_tried": strategies_tried,
    }

    out_dir = Path(output_dir) if output_dir else pdf_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{pdf_path.stem}.json"

    # 寫入 JSON 時把 _quality 一起寫但放最後（保持 backward compat）
    payload = {k: v for k, v in result.items() if not k.startswith("_")}
    payload["_quality"] = result["_quality"]
    if "_answer_source" in result:
        payload["_answer_source"] = result["_answer_source"]
        payload["_answers_merged"] = result["_answers_merged"]
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    result["_output_json"] = str(json_path)
    return result


def _worker(args: tuple) -> tuple[str, Optional[dict], Optional[str]]:
    """ProcessPool worker — 回 (pdf_path, result, error)。"""
    pdf_path, output_dir, enable_ocr, extractor_name, quality_threshold = args
    try:
        result = process_single_pdf(
            Path(pdf_path), output_dir, enable_ocr, extractor_name,
            quality_threshold=quality_threshold,
        )
        return pdf_path, result, None
    except Exception as e:
        return pdf_path, None, str(e)


# ============================================================
# 目錄處理（併發）
# ============================================================
def process_directory(
    input_dir: Path,
    output_dir: Optional[Path] = None,
    workers: Optional[int] = None,
    force: bool = False,
    enable_ocr: bool = True,
    manifest_path: Optional[Path] = None,
    extractor_name: str = "pdfplumber",
    quality_threshold: float = 0.7,
) -> dict:
    input_dir = Path(input_dir)
    if not input_dir.exists():
        print(f"目錄不存在: {input_dir}")
        return {}

    pdf_files = sorted(input_dir.rglob("試題.pdf"))
    if not pdf_files:
        pdf_files = sorted(input_dir.rglob("*.pdf"))

    print(f"找到 {len(pdf_files)} 個 PDF")

    manifest_path = manifest_path or (_ROOT / "cache" / "parse_manifest.json")
    manifest = ParseManifest(manifest_path)

    # 過濾出真正需要處理的檔案
    tasks: list[tuple] = []
    skipped = 0
    for pdf in pdf_files:
        if not force and manifest.is_unchanged(pdf):
            skipped += 1
            continue
        if output_dir:
            try:
                rel = pdf.relative_to(input_dir)
                out = Path(output_dir) / rel.parent
            except ValueError:
                out = Path(output_dir)
        else:
            out = None
        tasks.append((
            str(pdf), str(out) if out else None,
            enable_ocr, extractor_name, quality_threshold,
        ))

    print(f"  跳過（manifest 命中）: {skipped}")
    print(f"  需處理: {len(tasks)}")

    stats = {
        "total_pdfs": len(pdf_files),
        "skipped": skipped,
        "processed": 0,
        "failed": 0,
        "ocr_used": 0,
        "suspicious": 0,
        "total_questions": 0,
        "choice_questions": 0,
        "essay_questions": 0,
    }
    problematic: list[dict] = []

    if not tasks:
        print("無需處理。")
        return stats

    workers = workers or max(1, min(cpu_count(), 8))
    print(f"  併發 worker: {workers}")
    print("-" * 60)

    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_worker, t): t[0] for t in tasks}
        with tqdm(total=len(tasks), desc="解析中", unit="pdf") as pbar:
            for fut in as_completed(futures):
                pdf_path, result, error = fut.result()
                pdf_p = Path(pdf_path)

                if error or not result:
                    stats["failed"] += 1
                    logger.warning(f"失敗 {pdf_p.name}: {error}")
                elif not result.get("questions"):
                    stats["failed"] += 1
                else:
                    stats["processed"] += 1
                    qs = result["questions"]
                    stats["total_questions"] += len(qs)
                    stats["choice_questions"] += sum(
                        1 for q in qs if q["type"] == "choice"
                    )
                    stats["essay_questions"] += sum(
                        1 for q in qs if q["type"] == "essay"
                    )
                    if result.get("used_ocr"):
                        stats["ocr_used"] += 1

                    quality = result.get("_quality") or {}
                    score = quality.get("score", 1.0)
                    if score < quality_threshold:
                        stats["suspicious"] += 1
                        problematic.append({
                            "pdf": str(pdf_p),
                            "score": score,
                            "issues": quality.get("issues", []),
                            "strategies_tried": quality.get("strategies_tried", []),
                            "questions": len(qs),
                            "used_ocr": bool(result.get("used_ocr")),
                        })

                    out_json = result.get("_output_json")
                    if out_json:
                        manifest.record(
                            pdf_p,
                            Path(out_json),
                            questions=len(qs),
                            used_ocr=bool(result.get("used_ocr")),
                        )
                pbar.update(1)

    manifest.save()

    print("\n" + "=" * 60)
    print("提取完成")
    print("=" * 60)
    for k, v in stats.items():
        print(f"  {k}: {v}")

    base = output_dir or input_dir
    stats_path = base / "extraction_stats.json"
    stats["timestamp"] = datetime.now().isoformat()
    Path(stats_path).write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"統計報告: {stats_path}")

    if problematic:
        # 依分數低 → 高排序，方便先處理最爛的
        problematic.sort(key=lambda x: x["score"])
        prob_path = base / "problematic_pdfs.json"
        Path(prob_path).write_text(
            json.dumps(
                {
                    "timestamp": stats["timestamp"],
                    "threshold": quality_threshold,
                    "count": len(problematic),
                    "items": problematic,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"可疑檔案清單: {prob_path}（共 {len(problematic)} 個低品質 PDF）")

    return stats


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="PDF → 結構化題目提取器")
    parser.add_argument(
        "--input", "-i",
        default=os.path.join(os.path.dirname(__file__), "考古題庫"),
        help="輸入路徑（PDF 檔案或目錄）",
    )
    parser.add_argument("--output", "-o", default=None, help="輸出目錄")
    parser.add_argument(
        "--workers", "-w", type=int, default=None,
        help="併發 worker 數（預設 min(cpu_count, 8)）",
    )
    parser.add_argument(
        "--force", "-f", action="store_true",
        help="忽略 manifest 強制重跑所有 PDF",
    )
    parser.add_argument(
        "--no-ocr", action="store_true",
        help="停用 OCR fallback（只用主抽器）",
    )
    parser.add_argument(
        "--extractor", "-e",
        choices=list(EXTRACTORS.keys()),
        default="pdfplumber",
        help=(
            "主文字抽取器："
            "pdfplumber（預設，分欄處理最穩）/ "
            "pymupdf（最快但不支援雙欄）/ "
            "pymupdf-columns（PyMuPDF + 雙欄重組，仍在實驗）/ "
            "pymupdf4llm"
        ),
    )
    parser.add_argument(
        "--manifest", default=None,
        help="自訂 manifest 檔案路徑",
    )
    parser.add_argument(
        "--quality-threshold", type=float, default=0.7,
        help="品質門檻（0~1）。低於此分視為 suspicious 並 retry。預設 0.7",
    )
    parser.add_argument(
        "--no-retry", action="store_true",
        help="停用 quality 低時自動 retry 其他 extractor",
    )
    parser.add_argument(
        "--log-level", default="WARNING",
        help="日誌等級 (DEBUG/INFO/WARNING/ERROR)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.WARNING),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    input_path = Path(args.input)
    print("=" * 60)
    print("  PDF → 結構化題目提取器 (v2)")
    print("=" * 60)

    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        result = process_single_pdf(
            input_path,
            Path(args.output) if args.output else None,
            enable_ocr=not args.no_ocr,
            extractor_name=args.extractor,
            auto_retry=not args.no_retry,
            quality_threshold=args.quality_threshold,
        )
        if result:
            q = result.get("_quality", {})
            print(
                f"完成: {len(result.get('questions', []))} 題"
                f" (OCR: {result.get('used_ocr', False)},"
                f" quality: {q.get('score', '?')},"
                f" issues: {q.get('issues', [])})"
            )
    elif input_path.is_dir():
        process_directory(
            input_path,
            Path(args.output) if args.output else None,
            workers=args.workers,
            force=args.force,
            enable_ocr=not args.no_ocr,
            manifest_path=Path(args.manifest) if args.manifest else None,
            extractor_name=args.extractor,
            quality_threshold=args.quality_threshold,
        )
    else:
        print(f"無效的輸入路徑: {input_path}")


if __name__ == "__main__":
    main()
