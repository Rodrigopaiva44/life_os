"""
infrastructure/settings.py
==========================
Configuração centralizada via pydantic-settings.
Lê variáveis de ambiente e/ou arquivo .env. Nunca hardcode credenciais.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── PostgreSQL ─────────────────────────────────────────────────────────────
    postgres_user:     str = Field(default="lifeos")
    postgres_password: str = Field(...)          # obrigatório – sem default
    postgres_host:     str = Field(default="localhost")
    postgres_port:     int = Field(default=5432)
    postgres_db:       str = Field(default="lifeos_db")

    # ── App ────────────────────────────────────────────────────────────────────
    app_env:   str = Field(default="development")
    log_level: str = Field(default="INFO")

    # ── Telegram ───────────────────────────────────────────────────────────────
    telegram_bot_token: str = Field(...)   # obrigatório – sem default

    # ── Google Gemini ──────────────────────────────────────────────────────────
    gemini_api_key: str = Field(...)       # obrigatório – sem default

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


# Singleton – importado pelos outros módulos de infra.
settings = Settings()
