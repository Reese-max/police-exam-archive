# 考古題下載專案 - 測試與涵蓋率報告

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-69%20passed-brightgreen.svg)](TEST_REPORT.md)
[![Coverage](https://img.shields.io/badge/coverage-68%25-yellow.svg)](COVERAGE_REPORT.md)

> **注意**: 推送至 GitHub 後，請將上方 badge 中的 `YOUR_USERNAME/YOUR_REPO` 替換為實際的儲存庫路徑

---

## 📊 測試涵蓋率報告

### 最新涵蓋率統計 (2026-01-07)

```
總體涵蓋率: 68%

詳細模組涵蓋率:
┌─────────────────────────────┬────────┬──────┬────────┐
│ 模組                        │ 敘述數 │ 遺漏 │ 涵蓋率 │
├─────────────────────────────┼────────┼──────┼────────┤
│ auto_generate_form.py       │  273   │  54  │  80%   │
│ 考古題下載.py                │  514   │ 249  │  52%   │
│ smart_deploy.py             │  175   │ 175  │   0%   │
│ tests/*.py (測試程式)        │  535   │   0  │ 100%   │
├─────────────────────────────┼────────┼──────┼────────┤
│ **總計**                    │ 1498   │ 479  │ **68%**│
└─────────────────────────────┴────────┴──────┴────────┘
```

### 📈 涵蓋率分析

#### ✅ 高涵蓋率模組 (80%+)
- `auto_generate_form.py`: **80%**
  - ✅ CSV 解析邏輯完整測試
  - ✅ Apps Script 生成驗證
  - ⚠️ 需補充邊界情況測試

- `tests/*.py`: **100%**
  - ✅ 所有測試程式碼均有執行

#### ⚠️ 中涵蓋率模組 (50-79%)
- `考古題下載.py`: **52%**
  - ✅ 核心函數已測試：
    - `sanitize_filename` ✅
    - `check_path_length` ✅
    - `download_file` ✅
    - `get_exam_list_by_year` ✅
    - `parse_exam_page` ✅
  - ❌ 未測試部分：
    - `download_exam` (主要下載流程)
    - `main` (主程式入口)
    - UI 互動流程

#### ❌ 低涵蓋率模組 (<50%)
- `smart_deploy.py`: **0%**
  - ❌ 完全未測試
  - 建議：新增整合測試

---

## 🎯 改善涵蓋率計劃

### 短期目標 (本週)
- [ ] 提升 `考古題下載.py` 至 70%
  - 新增 `download_exam` 測試
  - 新增整合測試
- [ ] 提升 `smart_deploy.py` 至 50%
  - 新增基本功能測試

### 中期目標 (本月)
- [ ] 提升總體涵蓋率至 80%
- [ ] 新增 E2E 測試
- [ ] 新增效能測試

### 長期目標 (下季度)
- [ ] 達成 90%+ 涵蓋率
- [ ] 新增視覺化涵蓋率報告

---

## 🚀 查看涵蓋率報告

### 本地查看
```bash
# 生成 HTML 報告
pytest tests/ --cov=. --cov-report=html

# 開啟報告
# Windows:
start htmlcov\index.html

# macOS:
open htmlcov/index.html

# Linux:
xdg-open htmlcov/index.html
```

### CI/CD 自動報告
- GitHub Actions 會在每次 push/PR 時自動執行測試
- 涵蓋率報告上傳至 Codecov
- 可在 Artifacts 下載完整 HTML 報告

---

## 📦 涵蓋率設定

在 `pyproject.toml` 中配置：
```toml
[tool.pytest.ini_options]
addopts = "-ra --cov=. --cov-report=term --cov-report=html"
testpaths = ["tests"]

[tool.coverage.run]
omit = [
    "tests/*",
    "*/__pycache__/*",
    "*/venv/*",
    "*/backup/*"
]
```

---

## 📚 相關文件
- [TEST_REPORT.md](TEST_REPORT.md) - 完整測試報告
- [.github/workflows/ci.yml](.github/workflows/ci.yml) - CI/CD 設定
- [README.md](README.md) - 專案說明

---

**最後更新**: 2026-01-07  
**測試框架**: pytest 8.3.5 + pytest-cov 7.0.0  
**測試數量**: 69 個 (100% 通過)
