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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="A new, non-existing output directory")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    for source, destination in FILES.items():
        target = args.out / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, target)
    print(f"Space 檔案已整理至 {args.out.resolve()}")


if __name__ == "__main__":
    main()
