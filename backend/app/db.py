import os

from sqlmodel import Session, create_engine

DATA_DIR = os.environ.get(
    "DATA_DIR", os.path.join(os.path.dirname(__file__), "../../data")
)
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{DATA_DIR}/tracker.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def run_migrations():
    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(os.path.dirname(__file__), "../alembic.ini"))
    command.upgrade(cfg, "head")


def get_session():
    with Session(engine) as session:
        yield session
