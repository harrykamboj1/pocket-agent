"""Pure runtime-path derivation and explicit directory initialization."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PocketPaths:
    """Every runtime location owned by one Pocket Agent home directory."""

    home: Path
    state_db: Path
    traces_dir: Path
    usage_log: Path
    workspaces_dir: Path
    skills_dir: Path
    mcp_config: Path
    soul: Path
    memory: Path
    eval_report: Path

    @property
    def directories(self) -> tuple[Path, ...]:
        """Return the directories that initialization must create."""
        return (self.home, self.traces_dir, self.workspaces_dir, self.skills_dir)

    @property
    def all_paths(self) -> tuple[Path, ...]:
        """Return every derived runtime location for validation and inspection."""
        return (
            self.home,
            self.state_db,
            self.traces_dir,
            self.usage_log,
            self.workspaces_dir,
            self.skills_dir,
            self.mcp_config,
            self.soul,
            self.memory,
            self.eval_report,
        )


def derive_paths(home: Path | str) -> PocketPaths:
    """Derive runtime locations without reading or changing the filesystem."""
    root = Path(home).expanduser().resolve()
    return PocketPaths(
        home=root,
        state_db=root / "state.db",
        traces_dir=root / "traces",
        usage_log=root / "usage.jsonl",
        workspaces_dir=root / "workspaces",
        skills_dir=root / "skills",
        mcp_config=root / "mcp.json",
        soul=root / "SOUL.md",
        memory=root / "MEMORY.md",
        eval_report=root / "eval_report.json",
    )


def initialize_paths(paths: PocketPaths) -> PocketPaths:
    """Create Pocket-owned directories without creating runtime data files."""
    for directory in paths.directories:
        directory.mkdir(parents=True, exist_ok=True)
    return paths
