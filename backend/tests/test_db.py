import threading

from sqlalchemy import text

from app.db import BUSY_TIMEOUT_MS, make_engine


def test_engine_pragmas(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path}/t.db")
    with eng.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == BUSY_TIMEOUT_MS
        # 1 = NORMAL
        assert conn.exec_driver_sql("PRAGMA synchronous").scalar() == 1


def test_writer_commits_while_reader_holds_snapshot(tmp_path):
    eng = make_engine(f"sqlite:///{tmp_path}/t.db")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE t (x INTEGER)"))
        conn.execute(text("INSERT INTO t VALUES (1)"))

    reader = eng.raw_connection()
    cur = reader.cursor()
    cur.execute("BEGIN")
    cur.execute("SELECT x FROM t")
    cur.fetchall()

    errors = []

    def write():
        try:
            with eng.begin() as conn:
                conn.execute(text("UPDATE t SET x = 2"))
        except Exception as e:
            errors.append(e)

    # Rollback-journal mode would block this commit until the reader ends.
    t = threading.Thread(target=write)
    t.start()
    t.join(timeout=5)
    reader.rollback()
    reader.close()

    assert not t.is_alive()
    assert errors == []
