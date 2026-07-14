# 推理移出 Event Loop 與單一並行限制任務清單

## Task 1：序列化搜尋推理並移至 Thread Pool

**描述：** 在 `src/main.py` 建立容量為 1 的 process-local async semaphore；搜尋 endpoint 完成圖片讀取與驗證後，先非同步取得名額，再透過 Starlette thread pool 執行既有同步 `engine.search()`。保留原有錯誤映射與成功回應格式。

**驗收條件：**

- [ ] 同一程序中最多只有一個 `engine.search()` 正在執行，其餘搜尋非同步等待。
- [ ] `engine.search()` 不再執行於 Uvicorn event loop thread，推理期間 event loop 仍能處理其他 coroutine。
- [ ] 無效圖片仍回傳 400、找不到人臉仍回傳 422，成功 JSON contract 不變。
- [ ] 不新增 dependency、背景佇列、API 狀態碼或不相關修改。

**驗證方式：**

- [ ] 執行 `uv run ruff format src/main.py`、`uv run ruff check src/main.py`、`uv run python -m compileall -q src` 與 `git diff --check`。
- [ ] 以一次性 fake blocking search 同時觸發至少三個請求，確認 active peak 等於 1。
- [ ] 在 fake search 執行期間記錄 event loop heartbeat，確認 heartbeat 持續前進而非被同步工作阻塞。
- [ ] 檢查 diff，確認既有例外轉換與 response mapping 沒有改變。

**相依：** 無。

**預計檔案：**

- `src/main.py`

**預估規模：** XS（1 個檔案、單一 endpoint 的並行控制）。

## Checkpoint 1：程式與本機行為

- [ ] 格式、lint、語法與 diff 檢查全部通過。
- [ ] deterministic 並行驗證證明 active search peak 為 1。
- [ ] deterministic heartbeat 驗證證明 event loop 未被推理阻塞。
- [ ] 沒有新增 tracked 測試檔或修改正式資料。

## Task 2：建立原子 Commit 並提供 GCP 驗證步驟

**描述：** 審查最終差異及工作樹，確認修改只有本次並行控制後，以符合專案規範且包含「問題／解法」的 fix commit 保存進度；回報 GCP 重啟及實機併發驗證命令。

**驗收條件：**

- [ ] commit 只包含本需求必要的 tracked 程式修改。
- [ ] commit header 從問題角度描述，message 明列「問題」與「解法」。
- [ ] 未執行 push、merge 或 rebase。
- [ ] 提供可在 GCP 驗證兩筆搜尋排隊、其他 endpoint 可回應及服務無異常的操作方式。

**驗證方式：**

- [ ] commit 前檢查 `git status --short`、`git diff --check` 與完整 diff。
- [ ] commit 後檢查 `git show --stat --oneline HEAD` 與 `git status --short`。
- [ ] GCP 部署後由使用者檢查 HTTP 結果與 `journalctl -u find-me`。

**相依：** Task 1、Checkpoint 1。

**預計檔案：** 無額外 tracked 檔案。

**預估規模：** XS（驗證、commit 與部署交接）。

## Checkpoint 2：完成

- [ ] 所有驗收條件通過。
- [ ] 搜尋推理不阻塞 event loop 且同時最多執行一筆。
- [ ] 已建立原子 fix commit。
- [ ] 已提供 GCP 重啟與實機驗證方式。
