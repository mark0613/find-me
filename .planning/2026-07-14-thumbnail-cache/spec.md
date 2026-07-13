# 規格：縮圖併發限制與持久化快取

## 1. 目標

解決搜尋結果一次載入大量縮圖時，Find Me 程序因同時將多張原始照片完整解碼至記憶體而觸發 OOM 的問題。

已觀察到的基準事故：

- 主機記憶體約 4 GiB，沒有 Swap。
- 大量 `/api/thumb/{face_id}` 請求並行時，Python 程序峰值達 3.4 GiB。
- Linux OOM killer 終止程序後，Cloudflare Tunnel 收到 `EOF` 或 `connection refused`，使用者看到部分縮圖 502。

本次需完成：

1. 單一應用程序最多同時執行 8 個「縮圖快取未命中後的原圖解碼／縮放／JPEG 編碼／寫入」工作。
2. 將產生完成的 JPEG 縮圖持久化，後續相同來源狀態直接回傳快取檔案，不再解碼原圖。

## 2. 技術範圍

### 2.1 現有技術

- Python `>=3.11`
- FastAPI `>=0.139.0`
- OpenCV `>=5.0.0.93`
- Uvicorn `>=0.51.0`
- 目前正式啟動方式為單一 Uvicorn process。

不新增第三方 dependency；使用 Python 標準函式庫完成 semaphore、雜湊、暫存檔與原子替換。

### 2.2 專案結構

- `src/main.py`：HTTP endpoint 與既有照片路徑解析。
- `src/thumbnail_cache.py`：新增縮圖快取與生成服務，封裝併發限制、cache key、影像處理及原子寫入。
- `data/index/thumbs/`：預設持久化快取位置；若設定 `FINDME_INDEX_DIR`，則使用 `<INDEX_DIR>/thumbs/`。
- `README.md`：說明快取位置、lazy 建立、失效方式與可安全清空後重建。

`data/` 已由 `.gitignore` 排除，縮圖快取不得加入 Git。

## 3. 功能需求

### 3.1 併發限制

- 使用 process-level `threading.BoundedSemaphore(8)` 保護快取未命中的縮圖生成區段。
- 第 9 個以上的 cache miss 必須等待名額，不得拒絕請求，也不得另開不受控生成工作。
- cache hit 直接使用已完成的 JPEG，不占用生成名額。
- semaphore 必須涵蓋完整的高記憶體階段：讀取原圖、完整解碼、縮放、JPEG 編碼與快取寫入。
- 無論成功或例外，名額都必須可靠釋放。

FastAPI 會將同步 `def` endpoint 放在線程池執行，因此 process-level threading semaphore 可直接限制現有同步縮圖端點的重工作業。

### 3.2 快取位置與鍵

- 快取目錄固定為 `INDEX_DIR / "thumbs"`，首次 cache miss 時建立。
- 快取檔案使用 `.jpg`。
- cache key 使用 SHA-256，輸入至少包含：
  - cache schema/version；
  - 原始照片的 resolved absolute path；
  - `st_size`；
  - `st_mtime_ns`；
  - 最大邊長 `480`；
  - JPEG quality `85`。
- 同一路徑、大小、修改時間與縮圖設定必須得到相同快取路徑。
- 同張照片即使對應多個 face ID，也必須共用同一份縮圖。
- 原始照片內容狀態或縮圖設定改變時，必須使用新的快取鍵，不得誤用舊縮圖。
- 不以原圖內容雜湊作為鍵，避免每次 cache lookup 都必須完整讀取大檔。

### 3.3 快取生成與原子寫入

- cache hit 直接回傳既有檔案，不呼叫 OpenCV 解碼或編碼。
- cache miss 進入 semaphore 後需再次確認快取是否已出現，減少等待期間其他請求已完成時的重工。
- 影像處理結果與現有行為一致：最大邊長 480、維持長寬比、JPEG quality 85。
- 先將完整 JPEG 寫入同一快取目錄下的唯一暫存檔，關閉檔案後使用 `os.replace()` 原子替換正式路徑。
- 生成失敗不得留下正式快取檔；未完成的暫存檔必須在 `finally` 清理。
- 多個 process 或競態同時產生相同鍵時，最後可重複覆蓋相同內容，但任何讀者都不得看到部分檔案。

### 3.4 HTTP 行為

- 保留 `GET /api/thumb/{face_id}` URL 與 `image/jpeg` media type。
- 無效 ID、原始照片不存在或無法解碼時，維持現有 404 語意。
- JPEG 編碼或快取寫入失敗時回傳明確 500，不回傳半成品。
- 成功時改用 `FileResponse` 回傳持久化 JPEG，由 Starlette 提供 `Content-Length`、`Last-Modified` 與 `ETag`。
- 不在本次加入長時間瀏覽器或 Cloudflare cache header，避免 index 重建後 face ID 對應改變而產生錯圖。

### 3.5 快取生命週期

- 快取採 lazy 建立，不在 build index 或應用啟動時預先產生全部縮圖。
- 舊 cache key 對應的孤兒檔案本次不自動清理，避免在執行中誤刪仍可能被請求的檔案。
- 使用者可停止服務後清空 `<INDEX_DIR>/thumbs/`；服務會在後續請求中自動重建。
- 重建 index 不要求同步清空快取；相同來源狀態可繼續命中，不同來源狀態會自然使用新鍵。

## 4. 不變行為與範圍外

- 不改搜尋 API、相似度計算、結果排序或 face ID 格式。
- 不改原圖 `GET /api/photo/{face_id}`。
- 不改 ZIP 下載流程；Cloudflare 緩衝及前端 `res.blob()` 另案處理。
- 不調整 InsightFace 載入模組。
- 不加入前端縮圖失敗重試。
- 不修改 systemd、Cloudflare、Swap 或 GCP VM 規格。
- 不新增 unit、integration 或 e2e test 檔案，依專案規範以一次性驗證與實際 HTTP 壓力走查取代。

## 5. 開發與驗證指令

```bash
# 格式化與 lint
uv run ruff format src
uv run ruff check src

# 啟動
uv run --locked --no-sync python main.py

# GCP 部署依賴同步（只有 dependency 變更時需要；本次預期不變）
uv sync --locked --no-dev
sudo systemctl restart find-me
```

一次性驗證資料只能放在已忽略的 `tmp/` 或系統臨時目錄，驗證完成後不得提交。

## 6. 程式風格

- 縮圖 cache key、生成、寫入與查找封裝在單一職責模組，不把所有細節繼續塞進 endpoint。
- 使用明確常數與 self-explanatory 名稱，不增加大段 function header 註解。
- 只在解釋原子寫入或併發邊界等非直觀原因時保留短註解。
- endpoint 只負責解析照片路徑、呼叫縮圖服務、映射錯誤與回傳 response。

預期責任邊界示意：

```python
thumbnail_path = thumbnail_cache.get_or_create(source_path)
return FileResponse(thumbnail_path, media_type='image/jpeg')
```

## 7. 驗收標準

- 32 個以上同時 cache miss 的請求中，任一時間最多 8 張原圖處於縮圖生成區段。
- 大量首次縮圖請求不再讓 Find Me process 被 OOM killer 終止；`NRestarts` 在驗證前後不增加。
- 首次請求會產生可解碼的持久化 JPEG；後續相同來源狀態直接命中相同快取檔。
- 多個 face ID 指向同一照片時共用快取。
- 修改來源照片或縮圖設定後不使用舊 cache key。
- 高併發競態下不出現部分 JPEG、零位元檔或殘留暫存檔。
- `/api/thumb/{face_id}` 既有成功與錯誤 contract 保持不變。
- Ruff format、lint、隔離 fixture 驗證與 GCP 實際 HTTP 壓力驗證皆通過。

## 8. 邊界

### 一律執行

- 先用隔離資料驗證，不修改正式 index 或照片。
- 每個 commit 前執行 formatter、lint 與對應功能驗證。
- 檢查 cache 生成物保持在 Git ignore 範圍。
- GCP 驗證前記錄 `NRestarts` 與記憶體基準，驗證後再次比較。

### 需先詢問

- 新增第三方影像或 cache 套件。
- 改變 8 的上限、快取位置、縮圖尺寸或 JPEG quality。
- 加入自動刪除／容量上限策略。
- 修改前端、下載流程、InsightFace 或部署設定。

### 禁止

- 將縮圖、照片、index、臨時驗證資料加入 Git。
- 為驗證而修改或刪除正式照片與 `data/index`。
- 以增加 RAM 作為唯一修正而保留無界併發。

## 9. 官方依據

- [FastAPI：同步 path operation 會在線程池執行](https://fastapi.tiangolo.com/async/)
- [Python 3.11：BoundedSemaphore](https://docs.python.org/3.11/library/threading.html#boundedsemaphore-objects)
- [Python 3.11：os.replace](https://docs.python.org/3.11/library/os.html#os.replace)
- [Starlette：FileResponse](https://www.starlette.io/responses/#fileresponse)

## 10. 待確認事項與推薦答案

1. **8 的範圍：** 限制 cache miss 的重工作業，cache hit 不占名額（推薦）。
2. **多 worker 語意：** 目前單一 Uvicorn process 全機最多 8；未來若啟用多 worker，會變成每個 worker 各 8，屆時需重新評估（推薦維持目前單 process）。
3. **快取策略：** lazy 持久化於 `<INDEX_DIR>/thumbs/`，不在啟動時預建（推薦）。
4. **失效策略：** 路徑、大小、修改時間與縮圖設定共同構成 key；不做昂貴的原圖內容雜湊（推薦）。
5. **清理策略：** 本次不做自動 pruning，只文件化手動清空後自動重建（推薦）。
