#!/usr/bin/env python3
"""Create a self-contained Space directory without uploading it."""

import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
FILES = {
    "space/app.py": "app.py",
    "space/README.md": "README.md",
    "space/requirements.txt": "requirements.txt",
    "scripts/rag/query.py": "scripts/rag/query.py",
    "scripts/rag/answer.py": "scripts/rag/answer.py",
    "scripts/rag/retrieval.py": "scripts/rag/retrieval.py",
    "scripts/rag/model_identity.py": "scripts/rag/model_identity.py",
    "scripts/rag/build_corpus.py": "scripts/rag/build_corpus.py",
    "rag/bench_report.json": "rag/bench_report.json",
    "rag/abbreviations.json": "rag/abbreviations.json",
}


def _copy_frontend(out):
    source = ROOT / "space/web/dist"
    if not (source / "index.html").is_file():
        print("未包含前端 build")
        return False
    destination = out / "web" / "dist"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    print(f"已包含前端 build：{destination}")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="A new, non-existing output directory")
    parser.add_argument("--essay-mcp", type=Path, help="A built essay MCP project directory")
    args = parser.parse_args()
    if args.essay_mcp and not (args.essay_mcp / "dist" / "src" / "index.js").is_file():
        parser.error(f"申論 MCP 目錄缺少 dist/src/index.js：{args.essay_mcp}")
    args.out.mkdir(parents=True, exist_ok=False)
    for source, destination in FILES.items():
        target = args.out / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, target)
    _copy_frontend(args.out)
    if args.essay_mcp:
        for relative in ("dist/src", "templates", "assets"):
            shutil.copytree(args.essay_mcp / relative, args.out / "essay-mcp" / relative)
        for name in ("package.json", "package-lock.json"):
            shutil.copy2(args.essay_mcp / name, args.out / "essay-mcp" / name)
        (args.out / "packages.txt").write_text("fonts-noto-cjk\n", encoding="utf-8")
    print(f"Space 檔案已整理至 {args.out.resolve()}")


if __name__ == "__main__":
    main()
