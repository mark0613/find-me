# 一鍵下載原生串流任務清單

## Task 1：新增向下相容的 form 下載入口

**描述：** 在 `src/main.py` 將既有 ID 過濾、照片去重、重名處理與 ZIP `StreamingResponse` 建立抽為共用 helper；保留 JSON `POST /api/download`，另新增接受 repeated form `ids` 的 `POST /api/download/file`。

**驗收條件：**

- [ ] 既有 JSON request model、URL、成功 response 與 404 語意不變。
- [ ] form endpoint 將每個 `ids` 驗證為整數，並回傳相同 attachment stream。
- [ ] 兩個 endpoint 共用同一份下載規則，沒有複製去重或命名程式碼。
- [ ] 不新增 dependency，仍使用 `NO_COMPRESSION_64` 與逐區塊讀檔。

**驗證方式：**

- [ ] 使用一次性 fixture 分別呼叫 JSON 與 form endpoint，解開結果並比較 ZIP 成員與內容。
- [ ] 驗證重複照片、同名照片、無效 ID、全部遺失與非整數 form ID。
- [ ] 執行 `uv run ruff format src`、`uv run ruff check src` 與 compileall。

**相依：** 無。

**預計檔案：**

- `src/main.py`

**預估規模：** S（1 個檔案）。

## Task 2：前端改用瀏覽器原生下載

**描述：** 在 `src/static/index.html` 建立隱藏 iframe target，將一鍵下載 click handler 改為動態 form POST repeated face IDs；移除 ZIP fetch、blob 與 object URL，提交後立即恢復按鈕並顯示已交給瀏覽器的狀態。

**驗收條件：**

- [ ] click handler 不再將完整 ZIP 緩衝到 JavaScript memory。
- [ ] form 正確使用 POST、`/api/download/file`、隱藏 iframe target 與 repeated `ids`。
- [ ] 提交後暫時 form 被移除，頁面與搜尋結果不跳轉、不清空。
- [ ] status 語意正確且可由輔助技術感知，按鈕不在整段下載期間 disabled。

**驗證方式：**

- [ ] 靜態搜尋確認不存在 `res.blob()`、ZIP object URL 與舊「打包中」流程。
- [ ] 以有效 hits 觸發下載，檢查 form payload 與 attachment response。
- [ ] 在 GCP 經 Cloudflare 確認下載 UI 在完整 ZIP 傳完前出現，頁面仍可操作。

**相依：** Task 1。

**預計檔案：**

- `src/static/index.html`

**預估規模：** S（1 個檔案）。

## Checkpoint 1：完整下載流程

- [ ] JSON 與 form endpoint 下載內容一致。
- [ ] 原生下載不經過完整 blob。
- [ ] 搜尋、縮圖、單張照片與既有 JSON 下載 contract 無 regression。

## Task 3：完成品質檢查與遠端驗證

**描述：** 完成 formatter、lint、pre-commit、compileall、diff 與敏感資訊檢查；在 GCP／Cloudflare 實際觀察下載啟動與頁面狀態，通過後建立單一 fix commit。

**驗收條件：**

- [ ] 所有靜態與功能級檢查通過。
- [ ] GCP 下載開始後不再長時間停留「打包中」。
- [ ] 瀏覽器下載管理器直接接手串流；總傳輸時間仍如實反映網路速度。
- [ ] commit 只包含本次必要檔案，message 具備「問題」與「解法」。

**驗證方式：**

- [ ] 執行 Ruff、pre-commit、compileall 與 `git diff --check`。
- [ ] 檢查 browser Network 與下載管理器的啟動時序。
- [ ] 檢查 staged diff、Git status 與敏感資訊掃描。

**相依：** Task 1、Task 2、可使用的 GCP 部署環境。

**預計檔案：** 無新增 tracked file。

**預估規模：** XS（驗證與提交）。

## Checkpoint 2：完成

- [ ] 所有規格驗收條件通過。
- [ ] 已建立 `fix: 一鍵下載長時間停在打包中` commit。
- [ ] 未執行 push、merge 或 rebase。
