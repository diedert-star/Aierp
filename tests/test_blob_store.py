from pathlib import Path

import pytest

from aierp.blob_store.local import LocalFilesystemBlobStore


def test_put_then_get_roundtrips(tmp_path: Path) -> None:
    store = LocalFilesystemBlobStore(tmp_path)
    store.put("aa/bb/deadbeef", b"hello world")
    assert store.get("aa/bb/deadbeef") == b"hello world"


def test_exists(tmp_path: Path) -> None:
    store = LocalFilesystemBlobStore(tmp_path)
    assert not store.exists("nope")
    store.put("nope", b"x")
    assert store.exists("nope")


def test_put_never_overwrites_existing_key(tmp_path: Path) -> None:
    store = LocalFilesystemBlobStore(tmp_path)
    store.put("key", b"original")
    store.put("key", b"different bytes")
    assert store.get("key") == b"original"


def test_put_creates_intermediate_directories(tmp_path: Path) -> None:
    store = LocalFilesystemBlobStore(tmp_path)
    store.put("a/b/c/d", b"nested")
    assert store.get("a/b/c/d") == b"nested"


def test_key_cannot_escape_store_root(tmp_path: Path) -> None:
    store = LocalFilesystemBlobStore(tmp_path)
    with pytest.raises(ValueError):
        store.put("../escape", b"x")
