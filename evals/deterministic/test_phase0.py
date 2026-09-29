"""Phase 0 acceptance scenarios exercised through public boundaries."""

from pathlib import Path

from typer.testing import CliRunner

from pocket.cli import app
from pocket.db.connect import connect_database
from pocket.db.migrate import migrate_database
from pocket.paths import derive_paths, initialize_paths

runner = CliRunner()


def doctor_environment(home: Path, *, model: str) -> dict[str, str]:
    """Return an isolated, non-network doctor configuration."""

    return {
        "POCKET_PROVIDER": "openai",
        "POCKET_MODEL": model,
        "POCKET_API_KEY": "deterministic-eval-key",
        "POCKET_HOME": str(home),
        "POCKET_MAX_ITERATIONS": "10",
    }


def test_eval_doctor_reports_visible_optional_degradation(tmp_path: Path) -> None:
    pocket_home = tmp_path / "degraded"

    result = runner.invoke(
        app,
        ["doctor"],
        env=doctor_environment(pocket_home, model="test-model"),
    )

    assert result.exit_code == 0
    assert "[PASS] database" in result.output
    assert "[WARN] embedder" in result.output
    assert "[WARN] sandbox" in result.output
    assert "Overall: WARN" in result.output
    assert "deterministic-eval-key" not in result.output
    assert pocket_home.joinpath("state.db").is_file()


def test_eval_doctor_rejects_missing_required_model(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["doctor"],
        env=doctor_environment(tmp_path / "missing-model", model=""),
    )

    assert result.exit_code == 1
    assert "[FAIL] provider" in result.output
    assert "Fix: Set POCKET_MODEL." in result.output
    assert "Overall: FAIL" in result.output
    assert "deterministic-eval-key" not in result.output


def test_eval_fact_fts_index_tracks_full_row_lifecycle(tmp_path: Path) -> None:
    paths = initialize_paths(derive_paths(tmp_path / "database"))
    connection = connect_database(paths.state_db)

    try:
        assert migrate_database(connection) == 2

        fact_id = connection.execute(
            "INSERT INTO facts(subject, content) VALUES (?, ?)",
            ("project", "Pocket uses lexical retrieval"),
        ).lastrowid

        inserted = connection.execute(
            "SELECT rowid FROM facts_fts WHERE facts_fts MATCH ?",
            ("lexical",),
        ).fetchall()
        assert [row["rowid"] for row in inserted] == [fact_id]

        connection.execute(
            "UPDATE facts SET content = ? WHERE id = ?",
            ("Pocket uses searchable memory", fact_id),
        )

        old_match = connection.execute(
            "SELECT rowid FROM facts_fts WHERE facts_fts MATCH ?",
            ("lexical",),
        ).fetchall()
        new_match = connection.execute(
            "SELECT rowid FROM facts_fts WHERE facts_fts MATCH ?",
            ("searchable",),
        ).fetchall()

        assert old_match == []
        assert [row["rowid"] for row in new_match] == [fact_id]

        connection.execute("DELETE FROM facts WHERE id = ?", (fact_id,))

        deleted = connection.execute(
            "SELECT rowid FROM facts_fts WHERE facts_fts MATCH ?",
            ("searchable",),
        ).fetchall()
        assert deleted == []
    finally:
        connection.close()
