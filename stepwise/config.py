from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str

    # ── Claude model IDs, one per pipeline stage ────────────────────────────
    # Defaults pin the models this project was built against. Model IDs change
    # over time — check Anthropic's model docs before updating, and prefer the
    # current recommended IDs for new deployments:
    #   https://platform.claude.com/docs/en/about-claude/models/overview
    # As of this writing the current IDs are claude-sonnet-5, claude-opus-4-8,
    # and claude-haiku-4-5-20251001. See README "Choosing Claude models".
    structuring_model: str = "claude-haiku-4-5-20251001"   # step extraction (high volume)
    hyde_model: str = "claude-haiku-4-5"                    # HyDE hypothetical-answer generation
    synthesis_model: str = "claude-haiku-4-5"              # streamed answer synthesis
    consolidation_model: str = "claude-sonnet-4-6"        # step consolidation (judgment)

    data_dir: Path = Path("./data")
    db_path: Path = Path("./data/stepwise.db")
    chroma_path: Path = Path("./data/chroma")
    frames_dir: Path = Path("./data/frames")

    # Default library ("workspace") — everything lands here unless a library_id
    # is supplied, preserving single-library behaviour with no configuration.
    default_library_id: str = "local"
    default_library_name: str = "Local"

    model_config = {"env_file": ".env", "populate_by_name": True}

    frame_interval_seconds: int = 5
    embedding_model: str = "all-MiniLM-L6-v2"
    drive_token_path: Path = Path("./data/drive_token.json")

    # Auto-ingestion: poll watched sources on an interval inside the API process
    watcher_poll_enabled: bool = True
    # Bounded to [1, 1440] minutes (max once per day) to avoid runaway polling.
    watcher_poll_interval_minutes: int = Field(default=30, ge=1, le=1440)

    # Optional API key — when set, clients must send X-API-Key (or Authorization: Bearer).
    # Leave unset for local development with no auth.
    api_key: str | None = None

    # Comma-separated allowed origins, or "*" for all.
    # Default "*" is convenient for local dev, where the browser only talks to the
    # Next.js BFF (same-origin) and never hits this API cross-origin directly.
    # In production, set CORS_ORIGINS to your explicit frontend origin(s), e.g.
    #   CORS_ORIGINS="https://app.example.com,https://admin.example.com"
    # A wildcard combined with an API key is flagged at startup (see app.py).
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
