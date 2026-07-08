import cv2
import numpy as np
from insightface.app import FaceAnalysis

MAX_SIDE = 1920

_app: FaceAnalysis | None = None


def get_app() -> FaceAnalysis:
    global _app
    if _app is None:
        _app = _create_app()
    return _app


def _create_app() -> FaceAnalysis:
    try:
        app = FaceAnalysis(
            name='buffalo_l',
            providers=['CUDAExecutionProvider', 'CPUExecutionProvider'],
        )
        app.prepare(ctx_id=0, det_size=(640, 640))
    except Exception as e:
        print(f'[WARN] GPU 初始化失敗，改用 CPU: {e}')
        app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
        app.prepare(ctx_id=-1, det_size=(640, 640))
    return app


def extract_faces(img: np.ndarray) -> list:
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    return get_app().get(img)
