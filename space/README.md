---
title: 警察考古題檢索
emoji: 📚
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 5.50.0
python_version: 3.11
app_file: app.py
suggested_hardware: cpu-basic
pinned: false
---

輸入問題，檢索前五筆相關考古題，並顯示科目、年度、題號與已解析的考選部原始 PDF。
本介面只做檢索，不呼叫大型語言模型。

啟動前設定 `HF_DATASET_REPO` 為已有 `index-bge-m3.sqlite` 的公開 Dataset。
啟動時匿名下載索引與公開 BGE-M3 權重，不使用 Hugging Face token。
若題目的官方 PDF 尚未解析，介面會顯示「未解析」。
