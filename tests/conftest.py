from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from aierp.blob_store.local import LocalFilesystemBlobStore
from aierp.blob_store.protocol import BlobStore
from aierp.db import Base

# import every stage's models so they register on Base.metadata before create_all
from aierp.stage1_ingest import models as _stage1_models  # noqa: F401

TEST_DATABASE_URL = "postgresql+psycopg://aierp:aierp@127.0.0.1:5432/aierp_test"


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    eng = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Generator[Session, None, None]:
    connection = engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, expire_on_commit=False, future=True)
    session = session_factory()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def blob_store(tmp_path: Path) -> BlobStore:
    return LocalFilesystemBlobStore(tmp_path / "blobs")
