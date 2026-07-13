import hashlib
import os
import tempfile
from pathlib import Path
from threading import BoundedSemaphore

import cv2
import numpy as np

CACHE_VERSION = '1'


class ThumbnailReadError(Exception):
    pass


class ThumbnailEncodeError(Exception):
    pass


class ThumbnailCache:
    def __init__(
        self,
        cache_dir: Path,
        *,
        max_side: int = 480,
        jpeg_quality: int = 85,
        max_concurrent: int = 8,
    ):
        self.cache_dir = cache_dir
        self.max_side = max_side
        self.jpeg_quality = jpeg_quality
        self._generation_slots = BoundedSemaphore(max_concurrent)

    def get_or_create(self, source: Path) -> Path:
        source = source.resolve()
        cache_path = self._cache_path(source)
        if cache_path.is_file():
            return cache_path

        with self._generation_slots:
            cache_path = self._cache_path(source)
            if cache_path.is_file():
                return cache_path
            self._generate(source, cache_path)
            return cache_path

    def _cache_path(self, source: Path) -> Path:
        stat = source.stat()
        key = '\0'.join(
            (
                CACHE_VERSION,
                str(source),
                str(stat.st_size),
                str(stat.st_mtime_ns),
                str(self.max_side),
                str(self.jpeg_quality),
            )
        )
        digest = hashlib.sha256(key.encode()).hexdigest()
        return self.cache_dir / f'{digest}.jpg'

    def _generate(self, source: Path, cache_path: Path) -> None:
        image = cv2.imdecode(np.fromfile(source, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ThumbnailReadError('讀不到照片')

        height, width = image.shape[:2]
        scale = self.max_side / max(height, width)
        if scale < 1.0:
            size = (max(1, int(width * scale)), max(1, int(height * scale)))
            image = cv2.resize(image, size)

        ok, encoded = cv2.imencode(
            '.jpg',
            image,
            [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality],
        )
        if not ok:
            raise ThumbnailEncodeError('縮圖編碼失敗')

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.cache_dir,
                prefix=f'.{cache_path.stem}-',
                suffix='.tmp',
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(encoded)
            os.replace(temp_path, cache_path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
