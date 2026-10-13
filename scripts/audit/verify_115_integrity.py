#!/usr/bin/env python3
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
                if re.search(r"\b[a-z]{25,}\b", str(value)):
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
        raise SystemExit("115 唯讀稽核失敗（%d 項）：\n- %s" % (len(errors), "\n- ".join(errors)))
    print("115 唯讀稽核通過：13 類科、90 科次、官方清單、題組、membership、前端與治理契約均正確。")


if __name__ == "__main__":
    main()
