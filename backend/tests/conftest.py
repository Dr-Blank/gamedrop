import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

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
    """Redirect app.db.engine to the in-memory test engine for every test.
    Prevents DatabaseChannel (and any code using the engine directly) from
    writing to the real production DB during the test suite."""
    from app import db as _db

    original = _db.engine
    _db.engine = test_engine
    yield
    _db.engine = original


@pytest.fixture(name="client")
def client_fixture(session: Session):
    from main import app

    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()
