import argparse
import json
import ntpath
import os
import posixpath
import shutil
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import numpy as np

INDEX_DIR = Path('data/index')


class RelinkError(Exception):
    pass


def _path_tools(paths: set[str]):
    if all(PureWindowsPath(path).is_absolute() for path in paths):
        return ntpath, PureWindowsPath
    if all(PurePosixPath(path).is_absolute() for path in paths):
        return posixpath, PurePosixPath
    raise RelinkError('index 內的照片路徑不是一致的 Windows 或 Linux 絕對路徑')


def _map_paths(
    paths: set[str],
    old_root: str,
    new_root: Path,
    path_module: Any,
    pure_path: Any,
) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for path in paths:
        relative = pure_path(path_module.relpath(path, old_root))
        if '..' in relative.parts:
            raise RelinkError('index 內有照片不在共同舊根目錄下')
        mapping[path] = new_root.joinpath(*relative.parts)
    return mapping


def build_relinked_metadata(
    metadata: Any,
    new_root: Path,
) -> tuple[list[dict[str, Any]], str, int]:
    if not isinstance(metadata, list) or not metadata:
        raise RelinkError('meta.json 必須是非空陣列')

    paths: set[str] = set()
    for item in metadata:
        if not isinstance(item, dict) or not isinstance(item.get('path'), str):
            raise RelinkError('meta.json 內每筆資料都必須包含字串 path')
        paths.add(item['path'])

    path_module, pure_path = _path_tools(paths)
    try:
        old_root = path_module.commonpath([path_module.dirname(path) for path in paths])
    except ValueError as error:
        raise RelinkError('無法從 index 推導唯一的舊照片根目錄') from error
    if not old_root:
        raise RelinkError('無法從 index 推導舊照片根目錄')

    common_root = pure_path(old_root)
    candidates = [common_root, *common_root.parents]
    matches: list[tuple[str, dict[str, Path]]] = []
    closest_missing: set[Path] | None = None
    for candidate in candidates:
        path_mapping = _map_paths(paths, str(candidate), new_root, path_module, pure_path)
        missing = {target for target in path_mapping.values() if not target.is_file()}
        if not missing:
            matches.append((str(candidate), path_mapping))
        if closest_missing is None or len(missing) < len(closest_missing):
            closest_missing = missing

    if not matches:
        example = min(closest_missing) if closest_missing else new_root
        raise RelinkError(
            f'新根目錄缺少照片或目錄結構不符，最接近的映射仍缺少 '
            f'{len(closest_missing or ())} 張，例如: {example}'
        )
    if len(matches) > 1:
        raise RelinkError('新根目錄可對應多個舊 root，無法唯一判定路徑映射')

    old_root, path_mapping = matches[0]

    relinked = [{**item, 'path': str(path_mapping[item['path']])} for item in metadata]
    return relinked, old_root, len(paths)


def _load_metadata(index_dir: Path) -> tuple[Path, list[dict[str, Any]]]:
    embeddings_path = index_dir / 'embeddings.npy'
    metadata_path = index_dir / 'meta.json'
    if not embeddings_path.is_file() or not metadata_path.is_file():
        raise RelinkError(f'找不到完整 index: {index_dir}')

    try:
        with metadata_path.open(encoding='utf-8') as file:
            metadata = json.load(file)
        embeddings = np.load(embeddings_path, mmap_mode='r', allow_pickle=False)
    except (OSError, ValueError) as error:
        raise RelinkError(f'無法讀取 index: {error}') from error

    if not isinstance(metadata, list):
        raise RelinkError('meta.json 必須是陣列')
    if embeddings.ndim == 0 or embeddings.shape[0] != len(metadata):
        raise RelinkError(
            f'index 筆數不一致: embeddings={embeddings.shape[0] if embeddings.ndim else 0}, '
            f'metadata={len(metadata)}'
        )
    return metadata_path, metadata


def _next_backup_path(metadata_path: Path) -> Path:
    number = 1
    while True:
        backup_path = metadata_path.with_name(f'{metadata_path.name}.bak-{number}')
        if not backup_path.exists():
            return backup_path
        number += 1


def _replace_metadata(metadata_path: Path, metadata: list[dict[str, Any]]) -> Path:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=metadata_path.parent,
            prefix=f'.{metadata_path.name}.',
            suffix='.tmp',
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            json.dump(metadata, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())

        backup_path = _next_backup_path(metadata_path)
        shutil.copy2(metadata_path, backup_path)
        os.replace(temporary_path, metadata_path)
        return backup_path
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def relink_index(new_root: Path, index_dir: Path = INDEX_DIR) -> tuple[str, Path, int, int, Path]:
    new_root = new_root.resolve()
    if not new_root.is_dir():
        raise RelinkError(f'新照片根目錄不存在: {new_root}')

    metadata_path, metadata = _load_metadata(index_dir)
    relinked, old_root, photo_count = build_relinked_metadata(metadata, new_root)

    backup_path = _replace_metadata(metadata_path, relinked)
    return old_root, new_root, len(metadata), photo_count, backup_path


def main():
    parser = argparse.ArgumentParser(description='將既有 index 重新連結到新的照片根目錄')
    parser.add_argument('photos', type=Path, help='新的照片根目錄')
    args = parser.parse_args()

    try:
        old_root, new_root, metadata_count, photo_count, backup_path = relink_index(args.photos)
    except (OSError, RelinkError) as error:
        parser.error(str(error))

    print(f'[INFO] 舊照片根目錄: {old_root}')
    print(f'[INFO] 新照片根目錄: {new_root}')
    print(f'[INFO] 照片 {photo_count} 張、metadata {metadata_count} 筆')
    print(f'[DONE] index 路徑已重新連結，備份位於 {backup_path}')


if __name__ == '__main__':
    main()
