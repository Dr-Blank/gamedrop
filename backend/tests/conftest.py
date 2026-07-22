from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.channels.ntfy import NtfyChannel
from app.db import get_session


def _make_engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture(name="test_engine")
def test_engine_fixture():
    engine = _make_engine()
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="session")
def session_fixture(test_engine):
    with Session(test_engine) as session:
        yield session


@pytest.fixture(autouse=True)
def patch_db_engine(test_engine):
    """Redirect app.db.engine and app.config.engine to the in-memory test engine.
    config.py imports engine via `from .db import engine`, so its local binding
    must be patched separately — reassigning app.db.engine alone doesn't update it."""
    from app import config as _config
    from app import db as _db

    original_db = _db.engine
    original_cfg = _config.engine
    _db.engine = test_engine
    _config.engine = test_engine
    yield
    _db.engine = original_db
    _config.engine = original_cfg


@pytest.fixture(autouse=True)
def block_ntfy_network():
    """Stop NtfyChannel from making real HTTP calls to ntfy.sh during tests.

    notifier._dispatch always fans out to every channel, so a test that patches
    only one notify_* helper can still reach the live ntfy client through
    another code path. Patching the class attribute keeps instance-level
    patch.object(channel, "_client", ...) in tests working — the instance
    attribute still wins on lookup."""
    with patch.object(NtfyChannel, "_client", return_value=MagicMock()):
        yield


@pytest.fixture(name="client")
def client_fixture(session: Session):
    from main import app

    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()
