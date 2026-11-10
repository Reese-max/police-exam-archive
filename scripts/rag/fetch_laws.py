#!/usr/bin/env python3
"""Build the tracked current-law corpus from the Ministry of Justice open data."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import urllib.request
import zipfile
from urllib.parse import parse_qs, urlencode, urlsplit


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_URL = "https://law.moj.gov.tw/api/Ch/Law/JSON"
ARTICLE_NO = re.compile(r"^(?:第)?(\d+(?:-\d+)*)(?:條)?$")
CHAPTER_NUMBER = re.compile(r"第\s*([0-9一二三四五六七八九十百千〇零]+)\s*(編|章|節|款)")


def read_source(path=None):
    if path is None:
        with urllib.request.urlopen(DEFAULT_SOURCE_URL, timeout=30) as response:
            return json.loads(response.read().decode("utf-8-sig"))
    path = Path(path)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist()
                       if Path(name).name.casefold() == "chlaw.json"]
            if len(members) != 1:
                raise ValueError(f"ZIP 必須包含唯一 ChLaw.json：{path}")
            return json.loads(archive.read(members[0]).decode("utf-8-sig"))
    return json.loads(path.read_text(encoding="utf-8-sig"))


def normalize_article_no(value):
    compact = "".join(str(value or "").split())
    match = ARTICLE_NO.fullmatch(compact)
    if not match:
        raise ValueError(f"無法正規化法條號：{value!r}")
    return f"第{match.group(1)}條"


def article_flno(article_no):
    return article_no[1:-1]


HEADING_LEVEL = re.compile(r"^第\S+?([編章節款目])")


def normalize_chapter(value):
    text = " ".join(str(value or "").split())
    return CHAPTER_NUMBER.sub(r"第\1\2", text)


def law_pcode(law):
    try:
        value = parse_qs(urlsplit(law["LawURL"]).query)["pcode"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"法規缺少有效 pcode：{law.get('LawName')}") from exc
    if not re.fullmatch(r"[A-Za-z0-9]+", value):
        raise ValueError(f"法規 pcode 無效：{law.get('LawName')}")
    return value


def extract_laws(data, names):
    if not isinstance(data, dict) or not isinstance(data.get("Laws"), list):
        raise ValueError("來源格式不符：缺少 Laws 清單")
    by_name = {law.get("LawName"): law for law in data["Laws"] if isinstance(law, dict)}
    missing = [name for name in names if name not in by_name]
    abandoned = [name for name in names
                 if name in by_name and str(by_name[name].get("LawAbandonNote") or "").strip()]
    if missing or abandoned:
        details = []
        if missing:
            details.append("找不到法規：" + "、".join(missing))
        if abandoned:
            details.append("已廢止法規：" + "、".join(abandoned))
        raise ValueError("；".join(details))

    records = []
    law_counts = Counter({name: 0 for name in names})
    for name in names:
        law = by_name[name]
        pcode = law_pcode(law)
        modified = str(law.get("LawModifiedDate") or "")
        if not re.fullmatch(r"\d{8}", modified):
            raise ValueError(f"法規最後修正日期無效：{name}: {modified!r}")
        headings = {}
        chapter = ""
        for article in law.get("LawArticles", []):
            if article.get("ArticleType") == "C":
                # Keep the 編/章/節/款/目 path so a 款 heading does not erase its 編 and 章.
                heading = normalize_chapter(article.get("ArticleContent"))
                level = HEADING_LEVEL.match(heading)
                depth = "編章節款目".index(level.group(1)) if level else 0
                headings = {key: value for key, value in headings.items() if key < depth}
                headings[depth] = heading
                chapter = " ".join(headings[key] for key in sorted(headings))
                continue
            if article.get("ArticleType") != "A":
                continue
            article_no = normalize_article_no(article.get("ArticleNo"))
            content = str(article.get("ArticleContent") or "").replace("\r\n", "\n")
            if " ".join(content.split()) == "（刪除）":
                continue
            flno = article_flno(article_no)
            records.append({
                "id": f"law:{pcode}:{flno}",
                "law_name": name,
                "pcode": pcode,
                "article_no": article_no,
                "chapter": chapter,
                "content": content,
                "law_modified_date": modified,
                "url": "https://law.moj.gov.tw/LawClass/LawSingle.aspx?"
                       + urlencode({"pcode": pcode, "flno": flno}),
            })
            law_counts[name] += 1
    identifiers = [record["id"] for record in records]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("來源包含重複法條識別碼")
    return records, dict(sorted(law_counts.items()))


def write_outputs(records, law_counts, update_date, *, output, meta_output):
    output, meta_output = Path(output), Path(meta_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    meta_output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    summary = {
        "update_date": update_date,
        "law_counts": law_counts,
        "total_articles": len(records),
    }
    meta_output.write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8", newline="\n")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="本機 ChLaw.json 或含 ChLaw.json 的 ZIP")
    parser.add_argument("--list", type=Path, default=ROOT / "rag/law_list.json")
    parser.add_argument("--out", type=Path, default=ROOT / "rag/laws.jsonl")
    parser.add_argument("--meta-out", type=Path, default=ROOT / "rag/laws_meta.json")
    args = parser.parse_args(argv)
    try:
        source = read_source(args.source)
        names = json.loads(args.list.read_text(encoding="utf-8"))
        if (not isinstance(names, list) or not names
                or any(not isinstance(name, str) or not name for name in names)
                or len(names) != len(set(names))):
            raise ValueError("法規清單必須是無重複的名稱陣列")
        records, law_counts = extract_laws(source, names)
        summary = write_outputs(records, law_counts, source.get("UpdateDate"),
                                 output=args.out, meta_output=args.meta_out)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"法規擷取失敗：{exc}\n")
    print(f"資料日期：{summary['update_date']}")
    print(f"法規數：{len(law_counts)}")
    print(f"法條總數：{summary['total_articles']}")


if __name__ == "__main__":
    main()
