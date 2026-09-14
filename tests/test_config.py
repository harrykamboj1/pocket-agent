from pathlib import Path

import pytest
from pydantic import ValidationError

from pocket.config import Settings, load_settings

POCKET_ENV_VARS = (
    "POCKET_MODEL",
    "POCKET_PROVIDER",
    "POCKET_HOME",
    "POCKET_MAX_ITERATIONS",
    "POCKET_API_KEY",
)


@pytest.fixture(autouse=True)
def clean_pocket_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep local shell configuration from changing deterministic test results."""
    for name in POCKET_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.model == ""
    assert settings.provider == "ollama"
    assert settings.home == Path(".pocket")
    assert settings.max_iterations == 10
    assert settings.api_key is None


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POCKET_PROVIDER", "anthropic")
    settings = Settings(_env_file=None)

    assert settings.provider == "anthropic"


def test_invalid_max_iterations() -> None:
    with pytest.raises(ValidationError):
        Settings(max_iterations=0, _env_file=None)


def test_api_key_not_in_repr() -> None:
    settings = Settings(api_key="not-a-real-secret", _env_file=None)

    assert "not-a-real-secret" not in repr(settings)


def test_load_settings_without_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    settings = load_settings()

    assert settings.provider == "ollama"
    assert settings.loaded_env_path is None


def test_load_settings_discovers_parent_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir = tmp_path / "project"
    nested_dir = project_dir / "src" / "feature"
    nested_dir.mkdir(parents=True)
    dotenv_path = project_dir / ".env"
    dotenv_path.write_text("POCKET_PROVIDER=openai\n", encoding="utf-8")
    monkeypatch.chdir(nested_dir)

    settings = load_settings()

    assert settings.provider == "openai"
    assert settings.loaded_env_path == dotenv_path.resolve()


def test_process_environment_overrides_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("POCKET_PROVIDER=openai\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POCKET_PROVIDER", "anthropic")

    settings = load_settings()

    assert settings.provider == "anthropic"


def test_constructor_overrides_environment_and_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("POCKET_PROVIDER=openai\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POCKET_PROVIDER", "anthropic")

    settings = load_settings(provider="gemini")

    assert settings.provider == "gemini"


def test_loaded_env_path_is_not_a_serialized_setting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("POCKET_PROVIDER=openai\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    settings = load_settings()

    assert settings.loaded_env_path == dotenv_path.resolve()
    assert "loaded_env_path" not in settings.model_dump()
