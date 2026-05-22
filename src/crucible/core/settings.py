from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path.cwd()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CRUCIBLE_",
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: str = "dev"
    log_level: str = "INFO"
    runs_dir: Path = Path(".crucible/runs")
    cache_dir: Path = Path(".crucible/cache")
    reports_dir: Path = Path(".crucible/reports")
    sqlite_path: Path = Path(".crucible/crucible.sqlite")
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 7777
    plugin_modules: str = ""

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    openrouter_api_key: str | None = None

    ollama_url: str = "http://localhost:11434"
    vllm_url: str = "http://localhost:8000/v1"
    llamacpp_url: str = "http://localhost:8080"

    default_output_format: Literal["json", "html"] = "json"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
