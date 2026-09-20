import sqlite3
from pathlib import Path
from collections.abc import Iterator
from contextlib import contextmanager

BUSY_TIMEOUT_MS = 5_000  # 5 seconds


def connect_database(database_path: Path | str) -> sqlite3.Connection:
    """Open a configured SQLite connection.

    The caller must initialize the Pocket home directory before connecting.
    """
    path = Path(database_path)
    if not path.parent.is_dir():
        raise FileNotFoundError(
            f"Database directory does not exist: {path.parent}. "
            "Call initialize_paths() before connect_database()."
        )

    connection = sqlite3.connect(
        path, timeout=BUSY_TIMEOUT_MS / 1_000, isolation_level=None
    )

    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS};")
        row = connection.execute("PRAGMA journal_mode = WAL").fetchone()
        journal_mode = str(row[0]).lower() if row is not None else ""

        if journal_mode != "wal":
            raise RuntimeError(f"Could not enable WAL mode for database: {path}")
    except Exception:
        connection.close()
        raise

    return connection


@contextmanager
def transaction(
    connection: sqlite3.Connection,
    *,
    immediate: bool = False,
) -> Iterator[sqlite3.Connection]:
    """Run a group of statements as one atomic operation."""
    if connection.in_transaction:
        raise RuntimeError("Nested Transactions are not supported.")

    begin_statement = "BEGIN IMMEDIATE" if immediate else "BEGIN"

    connection.execute(begin_statement)

    try:
        yield connection
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()
