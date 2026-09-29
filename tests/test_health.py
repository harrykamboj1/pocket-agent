import sqlite3
import sys
from pathlib import Path

from pocket.config import Settings
from pocket.db.connect import connect_database
from pocket.db.migrate import current_schema_version
from pocket.ops.health import (
    HealthCheck,
    HealthReport,
    HealthStatus,
    check_database,
    check_embedder,
    check_fts5,
    check_home_directory,
    check_ollama,
    check_provider_configuration,
    check_python_version,
    check_sandbox,
    run_health_checks,
)
from pocket.paths import PocketPaths, derive_paths, initialize_paths


def test_python_check_passes_supported_version() -> None:
    result = check_python_version((3, 11))

    assert result.name == "python"
    assert result.status is HealthStatus.PASS
    assert result.remediation is None


def test_python_check_fails_unsupported_version() -> None:
    result = check_python_version((3, 10))

    assert result.status is HealthStatus.FAIL
    assert result.remediation == "Install Python 3.11 or newer."


def test_fts5_check_passes_when_search_works() -> None:
    result = check_fts5()

    assert result.name == "fts5"
    assert result.status is HealthStatus.PASS
    assert result.remediation is None


def test_fts5_check_reports_unavailable_extension() -> None:
    def unavailable_fts5(_database: str) -> sqlite3.Connection:
        raise sqlite3.OperationalError("no such module: fts5")

    result = check_fts5(unavailable_fts5)

    assert result.status is HealthStatus.FAIL
    assert "no such module: fts5" in result.message
    assert result.remediation is not None


def test_python_check_uses_running_version_by_default() -> None:
    result = check_python_version()

    running_version = f"{sys.version_info.major}.{sys.version_info.minor}"

    assert running_version in result.message


def test_home_check_initializes_required_directories(
    tmp_path: Path,
) -> None:
    paths = derive_paths(tmp_path / ".pocket")

    result = check_home_directory(paths)

    assert result.status is HealthStatus.PASS
    assert all(directory.is_dir() for directory in paths.directories)


def test_home_check_reports_initialization_failure(
    tmp_path: Path,
) -> None:
    paths = derive_paths(tmp_path / ".pocket")

    def permission_denied(
        _paths: PocketPaths,
    ) -> PocketPaths:
        raise PermissionError("permission denied")

    result = check_home_directory(
        paths,
        initializer=permission_denied,
    )

    assert result.status is HealthStatus.FAIL
    assert "permission denied" in result.message
    assert result.remediation is not None


def test_database_check_creates_and_validates_database(
    tmp_path: Path,
) -> None:
    paths = initialize_paths(derive_paths(tmp_path / ".pocket"))

    result = check_database(paths.state_db)

    assert result.status is HealthStatus.PASS
    assert paths.state_db.is_file()

    connection = connect_database(paths.state_db)

    try:
        assert current_schema_version(connection) == 2
    finally:
        connection.close()


def test_database_check_reports_connection_failure(
    tmp_path: Path,
) -> None:
    paths = initialize_paths(derive_paths(tmp_path / ".pocket"))

    def unavailable_database(
        _path: Path | str,
    ) -> sqlite3.Connection:
        raise sqlite3.OperationalError("unable to open database file")

    result = check_database(
        paths.state_db,
        connector=unavailable_database,
    )

    assert result.status is HealthStatus.FAIL
    assert "unable to open database file" in result.message
    assert result.remediation is not None


def test_provider_check_passes_valid_ollama_configuration() -> None:
    settings = Settings(
        provider="ollama",
        model="qwen3:1.7b",
    )

    result = check_provider_configuration(settings)

    assert result.status is HealthStatus.PASS
    assert "qwen3:1.7b" in result.message


def test_provider_check_fails_when_model_is_missing() -> None:
    settings = Settings(
        provider="ollama",
        model="",
    )

    result = check_provider_configuration(settings)

    assert result.status is HealthStatus.FAIL
    assert result.remediation == "Set POCKET_MODEL."


def test_cloud_provider_requires_api_key() -> None:
    settings = Settings(
        provider="openai",
        model="gpt-5",
        api_key=None,
    )

    result = check_provider_configuration(settings)

    assert result.status is HealthStatus.FAIL
    assert result.remediation == "Set POCKET_API_KEY."


def test_provider_check_never_exposes_api_key() -> None:
    secret = "top-secret-value"

    settings = Settings(
        provider="openai",
        model="gpt-5",
        api_key=secret,
    )

    result = check_provider_configuration(settings)

    assert result.status is HealthStatus.PASS
    assert secret not in result.message


def test_ollama_check_passes_with_reported_version() -> None:
    result = check_ollama(lambda: "0.12.0")

    assert result.status is HealthStatus.PASS
    assert "0.12.0" in result.message


def test_ollama_check_reports_unavailable_service() -> None:
    def unavailable() -> str:
        raise ConnectionError("connection refused")

    result = check_ollama(unavailable)

    assert result.status is HealthStatus.FAIL
    assert "connection refused" in result.message
    assert result.remediation is not None


def test_health_report_uses_most_severe_status() -> None:
    warning_report = HealthReport(
        checks=(
            HealthCheck(
                name="python",
                status=HealthStatus.PASS,
                message="Python works.",
            ),
            HealthCheck(
                name="embedder",
                status=HealthStatus.WARN,
                message="Using lexical search only.",
            ),
        )
    )

    failed_report = HealthReport(
        checks=warning_report.checks
        + (
            HealthCheck(
                name="database",
                status=HealthStatus.FAIL,
                message="Database failed.",
            ),
        )
    )

    assert warning_report.status is HealthStatus.WARN
    assert warning_report.exit_code == 0

    assert failed_report.status is HealthStatus.FAIL
    assert failed_report.exit_code == 1


def test_optional_capabilities_are_visible_warnings() -> None:
    embedder = check_embedder()
    sandbox = check_sandbox()

    assert embedder.status is HealthStatus.WARN
    assert embedder.remediation is not None

    assert sandbox.status is HealthStatus.WARN
    assert sandbox.remediation is not None


def test_run_health_checks_returns_degraded_report(
    tmp_path: Path,
) -> None:
    settings = Settings(
        provider="ollama",
        model="qwen3:1.7b",
        home=tmp_path / ".pocket",
    )

    report = run_health_checks(
        settings,
        ollama_probe=lambda: "0.12.0",
    )

    names = [check.name for check in report.checks]

    assert names == [
        "python",
        "fts5",
        "home",
        "database",
        "provider",
        "ollama",
        "embedder",
        "sandbox",
    ]
    assert report.status is HealthStatus.WARN
    assert report.exit_code == 0


def test_run_health_checks_omits_unselected_ollama(
    tmp_path: Path,
) -> None:
    settings = Settings(
        provider="openai",
        model="gpt-5",
        api_key="test-key",
        home=tmp_path / ".pocket",
    )

    def must_not_run() -> str:
        raise AssertionError("Ollama probe must not run for OpenAI")

    report = run_health_checks(
        settings,
        ollama_probe=must_not_run,
    )

    names = [check.name for check in report.checks]

    assert "ollama" not in names
    assert report.status is HealthStatus.WARN
    assert report.exit_code == 0


def test_run_health_checks_skips_database_after_home_failure(
    tmp_path: Path,
) -> None:
    settings = Settings(
        provider="ollama",
        model="qwen3:1.7b",
        home=tmp_path / ".pocket",
    )

    def permission_denied(
        _paths: PocketPaths,
    ) -> PocketPaths:
        raise PermissionError("permission denied")

    def must_not_connect(
        _path: Path | str,
    ) -> sqlite3.Connection:
        raise AssertionError("Database connection must not be attempted")

    report = run_health_checks(
        settings,
        initializer=permission_denied,
        database_connector=must_not_connect,
        ollama_probe=lambda: "0.12.0",
    )

    checks_by_name = {check.name: check for check in report.checks}

    assert checks_by_name["home"].status is HealthStatus.FAIL
    assert checks_by_name["database"].status is HealthStatus.FAIL
    assert "was not run" in checks_by_name["database"].message
    assert report.exit_code == 1
