from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from aierp.api.deps import get_blob_store, get_db_session, get_vies_client
from aierp.blob_store.local import LocalFilesystemBlobStore
from aierp.blob_store.protocol import BlobStore
from aierp.pipeline.router import router
from aierp.stage3_validation.vies_client import ViesClient

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ubl"
TENANT_HEADERS = {"X-Tenant-Id": "tenant-a", "X-Tenant-Vat-Number": "BE0999999999"}


class _AlwaysValidViesClient:
    def is_valid(self, country_code: str, vat_number: str) -> bool | None:
        return True


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

    def _get_vies_client() -> ViesClient:
        return _AlwaysValidViesClient()

    app.dependency_overrides[get_db_session] = _get_db_session
    app.dependency_overrides[get_blob_store] = _get_blob_store
    app.dependency_overrides[get_vies_client] = _get_vies_client

    with TestClient(app) as test_client:
        yield test_client


def test_upload_unknown_supplier_needs_review(client: TestClient) -> None:
    response = client.post(
        "/documents",
        files={
            "file": (
                "unknown_supplier.xml",
                (FIXTURES / "unknown_supplier.xml").read_bytes(),
                "application/xml",
            )
        },
        data={"channel": "peppol"},
        headers=TENANT_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["duplicate"] is False
    assert body["status"] == "needs_review"


def test_upload_same_bytes_twice_is_duplicate_and_keeps_status(client: TestClient) -> None:
    payload = {
        "files": {
            "file": (
                "unknown_supplier.xml",
                (FIXTURES / "unknown_supplier.xml").read_bytes(),
                "application/xml",
            )
        },
        "data": {"channel": "peppol"},
        "headers": TENANT_HEADERS,
    }
    first = client.post("/documents", **payload)
    second = client.post("/documents", **payload)

    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert second.json()["document_id"] == first.json()["document_id"]
    assert second.json()["status"] == first.json()["status"]


def test_list_documents_filters_by_status_and_includes_canonical_invoice(
    client: TestClient,
) -> None:
    client.post(
        "/documents",
        files={
            "file": (
                "unknown_supplier.xml",
                (FIXTURES / "unknown_supplier.xml").read_bytes(),
                "application/xml",
            )
        },
        data={"channel": "peppol"},
        headers=TENANT_HEADERS,
    )

    response = client.get(
        "/documents", params={"status": "needs_review"}, headers=TENANT_HEADERS
    )
    assert response.status_code == 200
    documents = response.json()
    assert len(documents) == 1
    assert documents[0]["status"] == "needs_review"
    assert documents[0]["canonical_invoice"]["invoice_number"] == "2024-5001"
    assert len(documents[0]["reasons"]) >= 1
    assert documents[0]["original_blob_url"].endswith("/original")


def test_get_original_document_returns_raw_bytes(client: TestClient) -> None:
    raw_bytes = (FIXTURES / "unknown_supplier.xml").read_bytes()
    upload = client.post(
        "/documents",
        files={"file": ("unknown_supplier.xml", raw_bytes, "application/xml")},
        data={"channel": "peppol"},
        headers=TENANT_HEADERS,
    )
    document_id = upload.json()["document_id"]

    response = client.get(f"/documents/{document_id}/original", headers=TENANT_HEADERS)

    assert response.status_code == 200
    assert response.content == raw_bytes


def test_get_original_document_404s_for_other_tenant(client: TestClient) -> None:
    raw_bytes = (FIXTURES / "unknown_supplier.xml").read_bytes()
    upload = client.post(
        "/documents",
        files={"file": ("unknown_supplier.xml", raw_bytes, "application/xml")},
        data={"channel": "peppol"},
        headers=TENANT_HEADERS,
    )
    document_id = upload.json()["document_id"]

    response = client.get(
        f"/documents/{document_id}/original",
        headers={"X-Tenant-Id": "tenant-b", "X-Tenant-Vat-Number": "BE0111111111"},
    )
    assert response.status_code == 404
