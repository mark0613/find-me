import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm

from src.face import extract_faces

IMG_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff'}
DEFAULT_INDEX_DIR = Path('data/index')


def list_images(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob('*') if p.suffix.lower() in IMG_EXTS)


def read_image(path: Path) -> np.ndarray | None:
    data = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def build_index(photos_dir: Path, out_dir: Path) -> None:
    images = list_images(photos_dir)
    print(f'[INFO] 找到 {len(images)} 張照片')

    embeddings: list[np.ndarray] = []
    meta: list[dict] = []
    skipped = 0

    for path in tqdm(images, desc='抽取向量'):
        img = read_image(path)
        if img is None:
            print(f'[WARN] 讀不到圖片，跳過: {path}')
            skipped += 1
            continue
        try:
            faces = extract_faces(img)
        except Exception as e:
            print(f'[WARN] 偵測失敗，跳過 {path}: {e}')
            skipped += 1
            continue
        for i, f in enumerate(faces):
            embeddings.append(f.normed_embedding.astype('float32'))
            meta.append({'path': str(path.resolve()), 'face': i})

    if not embeddings:
        print('[ERROR] 沒抽到任何人臉，請檢查照片目錄')
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    np.save(out_dir / 'embeddings.npy', np.vstack(embeddings))
    with open(out_dir / 'meta.json', 'w', encoding='utf-8') as fp:
        json.dump(meta, fp, ensure_ascii=False)

    print(
        f'[DONE] 照片 {len(images)} 張、臉 {len(meta)} 張、跳過 {skipped} 張，索引已存到 {out_dir}/'
    )


def main():
    ap = argparse.ArgumentParser(description='掃描照片海並建立人臉向量索引')
    ap.add_argument('--photos', required=True, type=Path, help='照片海目錄')
    ap.add_argument('--out', default=DEFAULT_INDEX_DIR, type=Path, help='索引輸出目錄')
    args = ap.parse_args()

    if not args.photos.is_dir():
        ap.error(f'照片目錄不存在: {args.photos}')
    build_index(args.photos, args.out)


if __name__ == '__main__':
    main()
