# 縮圖併發限制與持久化快取實作計畫

## 1. 概述

現有同步縮圖 endpoint 由 FastAPI 在線程池中並行執行，每個請求都使用 OpenCV 將完整原圖解碼後再縮成 480px。搜尋一次回傳數十張照片時，並行解碼加上常駐 InsightFace 模型使程序峰值達 3.4 GiB，4 GiB 無 Swap 主機因此觸發 OOM，Cloudflare 隨後將中斷請求呈現為 502。

本次以兩層控制根治：

1. 使用 `BoundedSemaphore(8)` 將 cache miss 的高記憶體縮圖生成工作限制為最多 8 個。
2. 將完成縮圖以來源狀態鍵持久化於 `<INDEX_DIR>/thumbs/`，後續直接以 `FileResponse` 傳送，不再解碼原圖。

## 2. 現況與依賴圖

```text
SearchEngine.meta[face_id].path
              │
              ▼
       _photo_path(face_id)
              │
              ▼
    GET /api/thumb/{face_id}
              │
      ┌───────┴────────┐
      │                │
 cache hit         cache miss
      │                │
 FileResponse     BoundedSemaphore(8)
                       │
               decode → resize → encode
                       │
              temp file → os.replace
                       │
                  FileResponse
```

實作順序必須先完成可獨立驗證的快取核心，再接入 HTTP endpoint，最後做隔離與 GCP 壓力驗證。

## 3. 架構決策

### 3.1 新增 `ThumbnailCache` 單一職責模組

新增 `src/thumbnail_cache.py`，由一個縮圖快取服務物件集中持有：

- cache directory；
- 最大邊長與 JPEG quality；
- cache schema version；
- `BoundedSemaphore(8)`；
- cache key、lookup、generate 與 atomic write 流程。

`src/main.py` 不保留 OpenCV 縮圖細節，只將 `_photo_path()` 的結果交給服務並回傳 `FileResponse`。這可避免 endpoint 同時承擔路由、快取、併發與檔案一致性責任。

### 3.2 只限制 cache miss 的重工作業

快取檔已存在時只需由 Starlette 串流讀檔，沒有完整原圖解碼的記憶體峰值，因此不占用 8 個生成名額。未命中時，以 `with semaphore:` 包住來源讀取至正式快取完成的完整區段；超過 8 個的請求在現有 threadpool 中等待。

採 `BoundedSemaphore` 而非一般計數器，讓 acquire／release 由標準同步原語處理，並在錯誤釋放過多時立即暴露問題。

### 3.3 來源狀態鍵取代 face ID

一張照片可能在 metadata 中對應多張臉與多個 face ID；以 face ID 命名會重複快取。計畫使用 SHA-256 雜湊以下欄位：

```text
cache version
resolved source path
source st_size
source st_mtime_ns
max side
jpeg quality
```

這讓同一照片狀態共用快取，照片或生成設定改變時自然換鍵。選擇 metadata 而非完整內容 hash，是為了讓 cache hit lookup 不必讀完整原圖。

### 3.4 同目錄暫存檔與原子替換

正式 `<hash>.jpg` 只能在 JPEG 完整寫入並關閉後出現。暫存檔建立於同一 cache directory，確保 `os.replace()` 不跨 filesystem；成功時原子替換，失敗時 `finally` 移除暫存檔。

即使兩個競態請求同時產生相同 key，讀者只會看到舊的完整檔案或新的完整檔案，不會讀到部分 JPEG。

### 3.5 使用 `FileResponse`

快取命中與剛生成完成後都回傳 `FileResponse(path, media_type='image/jpeg')`。Starlette 會處理檔案串流並提供 `Content-Length`、`Last-Modified` 與 `ETag`，避免重新把快取內容讀成 Python bytes。

不加入長效 HTTP cache header，因為 URL 仍以 face ID 表示，index 重建可能讓同一 URL 指向不同照片。

## 4. 預計修改檔案

- `src/thumbnail_cache.py`：新增持久化快取、8 併發限制、cache key 與 atomic write。
- `src/main.py`：初始化縮圖快取服務，將 `/api/thumb/{face_id}` 改為快取路徑 `FileResponse`，保留錯誤 contract。
- `README.md`：補充快取目錄、lazy 建立、手動清空與自動重建說明。

預期不修改：

- `pyproject.toml`、`uv.lock`（不新增 dependency）；
- `src/static/index.html`（本次不做 retry）；
- `src/face.py`（本次不縮減 InsightFace 模組）；
- systemd、Cloudflare 與資料索引格式。

## 5. 分階段執行

### Phase 1：快取核心

1. 新增縮圖 cache service 與明確常數。
2. 實作來源狀態 cache key。
3. 實作 cache hit fast path。
4. 實作最多 8 個 cache miss generation。
5. 實作 OpenCV decode／resize／encode 與同目錄 atomic write。
6. 使用隔離圖片驗證命中、失效、錯誤與競態。

### Checkpoint 1

- 同一來源狀態回傳同一 cache path。
- cache hit 不再解碼來源圖片。
- 來源修改後使用不同 path。
- 32 個並行 miss 的同時生成數不超過 8。
- 任何例外都不留下部分 JPEG 或暫存檔。

### Phase 2：HTTP 整合與文件

1. 在 `src/main.py` 初始化 service，cache root 使用 `INDEX_DIR / 'thumbs'`。
2. 縮圖 endpoint 改由 service 取得路徑並以 `FileResponse` 回傳。
3. 將無效來源、解碼、編碼與寫入錯誤映射回既有 404／500 語意。
4. README 說明快取運作與維運方式。
5. 使用隔離 index 實際呼叫 HTTP endpoint。

### Checkpoint 2

- `/api/thumb/{face_id}` URL、media type 與既有錯誤行為不變。
- 首次 HTTP 請求建立 JPEG，第二次直接命中同一檔案。
- `FileResponse` 回應具有正確 content length，且檔案可解碼。
- 生成物只出現在已忽略的 index cache directory。

### Phase 3：資源與 GCP 驗證

1. 執行 Ruff format／lint。
2. 部署後先記錄 `MainPID`、`NRestarts` 與程序 RSS。
3. 清空測試用快取或選取尚未建立快取的實際結果，觸發 32 個以上並行縮圖請求。
4. 驗證首次冷快取、第二次暖快取與 Cloudflare 頁面行為。
5. 比較驗證前後 `NRestarts`、kernel OOM log 與 memory peak。

### Checkpoint 3

- 冷快取壓力下服務不被 OOM killer 終止。
- `NRestarts` 不增加，cloudflared 不再因 origin 消失產生一批 502。
- 暖快取回應不重新解碼原圖，延遲與 RSS 低於冷快取。
- 所有驗收條件通過後才建立 fix commit。

## 6. 驗證策略

依專案規範不新增測試檔；使用已忽略的 `tmp/` 建立一次性 fixture 與壓力 harness。

### 6.1 快取核心驗證

- 逐張建立不同尺寸、不同格式的隔離圖片。
- 第一次 `get_or_create()` 後確認 JPEG 可由 OpenCV 解碼且最大邊為 480。
- 再次呼叫確認 cache path 與 mtime 不變。
- 讓兩個 face metadata 指向同一 source，確認共用相同 path。
- 修改 source 的內容或 mtime，確認產生新 key。
- 對不存在或不可讀圖片確認不建立正式 cache。
- 並行觸發至少 32 個 cache miss，使用一次性計數 harness 確認 active generation peak 為 8。
- 並行競態完成後確認所有 JPEG 可讀、沒有零位元檔與 `.tmp` 殘留。

### 6.2 HTTP 整合驗證

- 建立隔離 `embeddings.npy`、`meta.json` 與照片 fixture，以 `FINDME_INDEX_DIR` 啟動應用。
- 呼叫有效、無效與不可讀照片 ID，確認 200／404／500 contract。
- 連續呼叫同一 ID，確認第二次不改寫 cache。
- 呼叫同源不同 face ID，確認只有一份持久化 JPEG。

### 6.3 品質檢查

```bash
uv run ruff format src
uv run ruff check src
git diff --check
```

### 6.4 GCP 實機驗證

- 重啟服務前後記錄 `systemctl show find-me --property=MainPID --property=NRestarts`。
- 使用實際搜尋結果觸發超過 32 張冷快取縮圖。
- 監看 `systemctl status`、`journalctl -u find-me` 與 kernel OOM 訊息。
- 再次載入相同結果，確認快取命中且頁面不再出現因應用重啟導致的 502。

## 7. Commit 規劃

功能與驗證完成後建立一個原子 fix commit：

```text
fix: 載入大量縮圖時服務記憶體耗盡

問題: 縮圖端點會在線程池中同時完整解碼多張原始照片，與常駐人臉模型共同耗盡 4 GiB 記憶體，導致程序被 OOM killer 終止並讓部分縮圖回傳 502。
解法: 將縮圖快取未命中的生成工作限制為同時 8 張，並以來源狀態鍵持久化 JPEG；後續請求直接以 FileResponse 回傳快取。
```

commit 前完成 Ruff、隔離功能驗證與實際 HTTP 壓力驗證；不 push、merge 或 rebase。

## 8. 風險與因應

| 風險 | 影響 | 因應 |
|---|---|---|
| 8 張大型原圖加上 InsightFace 在 4 GiB 仍可能接近上限 | 仍有 OOM 風險 | 使用者同步升級 VM；實作後以實際 cold-cache 壓力測量，必要時需另行裁決是否降低上限 |
| 快取第一次建立仍需要完整解碼 | 首次載入較慢 | 以 semaphore 排隊換取可控峰值；後續由持久化快取消除重工 |
| 同一 key 的競態生成 | 重複工作或部分檔 | semaphore 內二次檢查並使用唯一 temp file + `os.replace()`；允許相同完整內容最後寫入者覆蓋 |
| source path、mtime 或 size 變更產生孤兒檔 | cache directory 緩慢增長 | 本次不自動刪除；README 文件化可安全清空並 lazy 重建 |
| index 重建後相同 face ID 指向不同照片 | 瀏覽器／CF 長效 cache 可能顯示錯圖 | 本次不新增長效 HTTP cache header；disk cache 以 source state 而非 face ID 命名 |
| cache directory 無寫入權限或磁碟滿 | 縮圖回傳 500 | 回傳明確錯誤且不回退到無界記憶體生成；部署時驗證 service user 權限與空間 |
| 未來啟用多 Uvicorn worker | 全機總生成數變成 8 × workers | 文件化目前為 per-process 上限；多 worker 前重新評估全域協調或降低單 worker 上限 |

## 9. 待確認事項與推薦答案

1. **8 個名額只計 cache miss generation，cache hit 不計入**（推薦）。
2. **維持單一 Uvicorn worker，8 為目前全服務上限**（推薦）。
3. **採 lazy cache，不在 build index 或服務啟動時預建**（推薦）。
4. **stale cache 不自動清理，只在 README 說明停止服務後可手動清空**（推薦）。
5. **若升級後實測 8 仍超出記憶體，不自行改成其他數字，先回報數據請使用者裁決**（推薦）。
