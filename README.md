# Find Me

從照片海撈出自己的本地人臉檢索系統。上傳一張自己的照片，找出照片海中所有包含你的照片。

核心技術：[InsightFace](https://github.com/deepinsight/insightface)（buffalo_l）抽取 512 維臉部向量 + 餘弦相似度比對。全程本地運行，照片不外流。

## 安裝

需求：Python 3.11、[uv](https://docs.astral.sh/uv/)

```bash
uv sync
```

第一次執行時會自動下載 buffalo_l 模型（約 326MB）到 `~/.insightface/models/`。

## 使用

### 1. 建立索引（一次性）

把照片海放在任意目錄，執行：

```bash
uv run python -m src.build_index --photos "D:\你的照片目錄"
```

索引會存到 `data/index/`（只存向量與照片路徑，不複製照片）。

若只是整個照片根目錄搬到新位置，保留原本的子目錄結構後可直接重新連結既有 index，不需重跑人臉辨識：

```bash
uv run python -m src.relink_index /srv/find-me/photos
```

指令固定更新 `data/index/meta.json`，寫入前會確認 embeddings 筆數與所有新照片路徑，並將原檔備份為 `meta.json.bak-N`。完成後需重新啟動網站。若照片本身有改名或變更子目錄結構，仍需重新建立 index。

### 2. 啟動網頁

```bash
uv run python main.py
```

開啟 <http://127.0.0.1:8613>，上傳一張自己的照片即可搜尋。

## 門檻調校

相似度門檻預設 0.40（頁面上可即時調整）：

- 撈到的照片太少 → 調低（0.35 左右）
- 混入別人的照片 → 調高（0.45 左右）
- 亞洲臉孔用 buffalo_l 通常 0.38～0.42 最穩

## 注意事項

- 預設用 CPU 推理；要用 GPU 改裝 `onnxruntime-gpu`（需對應 CUDA/cuDNN），程式會自動偵測並優先使用
- buffalo_l 模型授權為**非商業研究用途**，自用、整理個人照片沒問題；要做對外商業服務需向 InsightFace 購買授權或改用 Apache 2.0 的替代模型（如 AuraFace）
