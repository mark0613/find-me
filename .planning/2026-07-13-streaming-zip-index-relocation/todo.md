# Streaming ZIP 與 index 路徑重新連結任務清單

## Task 1：將照片 ZIP 改為串流回傳

**描述：** 新增並鎖定 `stream-zip`，以 `stream_zip()`、固定大小檔案 iterator 和 FastAPI `StreamingResponse` 取代 `BytesIO` 完整緩衝，同時保留現有下載 API 與 ZIP 內容規則。

**驗收條件：**

- [ ] `/api/download` 不在 RAM 或磁碟建立完整 ZIP，開始產生後即可逐 chunk 回傳。
- [ ] 記憶體用量不隨整包 ZIP 容量等比例增加；`NO_COMPRESSION_64` 僅緩衝目前處理的單一照片。
- [ ] 重複照片去重、同名編號、遺失照片跳過與全部無效回傳 404 的行為不變。
- [ ] ZIP 保持不壓縮並支援總容量超過 4 GiB 的 Zip64。

**驗證方式：**

- [ ] 執行專案 lint / format 檢查。
- [ ] 實際呼叫 API，使用標準 ZIP reader 驗證檔名、內容、去重與可解壓。
- [ ] 觀察第一批 response chunk 在完整 ZIP 尚未產生前送出，且程序記憶體不隨 ZIP 總容量等比例增加。

**相依：** 無。

**預計檔案：**

- `pyproject.toml`
- `uv.lock`
- `src/main.py`

**預估規模：** M（3 個檔案，一個 API 行為切片）。

## Task 2：新增 index 路徑重新連結 CLI

**描述：** 新增 `src/relink_index.py`，固定操作 `data/index`，只接收一個 positional argument 作為新照片根目錄並更新 `meta.json` 路徑，不重算 embeddings；包含跨平台舊 root 推導、完整驗證、編號備份與原子寫入。

**驗收條件：**

- [ ] 可用單一 positional argument 保留相對目錄結構並重寫所有 metadata path。
- [ ] index 固定使用 `data/index`，共同舊 root 從既有 metadata 路徑推導。
- [ ] 支援 Windows-to-Linux 路徑；不依賴執行平台解析舊路徑。
- [ ] 任一輸入、筆數或目標檔案驗證失敗時不修改 `meta.json`；成功時保留不覆蓋的備份。

**驗證方式：**

- [ ] 使用隔離 fixture 驗證 Windows 舊 root 推導、Linux 新路徑組裝、重複照片 metadata 與巢狀子目錄。
- [ ] 驗證成功、無法推導共同 root、缺少目標照片、embeddings/meta 筆數不一致四條路徑。

**相依：** 無。

**預計檔案：**

- `src/relink_index.py`

**預估規模：** S（1 個新 CLI 模組）。

## Checkpoint 1：核心功能

- [ ] Streaming ZIP 可下載並解壓，既有 API contract 不變。
- [ ] 重新連結 CLI 在任何失敗情境都不破壞原始 index。
- [ ] 正式 `data/index/meta.json` 未被驗證流程修改。

## Task 3：補充使用文件與完成整體驗證

**描述：** 在 README 加入重新連結既有 index 路徑的指令與注意事項，完成 lint、啟動與 HTTP 功能走查，並依功能拆成兩個原子 commit。

**驗收條件：**

- [ ] README 說明先放妥照片，再以單一 positional argument 重新連結 index。
- [ ] README 清楚說明固定 index、舊 root 自動推導、備份位置與不需要重跑人臉索引。
- [ ] 兩項功能驗證通過，commit 內容沒有混入無關修改。

**驗證方式：**

- [ ] 依 README 指令用隔離 fixture 完整走查一次。
- [ ] 執行 lint / format、應用啟動檢查及實際 HTTP 下載。
- [ ] 檢查 `git diff`、`git status` 與兩個 commit 的檔案邊界。

**相依：** Task 1、Task 2。

**預計檔案：**

- `README.md`

**預估規模：** S（1 個文件與整體驗證）。

## Checkpoint 2：完成

- [ ] 所有 acceptance criteria 通過。
- [ ] 無完整 ZIP 記憶體緩衝或暫存檔。
- [ ] 原始 index 與照片未被測試流程破壞。
- [ ] 完成兩個已驗證的原子 commit，未 push。
