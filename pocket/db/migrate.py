"""Database schema loading and versioned migrations."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from pocket.db.connect import transaction

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

BASE_SCHEMA_VERSION = 1
BASE_SCHEMA_NAME = "base_schema"


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


def apply_schema(
    connection: sqlite3.Connection,
    schema_path: Path = SCHEMA_PATH,
) -> None:
    """Create the base schema and record version 1 atomically."""

    if connection.in_transaction:
        raise RuntimeError("Cannot apply the schema inside an active transaction.")

    schema_sql = schema_path.read_text(encoding="utf-8")

    script = "\n".join(
        (
            "BEGIN IMMEDIATE;",
            schema_sql,
            (
                "INSERT OR IGNORE INTO schema_version(version, name) "
                "VALUES (1, 'base_schema');"
            ),
            "COMMIT;",
        )
    )

    try:
        connection.executescript(script)
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise

    row = connection.execute(
        "SELECT name FROM schema_version WHERE version = ?",
        (BASE_SCHEMA_VERSION,),
    ).fetchone()

    if row is None or row["name"] != BASE_SCHEMA_NAME:
        raise RuntimeError("Schema version 1 exists with an unexpected name.")


def current_schema_version(connection: sqlite3.Connection) -> int:
    """Return the latest applied schema version."""

    row = connection.execute(
        "SELECT COALESCE(MAX(version), 0) AS version FROM schema_version"
    ).fetchone()

    return int(row["version"])


def apply_migration(
    connection: sqlite3.Connection,
    migration: Migration,
) -> bool:
    """Apply one migration.

    Returns True when applied and False when it was already applied.
    """

    if migration.version <= BASE_SCHEMA_VERSION:
        raise ValueError(
            "Migration versions must be greater than the base schema version."
        )

    existing = connection.execute(
        "SELECT name FROM schema_version WHERE version = ?",
        (migration.version,),
    ).fetchone()

    if existing is not None:
        if existing["name"] != migration.name:
            raise RuntimeError(
                f"Migration version {migration.version} is already registered "
                f"as {existing['name']!r}, not {migration.name!r}."
            )

        return False

    with transaction(connection, immediate=True):
        for statement in migration.statements:
            connection.execute(statement)

        connection.execute(
            """
            INSERT INTO schema_version(version, name)
            VALUES (?, ?)
            """,
            (migration.version, migration.name),
        )

    return True


MIGRATIONS = (
    Migration(
        version=2,
        name="add_fts5_indexes",
        statements=(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
                subject,
                content,
                content='facts',
                content_rowid='id'
            )
            """,
            """
            CREATE TRIGGER IF NOT EXISTS facts_ai
            AFTER INSERT ON facts BEGIN
                INSERT INTO facts_fts(rowid, subject, content)
                VALUES (new.id, new.subject, new.content);
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS facts_ad
            AFTER DELETE ON facts BEGIN
                INSERT INTO facts_fts(facts_fts, rowid, subject, content)
                VALUES ('delete', old.id, old.subject, old.content);
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS facts_au
            AFTER UPDATE ON facts BEGIN
                INSERT INTO facts_fts(facts_fts, rowid, subject, content)
                VALUES ('delete', old.id, old.subject, old.content);

                INSERT INTO facts_fts(rowid, subject, content)
                VALUES (new.id, new.subject, new.content);
            END
            """,
            "INSERT INTO facts_fts(facts_fts) VALUES ('rebuild')",
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
                summary,
                content='episodes',
                content_rowid='id'
            )
            """,
            """
            CREATE TRIGGER IF NOT EXISTS episodes_ai
            AFTER INSERT ON episodes BEGIN
                INSERT INTO episodes_fts(rowid, summary)
                VALUES (new.id, new.summary);
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS episodes_ad
            AFTER DELETE ON episodes BEGIN
                INSERT INTO episodes_fts(episodes_fts, rowid, summary)
                VALUES ('delete', old.id, old.summary);
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS episodes_au
            AFTER UPDATE ON episodes BEGIN
                INSERT INTO episodes_fts(episodes_fts, rowid, summary)
                VALUES ('delete', old.id, old.summary);

                INSERT INTO episodes_fts(rowid, summary)
                VALUES (new.id, new.summary);
            END
            """,
            "INSERT INTO episodes_fts(episodes_fts) VALUES ('rebuild')",
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                heading,
                text,
                content='chunks',
                content_rowid='id'
            )
            """,
            """
            CREATE TRIGGER IF NOT EXISTS chunks_ai
            AFTER INSERT ON chunks BEGIN
                INSERT INTO chunks_fts(rowid, heading, text)
                VALUES (new.id, new.heading, new.text);
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS chunks_ad
            AFTER DELETE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, heading, text)
                VALUES ('delete', old.id, old.heading, old.text);
            END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS chunks_au
            AFTER UPDATE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, heading, text)
                VALUES ('delete', old.id, old.heading, old.text);

                INSERT INTO chunks_fts(rowid, heading, text)
                VALUES (new.id, new.heading, new.text);
            END
            """,
            "INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')",
        ),
    ),
)


def migrate_database(
    connection: sqlite3.Connection,
    migrations: tuple[Migration, ...] = MIGRATIONS,
) -> int:
    """Create the base schema and apply migrations in order."""

    apply_schema(connection)

    expected_version = BASE_SCHEMA_VERSION + 1

    for migration in migrations:
        if migration.version != expected_version:
            raise ValueError(
                f"Expected migration version {expected_version}, "
                f"but received {migration.version}."
            )

        apply_migration(connection, migration)
        expected_version += 1

    return current_schema_version(connection)
