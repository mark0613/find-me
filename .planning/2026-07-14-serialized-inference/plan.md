# 推理移出 Event Loop 與單一並行限制實作計畫

## 1. 概述

目前 `/api/search` 是 `async` endpoint，但會直接同步執行 `engine.search()`；人臉偵測與向量搜尋期間會占住 Uvicorn 的 event loop，使同一 worker 無法及時處理縮圖、下載與其他 HTTP 請求。

本次以最小修改達成兩件事：

1. 將 `engine.search()` 交由 Starlette/FastAPI 使用的 worker thread 執行，讓 event loop 保持可用。
2. 以 process-local `asyncio.Semaphore(1)` 限制同一程序同時只執行一個搜尋推理，其餘搜尋請求非同步等待名額。

不建立背景工作佇列、不改 API contract、不增加 dependency，也不調整 Uvicorn worker 數量。

## 2. 現況與目標流程

```text
POST /api/search
       │
       ├── event loop：讀取並解碼上傳圖片
       │
       └── await Semaphore(1)
                  │
                  └── worker thread：engine.search()
                              │
                              └── event loop：組裝並回傳結果
```

等待 semaphore 的請求只保留自身 coroutine 與已解碼圖片，不占用推理 thread；縮圖、下載及首頁請求仍可由 event loop／既有 thread pool 繼續處理。

## 3. 架構決策

### 3.1 限制整個 `engine.search()`

semaphore 包住完整 `engine.search()`，包含 InsightFace 推理與 embedding 相似度計算。如此不需讓 `SearchEngine` 或 `FaceAnalysis` 承擔非同步基礎設施責任，也可保證同一程序中的模型及搜尋資料一次只由一個搜尋工作使用。

### 3.2 使用 async semaphore

採用 `asyncio.Semaphore(1)`，等待中的請求會讓出 event loop；不使用同步 semaphore，避免等待鎖本身再次阻塞 event loop。

此限制是 process-local。依目前單一 Uvicorn worker 設定，全服務同時只會有一個推理；未來若增加 worker，每個程序會各有一個名額及一份模型，屆時需重新評估記憶體與總並行數。

### 3.3 使用既有框架的 threadpool bridge

透過 `starlette.concurrency.run_in_threadpool()` 執行同步的 `engine.search()`，沿用 FastAPI/Starlette 既有的 AnyIO thread pool 與 context propagation，不自行建立或管理 `ThreadPoolExecutor`。

### 3.4 保持錯誤與回應相容

- 圖片無法解碼仍回傳 400。
- `NoFaceError` 跨 thread 傳回後仍映射為 422。
- 成功回應的 JSON 欄位、排序與分數格式不變。
- 不額外加入 429、503 或排隊 timeout；超出容量的搜尋會等待。

## 4. 預計修改檔案

- `src/main.py`：新增單一推理 semaphore，並將 `engine.search()` 改為在取得名額後透過 thread pool await。

預期不修改 `src/face.py`、`src/search_engine.py`、前端、dependency、systemd 或 Cloudflare 設定。

## 5. 實作步驟

1. 在 `src/main.py` 宣告 process-local、容量為 1 的 async semaphore。
2. 在搜尋 endpoint 通過圖片驗證後，以 `async with` 取得推理名額。
3. 透過 `run_in_threadpool()` 執行既有 `engine.search(img, threshold=threshold)`。
4. 保留現有例外轉換及回應組裝邏輯。
5. 執行格式、lint、語法與 diff 檢查。
6. 使用一次性並行驗證 harness，將搜尋替換成可控的同步阻塞函式，確認 event loop 未被阻塞且 active search peak 為 1。
7. 驗證完成後建立一個原子 fix commit。

## 6. 驗收與驗證

### 驗收條件

- 三個以上同時抵達的搜尋請求中，`engine.search()` 的同時執行數最大為 1。
- 推理工作執行期間，event loop 上的獨立 heartbeat coroutine 能持續取得執行時間。
- 後續搜尋會等待前一個搜尋結束，不主動回傳 429、502 或 503。
- 既有 400、422 與成功 JSON contract 不變。
- 不新增 dependency、測試檔或不相關修改。

### 本機驗證

依專案規範不新增測試檔；本機只驗證並行語意，不用高規格電腦進行效能壓測：

```bash
uv run ruff format src/main.py
uv run ruff check src/main.py
uv run python -m compileall -q src
git diff --check
```

另以一次性腳本同時呼叫至少三次搜尋，使用短暫阻塞的 fake `engine.search()` 記錄 active peak，並以 heartbeat 證明 event loop 在推理期間仍可運作。此驗證不載入模型、不修改正式 index，也不新增 tracked 測試檔。

### GCP 驗證

部署並重啟服務後：

- 同時送出兩個搜尋，確認第二個等待且兩者最後均取得既有格式的回應。
- 第一個搜尋推理期間呼叫首頁或已快取縮圖，確認服務仍可回應。
- 檢查 `journalctl -u find-me`，確認沒有程序崩潰、OOM 或非預期 5xx。

GCP 實際負載與延遲由使用者部署後驗證；本次 commit 前不把本機硬體壓測作為完成條件。

## 7. Commit 規劃

完成實作及本機行為驗證後建立一個原子 fix commit：

```text
fix: 人臉搜尋期間其他請求無法回應

問題: 搜尋 endpoint 在 event loop 同步執行 CPU 密集的人臉推理，推理期間同一 worker 無法處理其他 HTTP 請求，且多筆搜尋缺少明確的推理並行限制。
解法: 將搜尋工作移至框架 thread pool，並以容量 1 的 async semaphore 讓多筆推理依序執行，維持 event loop 可回應其他請求。
```

不執行 push、merge 或 rebase。

## 8. 風險與因應

| 風險 | 影響 | 因應 |
|---|---|---|
| 瞬間大量搜尋在 semaphore 前排隊 | 後段請求延遲增加，極端時可能遇到 Cloudflare timeout | 本次依需求選擇等待而非拒絕；活動前在目標 VM 量測單次推理時間 |
| 每個等待請求保留已解碼圖片 | 大量高解析上傳仍會占用記憶體 | 本次只處理推理並行；現有圖片縮放在模型抽取階段執行，若實測仍有壓力再另案限制上傳大小或提早縮圖 |
| 未來增加 Uvicorn workers | 總推理並行數與模型份數等於 worker 數 | 維持目前單 worker；增加 worker 前重新評估記憶體與 semaphore 策略 |
| thread 中的底層 native code 不可被 coroutine cancellation 強制中止 | 用戶中斷後該次推理仍可能跑完 | 保持單次推理為有界工作；不自行使用不安全的 thread 終止手段 |

## 9. 待確認事項與推薦答案

本次沒有需要額外裁決的問題；計畫採用以下已對齊方案：

1. 推理並行固定為 1。
2. 超過容量時等待，不新增 429／503。
3. Uvicorn 維持單一 worker。
4. 不進行本機效能壓測，只驗證並行與 event loop 行為。
