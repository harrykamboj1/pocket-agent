import sqlite3
from pathlib import Path

import pytest
from pocket.db.migrate import (
    Migration,
    apply_migration,
    apply_schema,
    current_schema_version,
    migrate_database,
)

from pocket.db.connect import connect_database
from pocket.paths import derive_paths, initialize_paths
from collections.abc import Iterator

EXPECTED_TABLES = {
    "sessions",
    "turns",
    "chat_log",
    "facts",
    "episodes",
    "skill_uses",
    "documents",
    "chunks",
    "vectors",
    "fact_vectors",
    "embed_cache",
    "spans",
    "usage",
    "findings",
    "approvals",
    "eval_runs",
    "eval_cases",
    "provider_capabilities",
    "settings_kv",
    "schema_version",
}


def table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("""
        SELECT name
        FROM sqlite_schema
        WHERE type = 'table'
        """).fetchall()

    return {row["name"] for row in rows}


@pytest.fixture
def database_connection(
    tmp_path: Path,
) -> Iterator[sqlite3.Connection]:
    paths = initialize_paths(derive_paths(tmp_path / ".pocket"))
    connection = connect_database(paths.state_db)

    try:
        yield connection
    finally:
        connection.close()


def test_apply_schema_creates_expected_tables(tmp_path: Path) -> None:
    paths = initialize_paths(derive_paths(tmp_path / ".pocket"))
    connection = connect_database(paths.state_db)

    try:
        apply_schema(connection)

        assert EXPECTED_TABLES <= table_names(connection)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_apply_schema_is_idempotent(tmp_path: Path) -> None:
    paths = initialize_paths(derive_paths(tmp_path / ".pocket"))
    connection = connect_database(paths.state_db)

    try:
        apply_schema(connection)
        apply_schema(connection)

        assert EXPECTED_TABLES <= table_names(connection)
    finally:
        connection.close()


def test_apply_schema_rolls_back_on_error(tmp_path: Path) -> None:
    paths = initialize_paths(derive_paths(tmp_path / ".pocket"))
    connection = connect_database(paths.state_db)
    broken_schema = tmp_path / "broken.sql"

    broken_schema.write_text(
        """
        CREATE TABLE should_roll_back (
            id INTEGER PRIMARY KEY
        );

        THIS IS NOT VALID SQL;
        """,
        encoding="utf-8",
    )

    try:
        with pytest.raises(sqlite3.OperationalError):
            apply_schema(connection, broken_schema)

        assert "should_roll_back" not in table_names(connection)
        assert not connection.in_transaction
    finally:
        connection.close()


def test_apply_schema_records_base_version(database_connection):
    apply_schema(database_connection)

    assert current_schema_version(database_connection) == 1

    row = database_connection.execute(
        "SELECT version, name FROM schema_version"
    ).fetchone()

    assert row["version"] == 1
    assert row["name"] == "base_schema"


def test_apply_migration_is_idempotent(database_connection):
    apply_schema(database_connection)

    migration = Migration(
        version=2,
        name="create_notes",
        statements=(
            """
            CREATE TABLE notes (
                id INTEGER PRIMARY KEY,
                content TEXT NOT NULL
            )
            """,
        ),
    )

    assert apply_migration(database_connection, migration) is True
    assert apply_migration(database_connection, migration) is False
    assert current_schema_version(database_connection) == 2


def test_failed_migration_rolls_back(database_connection):
    apply_schema(database_connection)

    migration = Migration(
        version=2,
        name="broken_migration",
        statements=(
            "CREATE TABLE temporary_table (id INTEGER PRIMARY KEY)",
            "THIS IS NOT VALID SQL",
        ),
    )

    with pytest.raises(sqlite3.OperationalError):
        apply_migration(database_connection, migration)

    table = database_connection.execute("""
        SELECT name
        FROM sqlite_schema
        WHERE type = 'table' AND name = 'temporary_table'
        """).fetchone()

    assert table is None
    assert current_schema_version(database_connection) == 1


def test_migrations_must_be_sequential(database_connection):
    migration = Migration(
        version=3,
        name="skipped_version_two",
        statements=("CREATE TABLE skipped (id INTEGER PRIMARY KEY)",),
    )

    with pytest.raises(ValueError, match="Expected migration version 2"):
        migrate_database(database_connection, (migration,))

    assert current_schema_version(database_connection) == 1


FTS_TABLES = {
    "facts_fts",
    "episodes_fts",
    "chunks_fts",
}


def search_fts(
    connection: sqlite3.Connection,
    table: str,
    query: str,
) -> list[int]:
    rows = connection.execute(
        f"SELECT rowid FROM {table} where {table} MATCH ?",
        (query,),
    ).fetchall()
    return [row["rowid"] for row in rows]


def test_migrate_database_applies_fts_migration(database_connection):
    assert migrate_database(database_connection) == 2
    assert migrate_database(database_connection) == 2

    assert FTS_TABLES <= table_names(database_connection)


def test_fts_rebuild_indexes_existing_rows(database_connection):
    apply_schema(database_connection)

    fact_id = database_connection.execute(
        """
        INSERT INTO facts(subject, content)
        VALUES (?, ?)
        """,
        ("project", "Pocket uses SQLite"),
    ).lastrowid

    migrate_database(database_connection)

    assert search_fts(
        database_connection,
        "facts_fts",
        "SQLite",
    ) == [fact_id]


def test_fts_triggers_follow_insert_update_delete(database_connection):
    migrate_database(database_connection)

    fact_id = database_connection.execute(
        """
        INSERT INTO facts(subject, content)
        VALUES (?, ?)
        """,
        ("animals", "Alpacas are friendly"),
    ).lastrowid

    assert search_fts(database_connection, "facts_fts", "Alpacas") == [fact_id]

    database_connection.execute(
        "UPDATE facts SET content = ? WHERE id = ?",
        ("Llamas are friendly", fact_id),
    )

    assert search_fts(database_connection, "facts_fts", "Alpacas") == []
    assert search_fts(database_connection, "facts_fts", "Llamas") == [fact_id]

    database_connection.execute(
        "DELETE FROM facts WHERE id = ?",
        (fact_id,),
    )

    assert search_fts(database_connection, "facts_fts", "Llamas") == []


def test_episodes_fts_follows_insert_update_delete(database_connection):
    migrate_database(database_connection)

    episode_id = database_connection.execute(
        """
        INSERT INTO episodes(happened_at, summary)
        VALUES (?, ?)
        """,
        ("2026-09-20", "Visited a volcano"),
    ).lastrowid

    assert search_fts(
        database_connection,
        "episodes_fts",
        "volcano",
    ) == [episode_id]

    database_connection.execute(
        "UPDATE episodes SET summary = ? WHERE id = ?",
        ("Visited a glacier", episode_id),
    )

    assert search_fts(database_connection, "episodes_fts", "volcano") == []
    assert search_fts(
        database_connection,
        "episodes_fts",
        "glacier",
    ) == [episode_id]

    database_connection.execute(
        "DELETE FROM episodes WHERE id = ?",
        (episode_id,),
    )

    assert search_fts(database_connection, "episodes_fts", "glacier") == []


def test_chunks_fts_follows_insert_update_delete(database_connection):
    migrate_database(database_connection)

    document_id = database_connection.execute(
        """
        INSERT INTO documents(source, content_hash)
        VALUES (?, ?)
        """,
        ("notes.md", "hash-1"),
    ).lastrowid

    chunk_id = database_connection.execute(
        """
        INSERT INTO chunks(doc_id, ord, heading, text)
        VALUES (?, ?, ?, ?)
        """,
        (document_id, 0, "Physics", "Quantum mechanics notes"),
    ).lastrowid

    assert search_fts(
        database_connection,
        "chunks_fts",
        "Quantum",
    ) == [chunk_id]

    database_connection.execute(
        """
        UPDATE chunks
        SET heading = ?, text = ?
        WHERE id = ?
        """,
        ("Biology", "Neutrino research notes", chunk_id),
    )

    assert search_fts(database_connection, "chunks_fts", "Quantum") == []
    assert search_fts(
        database_connection,
        "chunks_fts",
        "Neutrino",
    ) == [chunk_id]

    database_connection.execute(
        "DELETE FROM chunks WHERE id = ?",
        (chunk_id,),
    )

    assert search_fts(database_connection, "chunks_fts", "Neutrino") == []
