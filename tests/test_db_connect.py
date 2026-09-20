import sqlite3
from pathlib import Path

import pytest

from pocket.db.connect import BUSY_TIMEOUT_MS, connect_database
from pocket.paths import derive_paths, initialize_paths
from pocket.db.connect import transaction


def test_connect_database_configures_connection(tmp_path: Path) -> None:
    paths = initialize_paths(derive_paths(tmp_path / ".pocket"))

    connection = connect_database(paths.state_db)

    try:
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

        row = connection.execute("SELECT 7 AS value").fetchone()

        assert paths.state_db.is_file()
        assert foreign_keys == 1
        assert busy_timeout == BUSY_TIMEOUT_MS
        assert journal_mode == "wal"
        assert isinstance(row, sqlite3.Row)
        assert row["value"] == 7
    finally:
        connection.close()


def test_connect_database_enforces_foreign_keys(tmp_path: Path) -> None:
    paths = initialize_paths(derive_paths(tmp_path / ".pocket"))
    connection = connect_database(paths.state_db)

    try:
        connection.executescript("""
            CREATE TABLE parents (
                id INTEGER PRIMARY KEY
            );

            CREATE TABLE children (
                id INTEGER PRIMARY KEY,
                parent_id INTEGER NOT NULL,
                FOREIGN KEY (parent_id) REFERENCES parents(id)
            );
            """)

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO children(id, parent_id) VALUES(1, 999)")
    finally:
        connection.close()


def test_connect_database_requires_initialized_directory(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "missing" / "state.db"

    with pytest.raises(
        FileNotFoundError,
        match="initialize_paths",
    ):
        connect_database(database_path)


def test_transaction_commits_successful_work(tmp_path: Path) -> None:
    paths = initialize_paths(derive_paths(tmp_path / ".pocket"))
    connection = connect_database(paths.state_db)

    try:
        connection.execute(
            "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )

        with transaction(connection):
            connection.execute(
                "INSERT INTO items(name) VALUES(?)",
                ("committed",),
            )

        row = connection.execute("SELECT name FROM items").fetchone()

        assert row["name"] == "committed"
    finally:
        connection.close()


def test_transaction_rolls_back_failed_work(tmp_path: Path) -> None:
    paths = initialize_paths(derive_paths(tmp_path / ".pocket"))
    connection = connect_database(paths.state_db)

    try:
        connection.execute(
            "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )

        with pytest.raises(RuntimeError, match="force rollback"):
            with transaction(connection):
                connection.execute(
                    "INSERT INTO items(name) VALUES(?)",
                    ("must disappear",),
                )
                raise RuntimeError("force rollback")

        count = connection.execute("SELECT COUNT(*) AS count FROM items").fetchone()

        assert count["count"] == 0
        assert not connection.in_transaction
    finally:
        connection.close()
