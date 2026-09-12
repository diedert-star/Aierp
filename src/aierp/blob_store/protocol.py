from typing import Protocol


class BlobStore(Protocol):
    """Content-addressed blob storage. Keys are never overwritten once written."""

    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...
