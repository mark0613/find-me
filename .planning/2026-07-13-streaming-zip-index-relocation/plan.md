# Streaming ZIP 與 index 路徑重新連結腳本實作計畫

## 1. 目標

完成兩項互相獨立但同屬 GCP 搬遷準備的調整：

1. 將 `POST /api/download` 從在記憶體建立完整 ZIP，改為邊讀照片、邊產生 ZIP、邊回傳。
2. 新增 index 路徑重新連結 CLI，讓既有 `embeddings.npy` 可直接沿用，只重寫 `meta.json` 的照片根目錄，不重新執行人臉辨識。

## 2. 範圍與不變行為

### Streaming ZIP

- 保留相同 API、request body、檔名與 media type，前端不需修改。
- 保留同一照片多張臉只打包一次。
- 保留同名檔案以 `_1`、`_2` 方式避開衝突。
- 保留無效 ID 與已不存在照片直接跳過；全部無效時回傳 404。
- 保留 `ZIP_STORED`，不對 JPEG 等已壓縮照片重複壓縮。
- 使用 `stream-zip` 的 `stream_zip()` 搭配 FastAPI `StreamingResponse`，不建立完整 `BytesIO` 或暫存 ZIP。

### index 路徑重新連結

- CLI 僅接收新的照片根目錄，index 固定使用 `data/index`：

  ```bash
  uv run python -m src.relink_index /srv/find-me/photos
  ```

- 從既有 `meta.json` 照片路徑推導共同舊根目錄，不要求使用者重複提供已存在於 index 的資訊。
- 對每個照片路徑進行根目錄替換，保留舊共同根目錄以下的相對路徑。
- 支援 Windows 舊路徑搬到 Linux 新路徑，不依賴腳本執行平台對舊路徑的解析方式。
- 寫入前驗證 `embeddings.npy` 筆數等於 `meta.json` 筆數，且共同舊根目錄可被明確推導。
- 預設驗證新路徑全部存在；驗證失敗不修改原檔。
- 正式寫入前建立依序編號的 `meta.json.bak-<number>` 備份，並使用暫存檔原子替換 `meta.json`。

## 3. 架構決策

### 3.1 使用 `stream-zip`

採用 `stream-zip>=0.0.84`，由 `uv.lock` 鎖定實際版本，沿用 `n8n-mentor/mentor` backend 已採用的做法。每個 ZIP member 由固定大小的檔案 block iterator 提供，使用 `NO_COMPRESSION_64` 避免重複壓縮 JPEG，並支援整包超過 4 GiB。此模式不緩衝完整 ZIP，但套件會先緩衝目前的單一照片以取得大小與 CRC；以目前約 5000 張、總量約 4 GB 的資料而言，記憶體峰值取決於最大單張照片，而不是整包下載容量。

### 3.2 同步 endpoint 搭配 `StreamingResponse`

ZIP 來源是同步檔案讀取與同步 iterator；endpoint 維持同步 function，由 Starlette/FastAPI 處理串流 iterator，避免在 event loop 直接做阻塞檔案 I/O。

### 3.3 路徑重新連結只接收新照片根目錄

`data/index` 是專案固定位置，舊照片根目錄由 metadata 所有獨立照片路徑的共同父路徑推導。腳本只接收一個 positional argument 作為新照片根目錄，使用平台無關的 lexical path component 計算相對路徑，再由新根目錄組裝。推導或目標檔案驗證不通過時零寫入，避免自動判斷錯誤後破壞 index。

## 4. 預計修改檔案

- `pyproject.toml`：新增 streaming ZIP dependency。
- `uv.lock`：由 `uv add` / `uv lock` 正常更新。
- `src/main.py`：改用 `stream_zip()`、固定大小檔案 iterator 與 `StreamingResponse`。
- `src/relink_index.py`：新增跨平台 index 路徑重新連結 CLI。
- `README.md`：補充既有 index 路徑重新連結用法。

不修改前端、不修改 embeddings 格式、不重新建立現有 index。

## 5. 執行順序

```text
新增並鎖定 stream-zip
          │
          └── 改造下載 endpoint ── 驗證 ZIP 串流與既有行為

新增 relink_index CLI ── 使用隔離資料驗證 root 推導 / 備份 / 改寫 / 失敗保護
          │
          └── 更新 README ── lint / 啟動 / HTTP 整合驗證
```

## 6. 驗證策略

依專案規範不新增 unit、integration 或 e2e test 檔案，改用以下一次性驗證：

- 執行專案既有 formatter / lint 指令。
- 啟動 FastAPI，實際呼叫 `/api/download`，確認 response 使用串流、ZIP 可由標準工具解開。
- 以至少兩個同名測試檔驗證 ZIP 內重名編號。
- 以重複 ID 驗證同一照片只出現一次。
- 以不存在檔案與無效 ID 驗證跳過與 404 行為。
- 下載期間觀察 response chunk 與程序記憶體，不等待整包 ZIP 建好才收到第一批資料。
- 使用隔離的臨時 index fixture 驗證重新連結邏輯，不修改正式 `data/index/meta.json`。
- 驗證舊 root 推導、成功重新連結會建立備份、任何驗證失敗都不變更原檔。
- 驗證 `embeddings.npy` 與重新連結後 `meta.json` 筆數一致。

## 7. Commit 規劃

1. `feat: 串流下載照片 ZIP`
2. `feat: 新增 index 路徑重新連結工具`

每個 commit 前分別執行相關 lint 與功能驗證；不執行 push、merge 或 rebase。

## 8. 風險與因應

| 風險 | 影響 | 因應 |
|---|---|---|
| response 開始後才發生檔案讀取錯誤 | HTTP status 已無法改成錯誤碼 | 建立串流前先完成路徑存在檢查；傳輸中檔案被移除屬不可完全避免的競態 |
| ZIP 超過 4 GiB | 舊 ZIP32 格式可能失敗 | 對 ZIP member 明確使用 `NO_COMPRESSION_64` |
| `NO_COMPRESSION_64` 會緩衝目前單一照片 | 峰值記憶體至少接近最大單檔大小 | 實作時以固定 block 讀取並驗證實際峰值；不緩衝多張照片或完整 ZIP |
| Windows 路徑在 Linux 無法用 `Path` 解析 | 相對路徑計算錯誤 | 對舊路徑做平台無關的 lexical normalization，不用 host OS 解讀舊路徑 |
| 共同舊 root 推導錯誤或語意不符 | 大量 path 指向錯誤位置 | 要求所有新路徑實際存在才允許寫入；否則零寫入並保留原 index |

## 9. 待確認事項與推薦答案

1. 「重新連結 index」定義為重寫 `meta.json` 的照片根目錄、不重算 embeddings（推薦，已依此規劃）。
2. CLI 固定操作 `data/index`，只接收一個 positional argument 作為新照片根目錄；舊 root 從 metadata 推導（推薦，已依此規劃）。
3. 成功改寫前自動建立 `meta.json.bak-<number>`，即使已有備份也不覆蓋（推薦）。
4. Streaming ZIP 使用 mentor backend 已採用的 `stream-zip` 與 `NO_COMPRESSION_64`（推薦）。
