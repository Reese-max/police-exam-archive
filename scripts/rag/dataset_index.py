#!/usr/bin/env python3
"""Download or publish a versioned index and catalog in an existing public dataset."""

import argparse
import json
import os
from pathlib import Path

FILES = ("index-bge-m3.sqlite", "moex_catalog.json")


def download(repo, folder):
    from huggingface_hub import HfApi, hf_hub_download

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    revision = HfApi(token=False).repo_info(repo, repo_type="dataset", token=False).sha
    for filename in FILES:
        hf_hub_download(repo, filename, repo_type="dataset", revision=revision,
                        local_dir=folder, token=False)
    (folder / ".base-revision.json").write_text(
        json.dumps({"repo": repo, "revision": revision}), encoding="utf-8")
    print(f"已下載 dataset revision {revision}")


def publish(repo, folder, report):
    from huggingface_hub import HfApi

    folder = Path(folder)
    result = json.loads(Path(report).read_text(encoding="utf-8"))
    if not result["index_changed"] and not result["catalog_changed"]:
        print("索引及目錄均無變更；不執行上傳")
        return
    receipt = json.loads((folder / ".base-revision.json").read_text(encoding="utf-8"))
    if receipt["repo"] != repo:
        raise ValueError("下載與上傳的 dataset 不同")
    token = os.environ.get("HF_DATASET_TOKEN")
    if not token:
        raise ValueError("缺少 HF_DATASET_TOKEN")
    HfApi(token=token).upload_folder(
        repo_id=repo, repo_type="dataset", folder_path=folder,
        allow_patterns=list(FILES), parent_commit=receipt["revision"],
        commit_message="Update exam retrieval index")
    print("已上傳更新後的索引與目錄")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("download", "publish"))
    parser.add_argument("--repo", required=True)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.action == "download":
        download(args.repo, args.folder)
    else:
        if not args.report:
            parser.error("publish requires --report")
        publish(args.repo, args.folder, args.report)


if __name__ == "__main__":
    main()
