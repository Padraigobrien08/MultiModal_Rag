from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class WatcherSourceType(str, Enum):
    """Valid watched-source types (also the keys of the watcher fetcher registry)."""
    youtube_channel = "youtube_channel"
    drive_folder = "drive_folder"
    notion_page = "notion_page"
    notion_database = "notion_database"


class Base(DeclarativeBase):
    pass


# Default library ("workspace") id. Mirrors settings.default_library_id but kept
# here as a literal so model defaults don't create a config import cycle.
DEFAULT_LIBRARY_ID = "local"


class LibraryDB(Base):
    """A library / workspace: an isolation boundary for a corpus."""
    __tablename__ = "libraries"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class TutorialDB(Base):
    __tablename__ = "tutorials"

    id = Column(String, primary_key=True)
    library_id = Column(
        String, ForeignKey("libraries.id"), default=DEFAULT_LIBRARY_ID, index=True
    )
    source_url = Column(String, nullable=False)
    title = Column(String)
    source_type = Column(String, default="youtube")
    meta = Column(JSON, default=dict)
    steps = relationship("StepDB", back_populates="tutorial", cascade="all, delete-orphan")


class StepDB(Base):
    __tablename__ = "steps"

    id = Column(String, primary_key=True)
    library_id = Column(
        String, ForeignKey("libraries.id"), default=DEFAULT_LIBRARY_ID, index=True
    )
    tutorial_id = Column(String, ForeignKey("tutorials.id"), nullable=False)
    step_number = Column(Integer, nullable=False)
    title = Column(String)
    description = Column(Text)
    action_type = Column(String)  # click / configure / explain / navigate
    visual_reference = Column(String)  # path to frame image
    timestamp_start = Column(Float)
    timestamp_end = Column(Float)
    transcript_source = Column(Text)
    confidence_score = Column(Float)
    tutorial = relationship("TutorialDB", back_populates="steps")


class JobDB(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    library_id = Column(
        String, ForeignKey("libraries.id"), default=DEFAULT_LIBRARY_ID, index=True
    )
    status = Column(String, default="pending")  # pending | running | done | error
    stage = Column(String, nullable=True)        # downloading | aligning | structuring | indexing
    segments_done = Column(Integer, nullable=True)
    segments_total = Column(Integer, nullable=True)
    tutorial_id = Column(String, nullable=True)
    step_count = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    completed_at = Column(DateTime, nullable=True)  # set when status reaches done | error


class FeedbackDB(Base):
    __tablename__ = "feedback"

    id = Column(String, primary_key=True)
    library_id = Column(
        String, ForeignKey("libraries.id"), default=DEFAULT_LIBRARY_ID, index=True
    )
    query = Column(Text, nullable=False)
    step_id = Column(String, nullable=False)
    helpful = Column(Integer, nullable=False)  # 1 = helpful, -1 = not helpful
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class WatcherDB(Base):
    """Tracks a watched source (YouTube channel, Drive folder, Notion page/database)."""
    __tablename__ = "watchers"

    id = Column(String, primary_key=True)
    library_id = Column(
        String, ForeignKey("libraries.id"), default=DEFAULT_LIBRARY_ID, index=True
    )
    # youtube_channel | drive_folder | notion_page | notion_database
    source_type = Column(String, nullable=False)
    source_id = Column(String, nullable=False)     # channel_id, folder_id, page_id, database_id
    label = Column(String)
    last_seen_at = Column(String, nullable=True)   # ISO 8601 — last time we detected new content
    last_item_id = Column(String, nullable=True)   # last video/file/page ID we queued
    config_json = Column(JSON, default=dict)         # e.g. {"token_path": "...", "recursive": true}
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class QueryLogDB(Base):
    __tablename__ = "query_logs"

    id = Column(String, primary_key=True)
    library_id = Column(
        String, ForeignKey("libraries.id"), default=DEFAULT_LIBRARY_ID, index=True
    )
    query_text = Column(Text, nullable=False)
    hypothetical_text = Column(Text, nullable=True)   # HyDE output
    tutorial_scoped = Column(String, nullable=True)   # tutorial_id if user pinned one
    tutorial_ids_searched = Column(JSON, nullable=True)  # pre-filter result, None = all
    steps_returned = Column(JSON, nullable=True)      # [{step_id, distance, ce_score}]
    answer_text = Column(Text, nullable=True)
    history_length = Column(Integer, default=0)
    latency_hyde_ms = Column(Integer, nullable=True)
    latency_retrieval_ms = Column(Integer, nullable=True)
    latency_synthesis_ms = Column(Integer, nullable=True)
    total_latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# Pydantic models for API / logic layer

class Step(BaseModel):
    id: str
    tutorial_id: str
    library_id: str = DEFAULT_LIBRARY_ID
    step_number: int
    title: str
    description: str
    action_type: Optional[str] = None
    visual_reference: Optional[str] = None
    timestamp_start: Optional[float] = None
    timestamp_end: Optional[float] = None
    transcript_source: Optional[str] = None
    confidence_score: Optional[float] = None


class Tutorial(BaseModel):
    id: str
    library_id: str = DEFAULT_LIBRARY_ID
    source_url: str
    title: Optional[str] = None
    source_type: str = "youtube"
    steps: list[Step] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


class Segment(BaseModel):
    """Intermediate object: transcript + frames before LLM structuring."""
    time_start: float
    time_end: float
    transcript: str
    frame_paths: list[str] = Field(default_factory=list)


# Tables that gained a library_id column and need backfilling on existing DBs.
_LIBRARY_SCOPED_TABLES = (
    "tutorials",
    "steps",
    "jobs",
    "watchers",
    "query_logs",
    "feedback",
)


def _migrate_libraries(engine) -> None:
    """Idempotently bring an existing SQLite DB up to the library-scoped schema.

    ``create_all`` creates the new ``libraries`` table but never ALTERs existing
    tables, so older DBs are missing the ``library_id`` column. Add it where
    absent and backfill rows into the default library.
    """
    with engine.begin() as conn:
        conn.execute(
            text("INSERT OR IGNORE INTO libraries (id, name, created_at) "
                 "VALUES (:id, :name, :ts)"),
            {
                "id": DEFAULT_LIBRARY_ID,
                "name": "Local",
                "ts": datetime.now(timezone.utc),
            },
        )
        for table in _LIBRARY_SCOPED_TABLES:
            cols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if "library_id" not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN library_id VARCHAR"))
            conn.execute(
                text(f"UPDATE {table} SET library_id = :lib WHERE library_id IS NULL"),
                {"lib": DEFAULT_LIBRARY_ID},
            )


def get_engine(db_path: Path):
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    _migrate_libraries(engine)
    return engine
