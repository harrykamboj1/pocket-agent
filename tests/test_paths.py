from pathlib import Path

from pocket.config import Settings
from pocket.paths import PocketPaths, derive_paths, initialize_paths


def test_derive_paths_is_pure_and_uses_configured_home(tmp_path: Path) -> None:
    configured_home = tmp_path / ".pocket"
    settings = Settings(home=configured_home, _env_file=None)

    paths = derive_paths(settings.home)

    assert paths == PocketPaths(
        home=configured_home,
        state_db=configured_home / "state.db",
        traces_dir=configured_home / "traces",
        usage_log=configured_home / "usage.jsonl",
        workspaces_dir=configured_home / "workspaces",
        skills_dir=configured_home / "skills",
        mcp_config=configured_home / "mcp.json",
        soul=configured_home / "SOUL.md",
        memory=configured_home / "MEMORY.md",
        eval_report=configured_home / "eval_report.json",
    )
    assert not configured_home.exists()


def test_every_runtime_path_stays_under_home(tmp_path: Path) -> None:
    paths = derive_paths(tmp_path / ".pocket")

    assert all(
        path == paths.home or path.is_relative_to(paths.home)
        for path in paths.all_paths
    )


def test_initialize_paths_creates_directories_but_not_data_files(
    tmp_path: Path,
) -> None:
    paths = derive_paths(tmp_path / "nested" / ".pocket")

    returned_paths = initialize_paths(paths)

    assert returned_paths is paths
    assert all(directory.is_dir() for directory in paths.directories)
    assert not paths.state_db.exists()
    assert not paths.usage_log.exists()
    assert not paths.mcp_config.exists()
    assert not paths.soul.exists()
    assert not paths.memory.exists()
    assert not paths.eval_report.exists()


def test_initialize_paths_is_idempotent(tmp_path: Path) -> None:
    paths = derive_paths(tmp_path / ".pocket")

    initialize_paths(paths)
    initialize_paths(paths)

    assert all(directory.is_dir() for directory in paths.directories)
