import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.face import extract_faces


class IndexNotFoundError(Exception):
    pass


class NoFaceError(Exception):
    pass


@dataclass
class Hit:
    id: int
    score: float
    path: str


class SearchEngine:
    def __init__(self, index_dir: Path):
        emb_path = index_dir / 'embeddings.npy'
        meta_path = index_dir / 'meta.json'
        if not emb_path.exists() or not meta_path.exists():
            raise IndexNotFoundError(
                f'索引不存在於 {index_dir}/，請先執行: python -m src.build_index --photos <照片目錄>'
            )
        self.embeddings: np.ndarray = np.load(emb_path)
        with open(meta_path, encoding='utf-8') as fp:
            self.meta: list[dict] = json.load(fp)

    def search(self, query_img: np.ndarray, threshold: float = 0.4) -> list[Hit]:
        faces = extract_faces(query_img)
        if not faces:
            raise NoFaceError('查詢照片裡偵測不到人臉')
        largest = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        q = largest.normed_embedding.astype('float32')

        scores = self.embeddings @ q
        best_per_photo: dict[str, Hit] = {}
        for idx in np.nonzero(scores >= threshold)[0]:
            path = self.meta[idx]['path']
            score = float(scores[idx])
            if path not in best_per_photo or score > best_per_photo[path].score:
                best_per_photo[path] = Hit(id=int(idx), score=score, path=path)

        return sorted(best_per_photo.values(), key=lambda h: h.score, reverse=True)
