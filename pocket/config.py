from pathlib import Path

from dotenv import find_dotenv
from pydantic import Field, PrivateAttr, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POCKET_", extra="ignore")

    model: str = Field(
        default="",
        description="Pocket Agent model to use for generating responses.",
    )
    provider: str = Field(
        default="ollama",
        description="Provider to use for generating responses.",
    )
    home: Path = Field(
        default=Path(".pocket"),
        description="Home directory for Pocket Agent.",
    )
    max_iterations: int = Field(
        default=10,
        ge=1,
        description="Maximum number of iterations for generating responses.",
    )
    api_key: SecretStr | None = Field(
        default=None, description="API key for the provider."
    )
    _loaded_env_path: Path | None = PrivateAttr(default=None)

    @property
    def loaded_env_path(self) -> Path | None:
        """Return the dotenv file used to create these settings, if one was found."""
        return self._loaded_env_path


def load_settings(**overrides: object) -> Settings:
    """Load validated settings while making the selected dotenv file observable."""
    dotenv_value = find_dotenv(usecwd=True)
    dotenv_path = Path(dotenv_value).resolve() if dotenv_value else None

    settings = Settings(_env_file=dotenv_path, **overrides)
    settings._loaded_env_path = dotenv_path
    return settings
