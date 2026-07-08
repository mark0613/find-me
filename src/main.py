import os
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response

from src.search_engine import NoFaceError, SearchEngine

INDEX_DIR = Path(os.environ.get('FINDME_INDEX_DIR', 'data/index'))
STATIC_DIR = Path(__file__).parent / 'static'
THUMB_MAX_SIDE = 480

app = FastAPI(title='find-me')
engine = SearchEngine(INDEX_DIR)


@app.get('/')
def index_page():
    return FileResponse(STATIC_DIR / 'index.html')


@app.post('/api/search')
async def search(file: UploadFile, threshold: float = Query(0.4, ge=0.0, le=1.0)):
    data = await file.read()
    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, '上傳的檔案不是可讀取的圖片')
    try:
        hits = engine.search(img, threshold=threshold)
    except NoFaceError as e:
        raise HTTPException(422, str(e)) from e
    return [{'id': h.id, 'score': round(h.score, 3), 'filename': Path(h.path).name} for h in hits]


def _photo_path(face_id: int) -> Path:
    if not 0 <= face_id < len(engine.meta):
        raise HTTPException(404, '無此照片')
    path = Path(engine.meta[face_id]['path'])
    if not path.exists():
        raise HTTPException(404, f'照片已不存在: {path.name}，請重建索引')
    return path


@app.get('/api/thumb/{face_id}')
def thumbnail(face_id: int):
    path = _photo_path(face_id)
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(404, '讀不到照片')
    h, w = img.shape[:2]
    scale = THUMB_MAX_SIDE / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise HTTPException(500, '縮圖編碼失敗')
    return Response(content=buf.tobytes(), media_type='image/jpeg')


@app.get('/api/photo/{face_id}')
def photo(face_id: int):
    return FileResponse(_photo_path(face_id))
