from pathlib import Path

import pytest
from typer.testing import CliRunner

from pocket.cli import app
from pocket.config import Settings
from pocket.ops.health import (
    HealthCheck,
    HealthReport,
    HealthStatus,
)

runner = CliRunner()


def configure_doctor(
    monkeypatch: pytest.MonkeyPatch,
    report: HealthReport,
) -> None:
    settings = Settings(
        provider="ollama",
        model="test-model",
    )

    monkeypatch.setattr(
        "pocket.cli.load_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "pocket.cli.run_health_checks",
        lambda _settings: report,
    )


def test_doctor_renders_passing_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = HealthReport(
        checks=(
            HealthCheck(
                name="python",
                status=HealthStatus.PASS,
                message="Python is supported.",
            ),
        )
    )
    configure_doctor(monkeypatch, report)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "[PASS] python: Python is supported." in result.output
    assert "Overall: PASS" in result.output


def test_doctor_warning_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = HealthReport(
        checks=(
            HealthCheck(
                name="embedder",
                status=HealthStatus.WARN,
                message="Using lexical search only.",
                remediation="Configure an embedding provider.",
            ),
        )
    )
    configure_doctor(monkeypatch, report)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "[WARN] embedder" in result.output
    assert "Fix: Configure an embedding provider." in result.output
    assert "Overall: WARN" in result.output


def test_doctor_failure_exits_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = HealthReport(
        checks=(
            HealthCheck(
                name="database",
                status=HealthStatus.FAIL,
                message="Database is unavailable.",
                remediation="Check POCKET_HOME.",
            ),
        )
    )
    configure_doctor(monkeypatch, report)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "[FAIL] database" in result.output
    assert "Fix: Check POCKET_HOME." in result.output
    assert "Overall: FAIL" in result.output


def test_cli_help_lists_doctor_command() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "doctor" in result.output
    assert "hello" not in result.output


def test_doctor_real_degraded_run_exits_zero(
    tmp_path: Path,
) -> None:
    pocket_home = tmp_path / ".pocket"

    result = runner.invoke(
        app,
        ["doctor"],
        env={
            "POCKET_PROVIDER": "openai",
            "POCKET_MODEL": "test-model",
            "POCKET_API_KEY": "test-key",
            "POCKET_HOME": str(pocket_home),
            "POCKET_MAX_ITERATIONS": "10",
        },
    )

    assert result.exit_code == 0
    assert "[PASS] python" in result.output
    assert "[PASS] database" in result.output
    assert "[PASS] provider" in result.output
    assert "[WARN] embedder" in result.output
    assert "[WARN] sandbox" in result.output
    assert "Overall: WARN" in result.output
    assert "test-key" not in result.output
    assert pocket_home.joinpath("state.db").is_file()
