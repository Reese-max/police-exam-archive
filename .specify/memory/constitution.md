# 專案憲章

> 本憲章定義「CSV → Google Forms 自動化」專案在 GitHub 上的規範。所有 Vibe Coding 迭代、Spec、Plan、Tasks 皆需符合下列原則。

## 核心原則

### 原則 1: CSV 單一真實來源

- **規範類型**: MUST  
- **說明**: 題庫資料只能來自受控 CSV；不得直接編輯產生出的 Apps Script。  
- **適用範圍**: CSV 驗證、Script 生成、部署。  
- **檢查標準**:
  - [ ] 任何表單異動皆有對應 CSV diff 與工具再跑紀錄。
  - [ ] `auto_generate_form.py` 的輸出帶有時間戳與來源檔案欄位。

### 原則 2: 自動化優先

- **規範類型**: MUST  
- **說明**: 每次部署都必須透過 CLI + CLASP 完成；不得在 UI 內手動重複操作。  
- **適用範圍**: Python 腳本、CLASP 指令、Apps Script 專案。  
- **檢查標準**:
  - [ ] README 或 `google_forms_setup_guide.md` 內指示的自動化步驟完整。
  - [ ] CLASP push/run 的輸出與 `form_generation_summary.json` 一起留存。

### 原則 3: 可觀測與可回溯

- **規範類型**: MUST  
- **說明**: 每次匯入需有統計報告、log 與 QA 清單，確保錯誤可追蹤。  
- **適用範圍**: Python 報告、Apps Script logs、檢查清單。  
- **檢查標準**:
  - [ ] `form_generation_summary.json` 含來源、題數、警告。
  - [ ] CLASP logs 連同 Google Drive 連結寫入 QA 報告或 issue。

### 原則 4: 安全存取與最小權限

- **規範類型**: SHOULD  
- **說明**: 使用專用 Google 帳號、standalone Apps Script 專案，避免洩漏題目。  
- **適用範圍**: Google OAuth、CLASP token、Git 版本控管。  
- **檢查標準**:
  - [ ] `.clasp.json` 不含敏感認證，只保留 scriptId。
  - [ ] `README`、Spec、Plan 清楚說明需使用專案帳號及 Drive 權限設定。

## 技術標準

- **語言/框架**: Python 3.10+（資料處理）、Google Apps Script（表單邏輯）、Node 18+（CLASP）。  
- **依賴**: `@google/clasp`, `python-dotenv`（如後續需要），標準庫。  
- **程式碼風格**: PEP 8 + type hints；Apps Script 遵循 Google Style Guide。  
- **測試/品質**:
  - Python 資料處理函式須有單元測試（pytest）。  
  - 關鍵函式需有 docstring；複雜區段補充註解。  
  - 每次 CLI 執行需輸出結果摘要與非 0 返回碼處理。

## 開發流程

1. **/speckit.constitution**：設定或更新本憲章。  
2. **/speckit.specify**：在 `.specify/features/<feature>/spec.md` 描述需求及驗收。  
3. **/speckit.plan**：撰寫同路徑 `plan.md`，定義架構、里程碑、風險。  
4. **/speckit.tasks**：拆解成 `tasks.md`，詳列檔案、驗收、測試。  
5. **/speckit.analyze**（未來擴充）：交叉檢查一致性。  
6. **實作與發布**：分支開發 → PR → CI（格式檢查/pytest）→ CLASP 驗證 → Release。

每個階段都必須：
- [ ] 確認遵守所有 MUST 原則。  
- [ ] 紀錄例外與技術負債。  
- [ ] 附上可測試的驗收標準。

## 文件與紀錄

- **必備文件**: `README.md`, `auto_generate_form.py` docstrings, `google_forms_setup_guide.md`, Spec/Plan/Tasks。  
- **輸出紀錄**: `form_generation_summary.json`, CLASP logs 截圖或貼上, QA 勾選紀錄。  
- **版本策略**: Semantic Versioning (Major.Minor.Patch) 反映工具 CLI 行為變更。

## 版本控制與發布

- **Git 流程**: GitHub Flow；feature branch 需至少 1 人審查。  
- **提交訊息**: 建議 Conventional Commits（feat:, fix:, docs:）。  
- **發布條件**:
  - README/指南同步更新。  
  - `form_generation_summary.json` schema 不破壞相容性或另附遷移。  
  - CLASP 測試帳號已跑過完整流程，並在 issue/PR 留下表單 URL。

## 變更管理

- 憲章修改必須透過 PR，並在 `變更歷史` 區段記錄。  
- 若需求需暫時違反憲章，需於 `spec.md` 記錄理由與補償措施。  
- 重大需求變更→更新 spec/plan/tasks，同步在 `README` 或 `docs/` 內公告。

---

**最後更新**: 2025-11-26  
**版本**: 1.0.0
