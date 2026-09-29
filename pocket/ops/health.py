import sqlite3
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pocket.db.connect import connect_database
from pocket.db.migrate import migrate_database
from pocket.paths import PocketPaths, initialize_paths, derive_paths

import json
from urllib.request import urlopen

from pocket.config import Settings

MINIMUM_PYTHON = (3, 11)
OLLAMA_VERSION_URL = "http://127.0.0.1:11434/api/version"

OllamaProbe = Callable[[], str]

ConnectionFactory = Callable[[str], sqlite3.Connection]
PathInitializer = Callable[[PocketPaths], PocketPaths]
DatabaseConnector = Callable[[Path | str], sqlite3.Connection]
DatabaseMigrator = Callable[[sqlite3.Connection], int]


class HealthStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(
    frozen=True,
    slots=True,
)
class HealthCheck:
    name: str
    status: HealthStatus
    message: str
    remediation: str | None = None


@dataclass(frozen=True, slots=True)
class HealthReport:
    checks: tuple[HealthCheck, ...]

    @property
    def status(self) -> HealthStatus:
        """Return the most severe status in the report."""

        if any(check.status is HealthStatus.FAIL for check in self.checks):
            return HealthStatus.FAIL

        if any(check.status is HealthStatus.WARN for check in self.checks):
            return HealthStatus.WARN

        return HealthStatus.PASS

    @property
    def exit_code(self) -> int:
        """Return an exit code based on the report's status."""

        if self.status is HealthStatus.FAIL:
            return 1

        return 0


def check_python_version(
    version: tuple[int, int] | None = None,
) -> HealthCheck:
    """Check whether the running version is supported or not."""

    actual = version or (sys.version_info.major, sys.version_info.minor)
    version_text = f"{actual[0]}.{actual[1]}"
    if actual < MINIMUM_PYTHON:
        return HealthCheck(
            name="python",
            status=HealthStatus.FAIL,
            message=f"Python {version_text} is unsupported.",
            remediation="Install Python 3.11 or newer.",
        )

    return HealthCheck(
        name="python",
        status=HealthStatus.PASS,
        message=f"Python {version_text} is supported.",
    )


def check_fts5(
    connection_factory: ConnectionFactory = sqlite3.connect,
) -> HealthCheck:
    """Prove that SQLite FTS5 creation, insertion, and search work."""

    connection: sqlite3.Connection | None = None

    try:
        connection = connection_factory(":memory:")

        connection.execute("CREATE VIRTUAL TABLE doctor_fts USING fts5(content)")
        connection.execute(
            "INSERT INTO doctor_fts(content) VALUES (?)",
            ("pocket doctor search",),
        )

        row = connection.execute(
            """
            SELECT rowid
            FROM doctor_fts
            WHERE doctor_fts MATCH ?
            """,
            ("doctor",),
        ).fetchone()

        if row is None:
            raise sqlite3.OperationalError("FTS5 query did not return the inserted row")

    except sqlite3.Error as error:
        return HealthCheck(
            name="fts5",
            status=HealthStatus.FAIL,
            message=f"SQLite FTS5 is unavailable: {error}",
            remediation=(
                "Install a Python build linked against SQLite " "with FTS5 support."
            ),
        )
    finally:
        if connection is not None:
            connection.close()

    return HealthCheck(
        name="fts5",
        status=HealthStatus.PASS,
        message=(f"SQLite {sqlite3.sqlite_version} has working FTS5 support."),
    )


def check_home_directory(
    paths: PocketPaths,
    initializer: PathInitializer = initialize_paths,
) -> HealthCheck:
    """Prove that Pocket's required runtime directories can be initialized."""

    try:
        initializer(paths)
    except OSError as error:
        return HealthCheck(
            name="home",
            status=HealthStatus.FAIL,
            message=f"Pocket home initialization failed: {error}",
            remediation=("Set POCKET_HOME to a location Pocket can create and access."),
        )

    missing_directories = [
        str(directory) for directory in paths.directories if not directory.is_dir()
    ]

    if missing_directories:
        return HealthCheck(
            name="home",
            status=HealthStatus.FAIL,
            message=(
                "Pocket home initialization did not create: "
                + ", ".join(missing_directories)
            ),
            remediation="Check the configured POCKET_HOME path.",
        )

    return HealthCheck(
        name="home",
        status=HealthStatus.PASS,
        message=f"Pocket runtime directories are ready under {paths.home}.",
    )


def check_database(
    database_path: Path | str,
    connector: DatabaseConnector = connect_database,
    migrator: DatabaseMigrator = migrate_database,
) -> HealthCheck:
    """Open, migrate, and validate Pocket's SQLite database."""

    path = Path(database_path)
    connection: sqlite3.Connection | None = None

    try:
        connection = connector(path)
        schema_version = migrator(connection)

        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]

        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()

        if foreign_keys != 1:
            raise RuntimeError("foreign-key enforcement is disabled")

        if str(journal_mode).lower() != "wal":
            raise RuntimeError(f"expected WAL journal mode, received {journal_mode!r}")

        if foreign_key_errors:
            raise RuntimeError(
                f"foreign-key integrity check found "
                f"{len(foreign_key_errors)} violation(s)"
            )

    except (OSError, sqlite3.Error, RuntimeError, ValueError) as error:
        return HealthCheck(
            name="database",
            status=HealthStatus.FAIL,
            message=f"Database health check failed: {error}",
            remediation=(
                "Check POCKET_HOME permissions and the integrity of state.db."
            ),
        )
    finally:
        if connection is not None:
            connection.close()

    return HealthCheck(
        name="database",
        status=HealthStatus.PASS,
        message=(
            f"Database schema version {schema_version} is healthy "
            "with foreign keys and WAL enabled."
        ),
    )


def check_provider_configuration(
    settings: Settings,
) -> HealthCheck:
    """Validate the minimum configuration required by the selected provider."""

    provider = settings.provider.strip().lower()
    model = settings.model.strip()

    if not provider:
        return HealthCheck(
            name="provider",
            status=HealthStatus.FAIL,
            message="No provider is configured.",
            remediation="Set POCKET_PROVIDER.",
        )

    if not model:
        return HealthCheck(
            name="provider",
            status=HealthStatus.FAIL,
            message=f"No model is configured for provider {provider!r}.",
            remediation="Set POCKET_MODEL.",
        )

    api_key = (
        settings.api_key.get_secret_value().strip()
        if settings.api_key is not None
        else ""
    )

    if provider != "ollama" and not api_key:
        return HealthCheck(
            name="provider",
            status=HealthStatus.FAIL,
            message=(
                f"Provider {provider!r} requires an API key, " "but none is configured."
            ),
            remediation="Set POCKET_API_KEY.",
        )

    return HealthCheck(
        name="provider",
        status=HealthStatus.PASS,
        message=(f"Provider {provider!r} is configured " f"with model {model!r}."),
    )


def probe_ollama_version() -> str:
    """Return the version reported by the local Ollama service."""

    with urlopen(
        OLLAMA_VERSION_URL,
        timeout=1.0,
    ) as response:
        payload = json.load(response)

    version = payload.get("version")

    if not isinstance(version, str) or not version.strip():
        raise ValueError("Ollama returned no valid version")

    return version


def check_ollama(
    probe: OllamaProbe = probe_ollama_version,
) -> HealthCheck:
    """Check whether the selected local Ollama service is reachable."""

    try:
        version = probe()
    except (OSError, ValueError) as error:
        return HealthCheck(
            name="ollama",
            status=HealthStatus.FAIL,
            message=f"Ollama is unavailable: {error}",
            remediation=("Start Ollama or configure a different provider."),
        )

    return HealthCheck(
        name="ollama",
        status=HealthStatus.PASS,
        message=f"Ollama {version} is reachable.",
    )


def run_health_checks(
    settings: Settings,
    *,
    initializer: PathInitializer = initialize_paths,
    database_connector: DatabaseConnector = connect_database,
    database_migrator: DatabaseMigrator = migrate_database,
    ollama_probe: OllamaProbe = probe_ollama_version,
) -> HealthReport:
    """Run Pocket's health checks in a stable order."""

    path = derive_paths(settings.home)
    checks: list[HealthCheck] = [check_python_version(), check_fts5()]

    home_check = check_home_directory(path, initializer=initializer)

    checks.append(home_check)

    if home_check.status is HealthStatus.PASS:
        checks.append(
            check_database(
                path.state_db, connector=database_connector, migrator=database_migrator
            )
        )
    else:
        checks.append(
            HealthCheck(
                name="database",
                status=HealthStatus.FAIL,
                message=(
                    "Database check was not run because "
                    "Pocket home initialization failed."
                ),
                remediation=home_check.remediation,
            )
        )

    checks.append(check_provider_configuration(settings))

    if settings.provider.strip().lower() == "ollama":
        checks.append(check_ollama(ollama_probe))

    checks.extend(
        (
            check_embedder(),
            check_sandbox(),
        )
    )

    return HealthReport(checks=tuple(checks))


def check_embedder() -> HealthCheck:
    """Report the current embedding capability."""

    return HealthCheck(
        name="embedder",
        status=HealthStatus.WARN,
        message=(
            "Embedding support is not implemented yet; "
            "lexical FTS5 search remains available."
        ),
        remediation=(
            "Continue with lexical search until an embedding " "provider is configured."
        ),
    )


def check_sandbox() -> HealthCheck:
    """Report the current sandbox capability."""

    return HealthCheck(
        name="sandbox",
        status=HealthStatus.WARN,
        message=(
            "Sandbox execution is not implemented yet; "
            "code execution is unavailable."
        ),
        remediation=(
            "Continue without code execution until a sandbox " "backend is configured."
        ),
    )
