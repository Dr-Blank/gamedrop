import os

from sqlalchemy import event
from sqlmodel import Session, create_engine

DATA_DIR = os.environ.get(
    "DATA_DIR", os.path.join(os.path.dirname(__file__), "../../data")
)
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{DATA_DIR}/tracker.db"
BUSY_TIMEOUT_MS = 30_000


def make_engine(url: str):
    """SQLite engine tuned for a background sync writing alongside API requests."""
    eng = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _configure(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        # WAL lets readers and a writer overlap; the timeout makes a second
        # writer wait out a long sync transaction instead of failing.
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        # Safe from corruption under WAL; a power cut may drop the last commits.
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    return eng


engine = make_engine(DATABASE_URL)


def run_migrations():
    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(os.path.dirname(__file__), "../alembic.ini"))
    # App already configured logging (ring buffer + stdout). Tell env.py to skip
    # fileConfig so it doesn't tear down our handlers / disable app loggers.
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


def get_session():
    with Session(engine) as session:
        yield session
