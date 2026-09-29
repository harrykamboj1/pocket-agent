import typer

from pocket.config import load_settings
from pocket.ops.health import HealthReport, run_health_checks

app = typer.Typer(help="Pocket Agent CLI", no_args_is_help=True)


@app.callback()
def cli() -> None:
    """Inspect and operate Pocket Agent."""


def render_health_report(report: HealthReport) -> None:
    """Render a structured health report for terminal users."""

    for check in report.checks:
        label = check.status.value.upper()

        typer.echo(f"[{label}] {check.name}: {check.message}")

        if check.remediation is not None:
            typer.echo(f"  Fix: {check.remediation}")

    typer.echo()
    typer.echo(f"Overall: {report.status.value.upper()}")


@app.command()
def doctor() -> None:
    """Check whether Pocket Agent can run correctly."""
    settings = load_settings()
    report = run_health_checks(settings)

    render_health_report(report)

    if report.exit_code != 0:
        raise typer.Exit(code=report.exit_code)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
