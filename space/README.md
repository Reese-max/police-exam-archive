---
title: 警察考古題 AI 助理
emoji: 📚
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 5.50.0
python_version: 3.12.12
app_file: app.py
pinned: false
---

以對話方式查詢考古題與現行法條，支援接續追問，並顯示可展開的檢索來源。
設定 `RAG_LLM_API_KEY` 後提供 AI 回答；未設定時只回傳檢索結果。
主要模型限流或失敗時，設有 `RAG_LLM_FALLBACK_API_KEY` 會改用備用模型。不設定 `RAG_LLM_MAX_PER_HOUR` 即不限每小時次數。
資料未涵蓋而由模型自身知識補充的內容，會由程式加上「未經查證」警語。
AI 回答僅供參考，請以考選部公告與現行條文為準。

啟動前設定 `HF_DATASET_REPO` 為已有 `index-bge-m3.sqlite` 的公開 Dataset。
啟動時匿名下載索引與公開 BGE-M3 權重，不使用 Hugging Face token。
若題目的官方 PDF 尚未解析，介面會顯示「未解析」。

此草案預期使用 `zero-a10g` 託管；檢索模型和 SQLite 查詢仍在 CPU 執行。
標記函式不會被呼叫。實際帳號資格與平台執行狀態須另行驗證。
