from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str
    GROQ_API_KEY: str
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    CEREBRAS_API_KEY: str | None = None
    CEREBRAS_MODEL: str = "gpt-oss-120b"

    # Qdrant vector store
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: str | None = None
    QDRANT_URL: str | None = None
    QDRANT_COLLECTION_NAME: str = "company_analyses"
    QDRANT_DIMENSION: int = 384

    # Fully automated pipeline scheduler
    SCHEDULER_INTERVAL_MINUTES: int = 10
    SCHEDULER_MAX_PAGES: int = 50

    # Telegram notifications (optional; disabled when not set)
    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_CHAT_ID: str | None = None


settings = Settings()