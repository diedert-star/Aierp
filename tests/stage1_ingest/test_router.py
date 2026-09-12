from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from aierp.api.deps import get_blob_store, get_db_session
from aierp.blob_store.local import LocalFilesystemBlobStore
from aierp.blob_store.protocol import BlobStore
from aierp.stage1_ingest.router import router


@pytest.fixture
def client(
    engine: Engine, db_session: Session, tmp_path: Path
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(router)

    def _get_db_session() -> Generator[Session, None, None]:
        yield db_session

    def _get_blob_store() -> BlobStore:
        return LocalFilesystemBlobStore(tmp_path / "blobs")

    app.dependency_overrides[get_db_session] = _get_db_session
    app.dependency_overrides[get_blob_store] = _get_blob_store

    with TestClient(app) as test_client:
        yield test_client


def test_upload_document_requires_tenant_header(client: TestClient) -> None:
    response = client.post(
        "/documents",
        files={"file": ("invoice.pdf", b"bytes", "application/pdf")},
        data={"channel": "upload"},
    )
    assert response.status_code == 422


def test_upload_document_returns_document_id(client: TestClient) -> None:
    response = client.post(
        "/documents",
        files={"file": ("invoice.pdf", b"bytes", "application/pdf")},
        data={"channel": "upload"},
        headers={"X-Tenant-Id": "tenant-a"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["duplicate"] is False
    assert "document_id" in body


def test_upload_same_document_twice_reports_duplicate(client: TestClient) -> None:
    payload = {
        "files": {"file": ("invoice.pdf", b"identical bytes", "application/pdf")},
        "data": {"channel": "upload"},
        "headers": {"X-Tenant-Id": "tenant-a"},
    }
    first = client.post("/documents", **payload)
    second = client.post("/documents", **payload)

    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert second.json()["document_id"] == first.json()["document_id"]
