import os
from datetime import datetime
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from stream_zip import NO_COMPRESSION_64, MemberFile, stream_zip

from src.search_engine import NoFaceError, SearchEngine
from src.thumbnail_cache import ThumbnailCache, ThumbnailEncodeError, ThumbnailReadError

INDEX_DIR = Path(os.environ.get('FINDME_INDEX_DIR', 'data/index'))
STATIC_DIR = Path(__file__).parent / 'static'
THUMB_MAX_SIDE = 480
READ_BLOCK_BYTES = 1024 * 1024

app = FastAPI(title='find-me')
engine = SearchEngine(INDEX_DIR)
thumbnail_cache = ThumbnailCache(INDEX_DIR / 'thumbs', max_side=THUMB_MAX_SIDE)


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
    try:
        cache_path = thumbnail_cache.get_or_create(path)
    except ThumbnailReadError as error:
        raise HTTPException(404, str(error)) from error
    except ThumbnailEncodeError as error:
        raise HTTPException(500, str(error)) from error
    return FileResponse(cache_path, media_type='image/jpeg')


@app.get('/api/photo/{face_id}')
def photo(face_id: int):
    return FileResponse(_photo_path(face_id))


class DownloadRequest(BaseModel):
    ids: list[int]


def _iter_file_blocks(path: Path) -> Iterator[bytes]:
    with path.open('rb') as file:
        while block := file.read(READ_BLOCK_BYTES):
            yield block


def _zip_members(files: list[tuple[Path, str]]) -> Iterator[MemberFile]:
    for path, name in files:
        yield (
            name,
            datetime.fromtimestamp(path.stat().st_mtime),
            0o600,
            NO_COMPRESSION_64,
            _iter_file_blocks(path),
        )


@app.post('/api/download')
def download(req: DownloadRequest):
    paths: dict[Path, None] = {}
    for face_id in req.ids:
        if not 0 <= face_id < len(engine.meta):
            continue
        path = Path(engine.meta[face_id]['path'])
        if path.exists():
            paths[path] = None
    if not paths:
        raise HTTPException(404, '沒有可下載的照片')

    files: list[tuple[Path, str]] = []
    used = set()
    for path in paths:
        name, n = path.name, 1
        while name in used:
            name = f'{path.stem}_{n}{path.suffix}'
            n += 1
        used.add(name)
        files.append((path, name))

    headers = {'Content-Disposition': 'attachment; filename="find-me-photos.zip"'}
    return StreamingResponse(
        stream_zip(_zip_members(files)),
        media_type='application/zip',
        headers=headers,
    )
