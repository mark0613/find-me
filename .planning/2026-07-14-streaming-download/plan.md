# 一鍵下載原生串流實作計畫

## 1. 概述

將目前「fetch 完整 ZIP → blob → object URL → 點擊下載」改為「HTML form POST → attachment response → 瀏覽器下載管理器」。後端新增向下相容的 form endpoint，並抽出共用 ZIP response builder；既有 JSON endpoint 保持不變。

這項修改改善的是下載啟動體感、狀態正確性與瀏覽器記憶體使用，不會改變實際傳輸頻寬。

## 2. 現況資料流

```text
點擊按鈕
  → fetch POST JSON
  → 後端 StreamingResponse
  → Cloudflare／網路持續傳輸
  → res.blob() 將完整 ZIP 放入瀏覽器記憶體
  → 全部完成後才建立 object URL
  → 瀏覽器顯示下載
```

問題點是前端 `blob()` 使「串流到瀏覽器」變成「完整緩衝後才交給下載管理器」。

## 3. 目標資料流

```text
點擊按鈕
  → 建立暫時 HTML form（重複 ids 欄位）
  → POST /api/download/file 至隱藏 iframe
  → 後端共用 ZIP StreamingResponse
  → Content-Disposition attachment
  → 瀏覽器下載管理器直接接手串流
```

## 4. 架構決策

### 4.1 採 additive endpoint

保留 `POST /api/download` 的 Pydantic JSON request，新增接受 form list 的 `POST /api/download/file`。不讓同一 endpoint 手動判斷 content type，可保留 FastAPI 自動驗證與清楚的 OpenAPI contract。

### 4.2 抽出單一 ZIP response builder

將目前 endpoint 內的 ID 過濾、路徑去重、重名處理與 `StreamingResponse` 建立抽為內部 function。JSON 與 form endpoint 只負責輸入 validation，避免兩份規則漂移。

### 4.3 使用 HTML form，而非 Fetch API

HTML form navigation 可讓 `Content-Disposition: attachment` 交給瀏覽器下載管理器。相較 `showSaveFilePicker()`，此方案不綁定 Chromium；相較 GET query，也不受大量 ID 的 URL 長度限制。

### 4.4 隱藏 iframe 保留目前頁面

form target 指向同源隱藏 iframe，避免極端情況下的 JSON error response 導航掉搜尋結果頁。代價是串流開始後無可靠、跨瀏覽器的完成事件；因此 UI 只表示「已開始」，不假裝知道完成時間。

## 5. 預計修改檔案

| 檔案 | 修改 |
|---|---|
| `src/main.py` | 新增 form endpoint，抽出共用下載 response builder，保留 JSON endpoint |
| `src/static/index.html` | 改以動態 form 提交，加入隱藏 iframe與誠實的狀態文字，移除 blob 流程 |

不修改 dependency、索引格式、照片內容、Cloudflare 或 systemd 設定。

## 6. 分階段執行

### Phase 1：後端向下相容介面

1. 以既有 JSON endpoint 行為作為一次性 regression baseline。
2. 抽出接受 `list[int]` 並回傳 `StreamingResponse` 的內部 helper。
3. 讓既有 endpoint 呼叫 helper，不改 request model 與 response contract。
4. 新增接受重複 form `ids` 的 `/api/download/file` endpoint。
5. 驗證 JSON 與 form 兩種輸入得到相同 ZIP 成員與錯誤語意。

### Checkpoint 1

- JSON endpoint contract 不變。
- form endpoint 可由標準 HTML form 呼叫。
- ZIP 去重、命名與串流邏輯只有一份。
- 沒有新增 dependency。

### Phase 2：前端原生下載

1. 為 status 加入 live-region semantics。
2. 新增隱藏 iframe download target。
3. 將 click handler 改為建立並提交暫時 form，每個 hit 使用一個 hidden `ids` input。
4. form 提交後立即清理 DOM、恢復按鈕並顯示「下載已開始」。
5. 移除 fetch、blob 與 object URL 下載邏輯。

### Checkpoint 2

- 點擊後頁面不跳轉，搜尋結果保留。
- 瀏覽器開始處理 attachment，而非等待 blob 完成。
- 按鈕與 status 不再宣稱整段傳輸都在打包。
- 鍵盤點擊與既有 button 行為維持正常。

### Phase 3：品質與 GCP 驗證

1. 執行 Ruff、pre-commit、compileall 與 diff check。
2. 使用一次性隔離 index 驗證 JSON／form endpoint ZIP 成員相同。
3. 在 GCP 經 Cloudflare 點擊一鍵下載，觀察瀏覽器下載管理器與 Network request。
4. 確認下載期間頁面可繼續操作，瀏覽器不等待完整 blob 才顯示下載。
5. 檢查 staged diff 與敏感資訊後建立 fix commit。

## 7. 驗證策略

### 7.1 後端 contract

- 對既有 JSON endpoint POST `{"ids":[...]}`。
- 對新 endpoint POST 重複 form fields。
- 讀取兩個 ZIP，驗證成員名稱、數量、內容與去重結果一致。
- 驗證無有效照片時為 404，非整數 form value 由 FastAPI validation 拒絕。

### 7.2 前端行為

- 靜態確認 click handler 不含 `blob()`、object URL 或 ZIP fetch。
- 確認 form method、action、target 與 repeated `ids` 正確。
- 確認提交後暫時 form 從 DOM 移除，搜尋結果不變。
- GCP 實際點擊，確認瀏覽器下載 UI 在完整傳輸結束前出現。

### 7.3 資源行為

- 後端仍以 1 MiB block 讀檔並用 `NO_COMPRESSION_64` 串流。
- 前端不持有完整 ZIP blob，因此瀏覽器 JS heap 不隨 ZIP 總量線性增加。
- 本次不以本機傳輸速度作效能結論，遠端 GCP 行為才是 UX 驗收依據。

## 8. Commit 規劃

單一功能 commit：

```text
fix: 一鍵下載長時間停在打包中

問題: 前端使用 res.blob() 緩衝完整 ZIP，導致遠端傳輸期間一直顯示打包中，且瀏覽器記憶體隨下載大小增加。
解法: 新增向下相容的 form 下載入口，改由瀏覽器下載管理器直接接手後端 ZIP 串流。
```

不執行 push、merge 或 rebase。

## 9. 風險與因應

| 風險 | 影響 | 因應 |
|---|---|---|
| form endpoint 與 JSON endpoint 邏輯漂移 | 兩種下載結果不同 | 共用單一 response builder |
| error response 導航掉頁面 | 搜尋結果遺失 | 使用隱藏 iframe target |
| 隱藏 iframe 無跨瀏覽器完成事件 | UI 無法精確顯示完成 | 只顯示「已開始」，進度交給瀏覽器 |
| 大量 ID 超過 URL 限制 | 下載失敗 | 使用 POST form body，不採 GET query |
| 誤以為此修改提升頻寬 | 期待錯置 | 文件與交付明確區分啟動體感和總傳輸時間 |

## 10. 待確認事項與推薦答案

1. 保留 JSON endpoint 並新增 form endpoint：推薦「是」。
2. 下載 target 使用隱藏 iframe：推薦「是」，優先保護目前搜尋頁。
3. 本次不為罕見 iframe error 增加 prepare token／狀態 API：推薦「是」，維持最小修改。
4. 本次不顯示百分比：推薦「是」，交由瀏覽器下載管理器呈現可取得的進度。
