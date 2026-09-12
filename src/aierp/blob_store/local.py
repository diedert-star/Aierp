from pathlib import Path


class LocalFilesystemBlobStore:
    """BlobStore backed by the local filesystem. Keys map directly to relative paths."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if self._root.resolve() not in path.parents and path != self._root.resolve():
            raise ValueError(f"blob key escapes store root: {key!r}")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path_for(key)
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_bytes(data)
        tmp_path.replace(path)

    def get(self, key: str) -> bytes:
        return self._path_for(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path_for(key).exists()
