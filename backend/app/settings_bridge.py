import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv


def _load_env():
    """Load .env file if it exists."""
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)


# 先加载环境变量，再定义类
_load_env()


def _resolve_path(value: str) -> Path:
    """Resolve a relative path against the backend directory."""
    p = Path(value)
    if p.is_absolute():
        return p
    backend_root = Path(__file__).resolve().parent.parent
    return (backend_root / p).resolve()


@dataclass(frozen=True)
class AppSettingsBridge:
    PROJECT_ROOT: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent.parent)
    BACKEND_ROOT: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    APP_HOME: Path = field(default_factory=lambda: _resolve_path(
        os.getenv("AGENT_PLAYGROUND_APP_HOME", "./data")
    ))
    BUNDLED_SKILLS_ROOT: Path = field(default_factory=lambda: _resolve_path(
        os.getenv("AGENT_PLAYGROUND_BUNDLED_SKILLS_ROOT", "./skills")
    ))
    BUNDLED_RUNTIME_ROOT: Path = field(default_factory=lambda: _resolve_path(
        os.getenv("AGENT_PLAYGROUND_BUNDLED_RUNTIME_ROOT", "./.runtime")
    ))
    APP_ENV_PATH: Path = field(default_factory=lambda: _resolve_path(
        os.getenv("AGENT_PLAYGROUND_ENV_PATH", "./.env")
    ))

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    SKILLHUB_API_KEY: str = os.getenv("SKILLHUB_API_KEY", "")
    SKILLHUB_BASE_URL: str = os.getenv("SKILLHUB_BASE_URL", "")
    SKILLHUB_TIMEOUT_SECONDS: int = int(os.getenv("SKILLHUB_TIMEOUT_SECONDS", "15"))

    EXCEL_DATA_ROOT: str = os.getenv("EXCEL_DATA_ROOT", "./backend/data/excel_inbox")
    SQL_DEFAULT_STATEMENT_TIMEOUT_SECONDS: int = int(os.getenv("SQL_DEFAULT_STATEMENT_TIMEOUT_SECONDS", "30"))
    SQL_MAX_ROWS: int = int(os.getenv("SQL_MAX_ROWS", "5000"))
    ARTIFACT_PUBLIC_BASE_URL: str = os.getenv("ARTIFACT_PUBLIC_BASE_URL", "http://127.0.0.1:8011/artifacts")


settings = AppSettingsBridge()
