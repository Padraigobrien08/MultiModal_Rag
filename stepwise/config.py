from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    claude_model: str = "claude-sonnet-4-6"

    data_dir: Path = Path("./data")
    db_path: Path = Path("./data/stepwise.db")
    chroma_path: Path = Path("./data/chroma")
    frames_dir: Path = Path("./data/frames")

    model_config = {"env_file": ".env", "populate_by_name": True}

    frame_interval_seconds: int = 5
    embedding_model: str = "all-MiniLM-L6-v2"
    # Cheaper model for high-volume schema-bound structuring; Sonnet used for consolidation/retrieval
    structuring_model: str = "claude-haiku-4-5-20251001"
    drive_token_path: Path = Path("./data/drive_token.json")

    # Auto-ingestion: poll watched sources on an interval inside the API process
    watcher_poll_enabled: bool = True
    watcher_poll_interval_minutes: int = 30

    # Optional API key — when set, clients must send X-API-Key (or Authorization: Bearer).
    # Leave unset for local development with no auth.
    api_key: str | None = None

    # Comma-separated allowed origins, or "*" for all (default — convenient for local dev).
    cors_origins: str = "*"

    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

settings = Settings()

# ensure data dirs exist
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.frames_dir.mkdir(parents=True, exist_ok=True)
