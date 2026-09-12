from collections.abc import Generator

from fastapi import Header
from sqlalchemy.orm import Session

from aierp.blob_store.local import LocalFilesystemBlobStore
from aierp.blob_store.protocol import BlobStore
from aierp.config import settings
from aierp.db import SessionLocal
from aierp.stage3_validation.vies_client import ViesClient, ViesHttpClient


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_blob_store() -> BlobStore:
    return LocalFilesystemBlobStore(settings.blob_store_root)


def get_tenant_id(x_tenant_id: str = Header(..., alias="X-Tenant-Id")) -> str:
    return x_tenant_id


def get_tenant_vat_number(
    x_tenant_vat_number: str = Header(..., alias="X-Tenant-Vat-Number"),
) -> str:
    return x_tenant_vat_number


# Module-level singleton: the VIES client's cache and rate limiter must persist across requests.
_vies_client: ViesClient = ViesHttpClient(
    cache_ttl_seconds=settings.vies_cache_ttl_seconds,
    min_interval_seconds=settings.vies_min_interval_seconds,
    request_timeout_seconds=settings.vies_request_timeout_seconds,
)


def get_vies_client() -> ViesClient:
    return _vies_client
