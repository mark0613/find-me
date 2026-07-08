# TODO: find-me 人臉檢索系統

依 `plan.md` 執行，每完成一個 task 打勾並 commit。

## Phase 0: 前置（使用者處理）
- [ ] 專案降版至 Python 3.11（`.python-version`、`requires-python`）

## Phase 1: 基礎環境
- [ ] Task 1: 安裝依賴並驗證 InsightFace 可運作（S｜依賴: Phase 0）
  - uv add 全部依賴、煙霧測試抽出 512 維向量、buffalo_l 自動下載成功

## Phase 2: 核心管線
- [ ] Task 2: 臉部向量抽取模組 `src/face.py`（S｜依賴: 1）
  - get_app() 單例、extract_faces()、大圖預縮、CUDA→CPU fallback
- [ ] Task 3: 建索引 CLI `src/build_index.py`（S｜依賴: 2）
  - `python -m src.build_index --photos <dir>` → embeddings.npy + meta.json

### Checkpoint A
- [ ] 真實照片目錄建索引成功，統計數字合理；重跑可覆蓋

## Phase 3: 搜尋與 Web
- [ ] Task 4: 搜尋模組 `src/search_engine.py`（S｜依賴: 3）
  - 載入索引、最大臉當本人、餘弦比對、同照片去重取最高分
- [ ] Task 5: FastAPI endpoints `src/main.py` + 改寫根目錄 `main.py` 為啟動入口（S｜依賴: 4）
  - POST /api/search、GET /api/thumb/{id}、GET /api/photo/{id}、GET /
  - `uv run python main.py` 可啟動 web
- [ ] Task 6: 網頁介面 `src/static/index.html`（S｜依賴: 5）
  - 拖放上傳、門檻滑桿（預設 0.40）、縮圖牆 + 分數、點擊開原圖

### Checkpoint B
- [ ] 瀏覽器端到端：上傳本人照片 → 正確撈出照片；滑桿與原圖檢視正常

## Phase 4: 收尾
- [ ] Task 7: README、.gitignore（加 `data/`）、最終驗證（S｜依賴: 6）

## 驗證通則（每個 task commit 前）
- [ ] `uv run ruff check .` 通過
- [ ] 該 task 的 Verification 項目全數通過
