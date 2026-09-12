from collections.abc import Generator

from fastapi import Header
from sqlalchemy.orm import Session

from aierp.blob_store.local import LocalFilesystemBlobStore
from aierp.blob_store.protocol import BlobStore
from aierp.config import settings
from aierp.db import SessionLocal


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
