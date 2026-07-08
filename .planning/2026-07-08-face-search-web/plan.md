# Implementation Plan: find-me — 從照片海撈出自己的人臉檢索系統

## Overview

建立一個最簡可用的本地人臉檢索系統：使用者把「照片海」放在本機目錄，先跑一次 CLI 建立臉部向量索引；之後開啟 FastAPI 提供的網頁，上傳一張自己的照片，系統即回傳所有包含自己的照片（含相似度分數與縮圖預覽）。

技術核心採用 Perplexity 討論結論：InsightFace（buffalo_l 模型）抽 512 維臉部向量 + 餘弦相似度比對。全程本地運行，照片不外流。

## Architecture Decisions

- **向量比對用 numpy，不用 FAISS**：照片海規模為數萬張（臉向量約 5～20 萬條），512 維 float32 全量矩陣內積在毫秒～數十毫秒等級，numpy 完全足夠。省掉 faiss-cpu 依賴（Windows + Python 3.13 的 wheel 相容性風險也一併消除）。
- **推理後端先用 CPU（onnxruntime）**：建索引是一次性工作，數萬張照片 CPU 約 1 小時內可完成，日常查詢是單張照片、秒級。GPU（onnxruntime-gpu + CUDA）列為後續優化，`face.py` 的 provider 設計預留自動 fallback，屆時只需換裝套件。
- **照片海不經 web 上傳**：照片海直接放本機目錄，用 CLI 指定路徑建索引；web 僅負責「上傳查詢照片 → 顯示結果」。重建索引也走 CLI（數萬張重跑即可，不做增量更新）。
- **索引儲存格式**：`data/index/embeddings.npy`（N×512 float32）+ `data/index/meta.json`（每列對應的照片絕對路徑與臉序號）。meta 用 JSON 而非 pickle，可讀、可除錯、無反序列化風險。
- **前端極簡**：單一靜態 `index.html`（原生 JS + fetch），不引入前端框架、不用模板引擎。上傳表單 + 門檻滑桿 + 結果縮圖牆。
- **縮圖即時產生**：`GET /api/thumb/{id}` 用 OpenCV 即時縮圖回傳 JPEG，不落地快取（一次查詢僅顯示數十張，延遲可接受）。點縮圖可看原圖（`GET /api/photo/{id}`）。
- **查詢照片取「最大的臉」當作本人**（與 Perplexity 腳本一致）；同一張照片有多張臉命中時只列一次，取最高分。
- **模組劃分**：
  - `src/face.py` — InsightFace 初始化與向量抽取（建索引與查詢共用，避免重複）
  - `src/build_index.py` — CLI：掃目錄 → 抽向量 → 存索引
  - `src/search_engine.py` — 載入索引 + 餘弦比對 + 依照片分組
  - `src/main.py` — FastAPI app 與 API endpoints
  - `src/static/index.html` — 網頁介面
- **根目錄 `main.py` 改寫為啟動入口**：以 `uvicorn.run("src.main:app")` 啟動 web（`uv run python main.py`）；建索引則為 `python -m src.build_index`。
- **Python 版本採 3.11**：insightface 生態在 3.10/3.11 最成熟，避免 3.13 的編譯相容風險。由使用者自行降版後才開工。

## 目錄結構（完成後）

```
find-me/
├─ main.py                 # 啟動入口：uv run python main.py
├─ src/
│  ├─ __init__.py
│  ├─ face.py              # InsightFace 封裝：初始化、抽向量、縮圖預處理
│  ├─ build_index.py       # CLI 建索引：python -m src.build_index --photos <dir>
│  ├─ search_engine.py     # 索引載入 + 餘弦相似度搜尋
│  ├─ main.py              # FastAPI app
│  └─ static/
│     └─ index.html        # 上傳 + 結果頁
├─ data/                   # 整個目錄 gitignore
│  └─ index/               # embeddings.npy + meta.json
├─ pyproject.toml
└─ README.md
```

## API 設計

| Method | Path | 說明 |
|---|---|---|
| GET | `/` | 回傳 `index.html` |
| POST | `/api/search` | multipart 上傳查詢照片；query 參數 `threshold`（預設 0.4）；回傳 JSON：`[{id, score, filename}]`，依分數排序 |
| GET | `/api/thumb/{id}` | 依索引 id 回傳該照片的縮圖 JPEG（長邊 480px） |
| GET | `/api/photo/{id}` | 回傳原圖檔案 |

`id` 為索引中的列序號，照片路徑只存在後端 meta 中，不直接暴露檔案系統路徑作為 URL 參數。

## Task List

### Phase 1: 基礎環境

- [ ] Task 1: 安裝依賴並驗證 InsightFace 可運作

### Phase 2: 核心管線（CLI 可先跑通）

- [ ] Task 2: 臉部向量抽取模組 `src/face.py`
- [ ] Task 3: 建索引 CLI `src/build_index.py`

### Checkpoint A: 索引建立完成
- [ ] 對一個真實照片目錄成功建出索引，臉數與檔案數合理
- [ ] 重跑 CLI 可正常覆蓋舊索引

### Phase 3: 搜尋與 Web

- [ ] Task 4: 搜尋模組 `src/search_engine.py`
- [ ] Task 5: FastAPI endpoints `src/main.py`
- [ ] Task 6: 網頁介面 `src/static/index.html`

### Checkpoint B: 端到端流程
- [ ] 瀏覽器上傳自己的照片 → 正確列出照片海中含自己的照片
- [ ] 調整門檻滑桿結果隨之變化；點縮圖能開原圖

### Phase 4: 收尾

- [ ] Task 7: README、.gitignore 與最終驗證

---

## Task 詳細內容

## Task 1: 安裝依賴並驗證 InsightFace 可運作

**Description:** 用 uv 安裝所有執行期依賴，並寫一個丟棄式煙霧測試（放 scratchpad，不進版控）驗證 buffalo_l 模型能自動下載、能從測試照片抽出 512 維向量。這是整個專案最大的風險點（insightface 在 Windows + Python 3.13 需要 C++ 編譯），必須最先驗證。

**Acceptance criteria:**
- [ ] `uv add fastapi "uvicorn[standard]" python-multipart insightface onnxruntime opencv-python numpy tqdm` 成功
- [ ] 煙霧測試：讀一張含人臉的測試照片，印出 `normed_embedding.shape == (512,)`
- [ ] buffalo_l 已下載至 `~/.insightface/models/buffalo_l/`

**Verification:**
- [ ] `uv run python <scratchpad>/smoke.py` 輸出向量 shape
- [ ] `uv run ruff check .` 通過

**Dependencies:** None

**Files likely touched:** `pyproject.toml`, `uv.lock`

**Estimated scope:** S（1-2 檔）

**前置條件:** 使用者已將專案降版至 Python 3.11（`.python-version`、`pyproject.toml` 的 `requires-python`）。

---

## Task 2: 臉部向量抽取模組 `src/face.py`

**Description:** 封裝 InsightFace 為單一模組，供建索引與查詢共用。內容：`FaceAnalysis` 惰性初始化（providers 先 CUDA 後 CPU 自動 fallback，比照 Perplexity 腳本的寫法）、`extract_faces(image) -> list[Face]`（回傳 bbox 與 normed_embedding）、大圖預縮（長邊超過 1920 先縮，省記憶體）。

**Acceptance criteria:**
- [ ] 提供 `get_app()`（單例）與 `extract_faces(img: np.ndarray)` 兩個介面
- [ ] 超過 1920px 長邊的圖片會先等比縮小再偵測
- [ ] 無 GPU 環境下自動走 CPU，不拋例外

**Verification:**
- [ ] 用煙霧測試腳本改 import `src.face`，多人合照能抽出多張臉的向量
- [ ] `uv run ruff check .` 通過

**Dependencies:** Task 1

**Files likely touched:** `src/__init__.py`, `src/face.py`

**Estimated scope:** S（2 檔）

---

## Task 3: 建索引 CLI `src/build_index.py`

**Description:** 遞迴掃描 `--photos` 目錄下所有圖片（jpg/jpeg/png/bmp/webp/tiff），對每張照片呼叫 `src.face.extract_faces`，把所有臉向量堆成 N×512 矩陣存 `data/index/embeddings.npy`，對應的 `(照片絕對路徑, 臉序號)` 存 `data/index/meta.json`。tqdm 顯示進度，讀不到或偵測失敗的圖片印警告後跳過。

**Acceptance criteria:**
- [ ] `uv run python -m src.build_index --photos <dir> [--out data/index]` 可執行
- [ ] 產出 `embeddings.npy` 與 `meta.json`，兩者列數一致
- [ ] 壞圖／無臉照片不中斷流程，結尾印出統計（照片數、臉數、跳過數）

**Verification:**
- [ ] 對一個 20～50 張的小型測試目錄建索引，抽查 meta.json 內容正確
- [ ] 對真實照片海跑一次（Checkpoint A）
- [ ] `uv run ruff check .` 通過

**Dependencies:** Task 2

**Files likely touched:** `src/build_index.py`

**Estimated scope:** S（1 檔）

---

## Task 4: 搜尋模組 `src/search_engine.py`

**Description:** 定義 `SearchEngine` 類別：載入 `embeddings.npy` + `meta.json`；`search(query_image, threshold) -> list[Hit]`——對查詢照片抽臉、取面積最大的臉當本人、與全索引做內積（normed embedding 內積即餘弦相似度）、過門檻後依照片路徑去重（同照片取最高分）、按分數降冪回傳。Hit 含索引 id、分數、照片路徑。

**Acceptance criteria:**
- [ ] 索引不存在時拋出明確錯誤訊息（提示先跑 build_index）
- [ ] 查詢照片無人臉時回傳明確錯誤（而非空結果）
- [ ] 同一張照片多張臉命中只回傳一筆（最高分）

**Verification:**
- [ ] 用測試索引 + 一張本人照片跑通，分數排序正確
- [ ] `uv run ruff check .` 通過

**Dependencies:** Task 3

**Files likely touched:** `src/search_engine.py`

**Estimated scope:** S（1 檔）

---

## Task 5: FastAPI endpoints `src/main.py`

**Description:** 建立 FastAPI app：啟動時載入 `SearchEngine`（索引不存在則啟動失敗並提示）；實作 `POST /api/search`（接 multipart 圖檔 + `threshold` 參數，回傳 JSON 結果）、`GET /api/thumb/{id}`（OpenCV 即時縮圖，長邊 480px，回傳 JPEG）、`GET /api/photo/{id}`（FileResponse 原圖）、`GET /`（回傳靜態 index.html）。id 超出範圍回 404。同時把根目錄 `main.py` 改寫為啟動入口（`uvicorn.run("src.main:app")`）。

**Acceptance criteria:**
- [ ] `uv run python main.py` 可啟動 web server
- [ ] `/api/search` 用 curl 上傳照片可拿到 JSON 結果
- [ ] `/api/thumb/{id}` 與 `/api/photo/{id}` 回傳正確圖片，非法 id 回 404
- [ ] 上傳非圖片檔回 400，查詢照片無人臉回 422 並附中文錯誤訊息

**Verification:**
- [ ] curl 手動打三支 API 驗證
- [ ] `uv run ruff check .` 通過

**Dependencies:** Task 4

**Files likely touched:** `src/main.py`, `main.py`

**Estimated scope:** S（2 檔）

---

## Task 6: 網頁介面 `src/static/index.html`

**Description:** 單一 HTML 檔（原生 JS，無框架、無外部 CDN）：檔案選擇／拖放上傳查詢照片、門檻滑桿（0.30～0.50，預設 0.40）、送出後顯示「找到 N 張」與縮圖牆（每張顯示相似度分數），點縮圖新分頁開原圖。查詢中顯示 loading，錯誤訊息（無人臉等）直接顯示在頁面上。

**Acceptance criteria:**
- [ ] 拖放或選檔上傳皆可觸發查詢
- [ ] 結果以縮圖網格呈現，含分數標籤，點擊開原圖
- [ ] 調整門檻重新查詢，結果數量隨之改變
- [ ] 後端錯誤（無人臉、非圖片）在頁面顯示為可讀訊息

**Verification:**
- [ ] 瀏覽器手動走完整流程（Checkpoint B）

**Dependencies:** Task 5

**Files likely touched:** `src/static/index.html`

**Estimated scope:** S（1 檔）

---

## Task 7: README、.gitignore 與最終驗證

**Description:** 更新 README（專案說明、安裝、建索引、啟動 web 的步驟、門檻調校建議 0.35~0.45、buffalo_l 非商業授權提醒）；`.gitignore` 加入 `data/`；對真實照片海做最終端到端驗證。

**Acceptance criteria:**
- [ ] README 依步驟可從零跑起整套系統
- [ ] `data/` 不會進版控
- [ ] 真實照片海端到端驗證通過

**Verification:**
- [ ] `git status` 確認無不該進版控的檔案
- [ ] `uv run ruff check .` 通過

**Dependencies:** Task 6

**Files likely touched:** `README.md`, `.gitignore`

**Estimated scope:** S（2 檔）

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| insightface 安裝需 C++ 編譯（sdist 需 build tools / Cython） | Med | 已決議採 Python 3.11（生態最成熟）；Task 1 最先驗證安裝，卡編譯先試 `pip install cython` 或裝 VS C++ Build Tools |
| CPU 建索引數萬張需 20 分鐘～1 小時 | Med | 一次性成本，可接受；太慢再加裝 onnxruntime-gpu（face.py 已預留 CUDA fallback 設計，1660 Ti 6GB 足夠） |
| 門檻 0.4 撈太少或混入他人 | Low | UI 提供滑桿即時調整（0.35~0.45），README 附調校建議 |
| 高解析度原圖直接回傳導致結果頁過慢 | Low | 已用即時縮圖 endpoint 解決；若仍慢再加磁碟快取 |

## Open Questions（已全數裁決，2026-07-08）

1. **向量比對引擎**：✅ 採 **numpy**（FAISS Flat 與 numpy 內積結果精確相同，此規模無效能差異）。
2. **推理後端**：✅ **先 CPU** 跑通全流程，正式使用再換 onnxruntime-gpu（face.py 預留 CUDA fallback）。
3. **照片海進入方式**：✅ 本機目錄 + CLI 建索引，web 只做查詢。
4. **Python 版本**：✅ 開工前由使用者自行降版至 **3.11**。
5. **根目錄 `main.py`**：✅ 不刪除，**改寫為啟動入口**（`uv run python main.py` 啟動 web），於 Task 5 完成。
