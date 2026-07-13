# 縮圖併發限制與持久化快取任務清單

## Task 1：建立縮圖持久化快取核心

**描述：** 新增 `src/thumbnail_cache.py`，封裝來源狀態 cache key、cache hit fast path、最多 8 個並行 cache miss、OpenCV 縮圖生成，以及同目錄暫存檔與原子替換。快取固定置於呼叫端提供的 index cache directory，不新增第三方 dependency。

**驗收條件：**

- [ ] 同一路徑、size、mtime 與縮圖設定得到相同 SHA-256 cache path；同張照片的不同 face ID 可共用快取。
- [ ] cache hit 不讀取或解碼原始照片；cache miss 的完整高記憶體區段最多同時執行 8 個。
- [ ] 來源或縮圖設定變更後使用新 key；JPEG 只在完整寫入後原子出現在正式路徑。
- [ ] 任何解碼、編碼或寫入失敗都不留下正式半成品或暫存檔。

**驗證方式：**

- [ ] 使用 `tmp/` 一次性 fixture 驗證首次產生、再次命中、同源共用、來源變更失效與不可讀圖片。
- [ ] 使用至少 32 個並行 miss 的一次性計數 harness，確認 active generation peak 為 8。
- [ ] 驗證所有產物可由 OpenCV 解碼、最大邊為 480、沒有零位元檔或 `.tmp` 殘留。
- [ ] 執行 `uv run ruff format src` 與 `uv run ruff check src`。

**相依：** 無。

**預計檔案：**

- `src/thumbnail_cache.py`

**預估規模：** S（1 個新模組）。

## Task 2：整合縮圖 API 並文件化快取維運

**描述：** 在 `src/main.py` 使用 `INDEX_DIR / 'thumbs'` 初始化縮圖快取服務，將 `/api/thumb/{face_id}` 的解碼細節替換為 `get_or_create()` 與 `FileResponse`，保留既有 HTTP contract；在 README 說明快取位置、lazy 建立及安全清空後自動重建。

**驗收條件：**

- [ ] `GET /api/thumb/{face_id}` 的 URL、`image/jpeg` 與既有 404／500 語意不變。
- [ ] 有效 ID 首次建立 cache，後續相同來源直接由 `FileResponse` 回傳同一 JPEG。
- [ ] 自訂 `FINDME_INDEX_DIR` 時，快取位於該 index 的 `thumbs/`，且所有生成物維持 Git ignored。
- [ ] README 清楚說明快取不需預建、可手動清空、會自動重建，且不引用未版控文件。

**驗證方式：**

- [ ] 使用隔離 index 實際啟動服務並呼叫有效、無效、同源不同 face ID 與不可讀來源。
- [ ] 檢查 response status、media type、content length、JPEG 可讀性與第二次請求不改寫 cache。
- [ ] 執行 `uv run ruff format src`、`uv run ruff check src` 與 `git diff --check`。

**相依：** Task 1。

**預計檔案：**

- `src/main.py`
- `README.md`

**預估規模：** S（2 個檔案）。

## Checkpoint 1：核心與 HTTP 行為

- [ ] semaphore、cache key、失效與 atomic write 的隔離驗證全部通過。
- [ ] 縮圖 API contract 不變，且快取命中不再完整解碼原圖。
- [ ] 沒有新增 dependency、測試檔或 Git tracked cache。

## Task 3：完成資源壓力與 GCP 端到端驗證

**描述：** 在完成本機隔離驗證後部署至升級後的 GCP，使用實際搜尋結果進行 cold-cache 與 warm-cache 壓力走查，比較服務 restart、OOM、記憶體與縮圖回應；全部通過後建立單一 fix commit。

**驗收條件：**

- [ ] 32 張以上 cold-cache 縮圖同時載入時，服務不被 OOM killer 終止，`NRestarts` 不增加。
- [ ] 同一批 warm-cache 縮圖可正常顯示，不再因 origin 程序消失出現一批 Cloudflare 502。
- [ ] 驗證期間沒有修改正式 index metadata、原始照片或其他不相關程式碼。
- [ ] commit 僅包含本功能必要檔案，fix message 具備「問題」與「解法」。

**驗證方式：**

- [ ] 驗證前後記錄 `systemctl show find-me --property=MainPID --property=NRestarts`。
- [ ] 檢查 `journalctl -u find-me` 與 kernel log，確認沒有新的 `oom-kill`。
- [ ] 比較 cold-cache／warm-cache 回應時間、程序 RSS 與 cache 檔案數量。
- [ ] 最終執行 Ruff、`git diff --check`、`git status` 與 staged diff 檢查。

**相依：** Task 1、Task 2、使用者完成 GCP 規格升級。

**預計檔案：** 無新增 tracked file；只使用已忽略的驗證 fixture 與 GCP runtime cache。

**預估規模：** S（部署與實機驗證）。

## Checkpoint 2：完成

- [ ] 所有規格驗收條件通過。
- [ ] 冷快取峰值受控，暖快取不重複解碼原圖。
- [ ] 應用程序不再因大量縮圖請求被 OOM killer 終止。
- [ ] 已建立 `fix: 載入大量縮圖時服務記憶體耗盡` 原子 commit，未執行 push、merge 或 rebase。
