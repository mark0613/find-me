# 規格：一鍵下載改用瀏覽器原生串流

## 1. 背景

目前前端以 `fetch('/api/download')` 取得 ZIP，接著執行 `await res.blob()`。瀏覽器必須先把整個 ZIP 下載到記憶體，完成後才建立 object URL 並觸發下載，因此遠端傳輸期間按鈕會一直顯示「打包中…」。本機透過 loopback 傳輸時不明顯，但經 GCP 與 Cloudflare Tunnel 下載較大檔案時，使用者無法分辨伺服器處理與網路傳輸，也看不到瀏覽器原生下載狀態。

後端現有實作已使用 `stream_zip`、`NO_COMPRESSION_64` 與 `StreamingResponse`，不會先將完整 ZIP 放入記憶體。本次問題集中在前端消費串流的方式。

## 2. 目標

- 點擊「一鍵下載」後，立即把 ZIP 回應交給瀏覽器下載管理器。
- 移除前端對完整 ZIP 的 `blob()` 緩衝，避免瀏覽器記憶體隨下載總量增加。
- UI 不再把遠端傳輸時間誤稱為「打包中」。
- 保留既有 JSON `POST /api/download` contract，避免破壞既有呼叫者。
- 保留同照片去重、重名加序號、遺失檔案跳過及不壓縮串流行為。

## 3. 非目標

- 不宣稱縮短 ZIP 的實際網路傳輸時間；總時間仍受 GCP、Cloudflare 與使用者網路頻寬影響。
- 不預先建立 ZIP、不寫入伺服器暫存 ZIP，也不新增下載工作佇列。
- 不加入下載進度百分比；串流回應目前沒有完整 `Content-Length`。
- 不調整 Cloudflare Tunnel、systemd、VM 規格或原始照片存放方式。
- 不新增第三方 dependency 或測試檔。

## 4. API contract

### 4.1 保留既有程式化介面

`POST /api/download`

- Request content type：`application/json`
- Request body：`{"ids": [1, 2, 3]}`
- Success：`200 application/zip`
- Header：`Content-Disposition: attachment; filename="find-me-photos.zip"`
- Error：沒有可下載照片時維持 `404` 與既有 detail。

### 4.2 新增瀏覽器原生下載介面

`POST /api/download/file`

- Request content type：`application/x-www-form-urlencoded`
- Request body：重複的 `ids` 欄位，例如 `ids=1&ids=2&ids=3`。
- FastAPI 在 API 邊界將每個值驗證為整數。
- Success 與 error 語意沿用既有下載介面。
- 兩個 endpoint 共用同一個 ZIP response builder，禁止複製去重、命名與串流邏輯。

新增 endpoint 而不改變既有 endpoint，可讓目前 JSON 呼叫者繼續運作，前端則使用 HTML form navigation 取得瀏覽器原生下載行為。

## 5. 前端互動

1. 頁面建立一個隱藏、具固定 `name` 的 iframe 作為下載 target，避免錯誤回應取代搜尋結果頁。
2. 點擊按鈕時建立暫時性的 `<form method="post">`，action 指向 `/api/download/file`，target 指向隱藏 iframe。
3. 每個目前命中的 face ID 建立一個 `name="ids"` 的 hidden input。
4. 提交 form 後立即移除暫時 form；瀏覽器接手 attachment response。
5. 不再呼叫 `fetch()`、`res.blob()`、`URL.createObjectURL()` 或 `URL.revokeObjectURL()`。
6. 按鈕不在整個傳輸期間保持 disabled；提交完成後恢復可用。
7. `#status` 顯示「下載已開始，請查看瀏覽器下載進度」，並具有 `role="status"`／`aria-live="polite"`。

## 6. 錯誤行為

- 前端只在 `hits` 非空時顯示下載按鈕，因此正常路徑一定會送出至少一個 ID。
- 後端仍忽略超出範圍或照片已移走的 ID；全部無效時回傳 404。
- 下載 target 使用隱藏 iframe 後，罕見的 HTTP error response 不會取代目前頁面，但也不保證能由瀏覽器一致地回報到主頁 UI。
- 既有 JSON endpoint 保留完整的程式化錯誤回應，可用於診斷。

## 7. 安全與資源限制

- 客戶端只送 face ID，不能直接指定檔案路徑；實際路徑仍由 server-side index metadata 解析。
- 新 endpoint 必須驗證 form ID 為整數，無效 ID 不得造成任意檔案讀取。
- ZIP 持續採逐檔、逐區塊讀取；不得將完整照片集合或 ZIP 載入記憶體。
- 動態 form 提交至同源相對路徑，會沿用現有 Cloudflare Access session。

## 8. 驗收標準

- [ ] 點擊一鍵下載後，瀏覽器下載管理器在 ZIP 完整傳完前就開始處理 attachment。
- [ ] 前端程式不再出現 `res.blob()` 或 ZIP object URL。
- [ ] UI 不再長時間顯示「打包中」，而是明確告知下載已交給瀏覽器。
- [ ] 既有 JSON endpoint 的 request／response／error contract 不變。
- [ ] 新 form endpoint 產生的 ZIP 與既有 endpoint 內容規則一致。
- [ ] 多張臉指向同一照片時仍只打包一次，重名仍自動加序號。
- [ ] Ruff、pre-commit、`git diff --check` 與一次性 API 驗證通過。
- [ ] GCP 經 Cloudflare 實測時，Network request 持續傳輸期間不再卡住 UI，也不再由瀏覽器額外保留完整 ZIP blob。

## 9. 待確認事項與推薦答案

### 9.1 是否保留既有 JSON endpoint

推薦：保留，並新增 `/api/download/file`。這是向下相容的最小修改，也能讓 CLI 或未來其他程式繼續使用 JSON contract。

### 9.2 原生下載 endpoint 發生 404 時如何呈現

推薦：以隱藏 iframe 保護目前頁面，接受罕見的 404 不一定能顯示在主頁；server log 與既有 JSON endpoint 仍可診斷。若要求所有瀏覽器都在主頁顯示下載串流中的後端錯誤，就需要額外的 prepare token／狀態 API，超出本次最小修正。

### 9.3 是否顯示下載百分比

推薦：本次不做。ZIP 是即時串流且沒有預先計算的總 Content-Length，交由瀏覽器顯示已下載量即可。
