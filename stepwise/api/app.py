import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import parse_qs, urlparse

import chromadb
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from stepwise.api.middleware import APIKeyMiddleware, RequestIDMiddleware
from stepwise.config import settings
from stepwise.indexing import get_db_session
from stepwise.indexing.indexer import check_vector_consistency, delete_tutorial_vectors
from stepwise.ingestion.tasks import (
    run_drive_ingestion,
    run_image_ingestion,
    run_notion_ingestion_api,
    run_youtube_ingestion,
)
from stepwise.logging_config import setup_logging
from stepwise.models import (
    FeedbackDB,
    JobDB,
    LibraryDB,
    TutorialDB,
    WatcherDB,
    WatcherSourceType,
)
from stepwise.retrieval import query_steps, query_steps_stream

DEFAULT_LIBRARY_ID = settings.default_library_id

# Public-input bounds
MAX_QUERY_LEN = 2000
MAX_HISTORY_TURNS = 50
MAX_URL_LEN = 2048
MAX_TITLE_LEN = 500
MAX_ID_LEN = 256
MAX_UPLOAD_FILES = 100
MAX_UPLOAD_BYTES = 25 * 1024 * 1024          # 25 MB per file
MAX_TOTAL_UPLOAD_BYTES = 200 * 1024 * 1024   # 200 MB per request


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    with get_db_session() as session:
        now = datetime.now(timezone.utc)
        session.query(JobDB).filter(
            JobDB.status.in_(["pending", "running"])
        ).update({
            "status": "error",
            "error": "Server restarted while job was in progress",
            "updated_at": now,
            "completed_at": now,
        })
        session.commit()
    # One-time backfill: tag pre-scoping Chroma vectors into the default library.
    from stepwise.indexing.indexer import migrate_chroma_default_library
    migrate_chroma_default_library()
    if settings.watcher_poll_enabled:
        from stepwise.ingestion import scheduler
        scheduler.start(settings.watcher_poll_interval_minutes, _poll_all_active)
    yield
    from stepwise.ingestion import scheduler
    scheduler.shutdown()


app = FastAPI(title="Stepwise", version="0.1.0", lifespan=lifespan)


def _canonical_url(url: str) -> str:
    """Normalise YouTube URLs to a canonical form for duplicate detection.

    Handles youtu.be short links, extra query params, and playlist noise so
    the same video submitted twice with different URL formats is caught.
    """
    # youtu.be/VIDEO_ID
    m = re.match(r"https?://youtu\.be/([A-Za-z0-9_-]+)", url)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"
    parsed = urlparse(url)
    if "youtube.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        if "v" in qs:
            return f"https://www.youtube.com/watch?v={qs['v'][0]}"
    return url

_cors_origins = settings.cors_origin_list()
if _cors_origins == ["*"] and settings.api_key:
    logging.getLogger(__name__).warning(
        "CORS is set to '*' while an API key is configured — set CORS_ORIGINS to "
        "explicit frontend origin(s) for production."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)
app.add_middleware(APIKeyMiddleware)
app.add_middleware(RequestIDMiddleware)


class IngestRequest(BaseModel):
    url: str = Field(min_length=1, max_length=MAX_URL_LEN)
    title: Optional[str] = Field(default=None, max_length=MAX_TITLE_LEN)
    library_id: str = Field(default=DEFAULT_LIBRARY_ID, max_length=MAX_ID_LEN)


class DriveIngestRequest(BaseModel):
    source_url: str = Field(min_length=1, max_length=MAX_URL_LEN)
    title: str = Field(min_length=1, max_length=MAX_TITLE_LEN)
    video_id: str = Field(min_length=1, max_length=MAX_ID_LEN)
    transcript: list[dict]   # [{text, start, duration}]
    frames: list[dict]       # [{path, timestamp}]
    library_id: str = Field(default=DEFAULT_LIBRARY_ID, max_length=MAX_ID_LEN)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=MAX_QUERY_LEN)
    library_id: str = Field(default=DEFAULT_LIBRARY_ID, max_length=MAX_ID_LEN)
    tutorial_id: Optional[str] = Field(default=None, max_length=MAX_ID_LEN)
    top_k: int = Field(default=5, ge=1, le=50)
    # [{role, text}] — last N exchanges for multi-turn context
    history: list[dict] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)


class FeedbackRequest(BaseModel):
    query: str = Field(min_length=1, max_length=MAX_QUERY_LEN)
    step_id: str = Field(min_length=1, max_length=MAX_ID_LEN)
    helpful: bool
    library_id: str = Field(default=DEFAULT_LIBRARY_ID, max_length=MAX_ID_LEN)


class NotionIngestRequest(BaseModel):
    page_id: str = Field(min_length=1, max_length=MAX_ID_LEN)
    notion_token: str = Field(min_length=1, max_length=MAX_ID_LEN)
    title: Optional[str] = Field(default=None, max_length=MAX_TITLE_LEN)
    library_id: str = Field(default=DEFAULT_LIBRARY_ID, max_length=MAX_ID_LEN)


class WatcherCreateRequest(BaseModel):
    source_type: WatcherSourceType
    source_id: str = Field(min_length=1, max_length=MAX_ID_LEN)
    label: Optional[str] = Field(default=None, max_length=MAX_ID_LEN)
    config: dict = Field(default_factory=dict)  # token_path, notion_token, recursive, etc.
    library_id: str = Field(default=DEFAULT_LIBRARY_ID, max_length=MAX_ID_LEN)


class LibraryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_TITLE_LEN)


@app.post("/libraries", status_code=201)
def create_library(req: LibraryCreateRequest) -> dict:
    library_id = str(uuid.uuid4())
    with get_db_session() as session:
        session.add(LibraryDB(id=library_id, name=req.name))
        session.commit()
    return {"id": library_id, "name": req.name}


@app.get("/libraries")
def list_libraries() -> list:
    with get_db_session() as session:
        libs = session.query(LibraryDB).order_by(LibraryDB.created_at).all()
        return [
            {
                "id": lib.id,
                "name": lib.name,
                "created_at": lib.created_at.isoformat() if lib.created_at else None,
            }
            for lib in libs
        ]


@app.post("/ingest", status_code=202)
def ingest(req: IngestRequest, background_tasks: BackgroundTasks) -> dict:
    canonical = _canonical_url(req.url)
    with get_db_session() as session:
        existing = (
            session.query(TutorialDB)
            .filter_by(source_url=canonical, library_id=req.library_id)
            .first()
        )
        if existing:
            return {"tutorial_id": existing.id, "step_count": len(existing.steps), "existing": True}
        # Also check against the raw URL in case it was previously stored unnormalised
        existing = (
            session.query(TutorialDB)
            .filter_by(source_url=req.url, library_id=req.library_id)
            .first()
        )
        if existing:
            return {"tutorial_id": existing.id, "step_count": len(existing.steps), "existing": True}

    job_id = str(uuid.uuid4())
    with get_db_session() as session:
        session.add(JobDB(id=job_id, status="pending", library_id=req.library_id))
        session.commit()

    background_tasks.add_task(
        run_youtube_ingestion, job_id, req.url, req.title, library_id=req.library_id
    )
    return {"job_id": job_id}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    with get_db_session() as session:
        job = session.get(JobDB, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return {
            "job_id": job.id,
            "status": job.status,
            "stage": job.stage,
            "segments_done": job.segments_done,
            "segments_total": job.segments_total,
            "tutorial_id": job.tutorial_id,
            "step_count": job.step_count,
            "error": job.error,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }


@app.get("/tutorials/{tutorial_id}")
def get_tutorial(tutorial_id: str) -> dict:
    with get_db_session() as session:
        t = session.get(TutorialDB, tutorial_id)
        if not t:
            raise HTTPException(status_code=404, detail="Tutorial not found")
        return {
            "id": t.id,
            "title": t.title,
            "source_url": t.source_url,
            "source_type": t.source_type,
            "meta": t.meta,
            "steps": [
                {
                    "id": s.id,
                    "step_number": s.step_number,
                    "title": s.title,
                    "description": s.description,
                    "action_type": s.action_type,
                    "visual_reference": s.visual_reference,
                    "timestamp_start": s.timestamp_start,
                    "timestamp_end": s.timestamp_end,
                    "confidence_score": s.confidence_score,
                }
                for s in sorted(t.steps, key=lambda s: s.step_number)
            ],
        }


@app.get("/tutorials")
def list_tutorials(library_id: str = Query(default=DEFAULT_LIBRARY_ID)) -> list:
    with get_db_session() as session:
        tutorials = (
            session.query(TutorialDB)
            .filter_by(library_id=library_id)
            .order_by(TutorialDB.id)
            .all()
        )
        return [
            {
                "id": t.id,
                "title": t.title,
                "source_url": t.source_url,
                "source_type": t.source_type,
                "step_count": len(t.steps),
                "potential_duplicate_of": (t.meta or {}).get("potential_duplicate_of"),
            }
            for t in tutorials
        ]


def _delete_tutorial_data(tutorial_id: str) -> None:
    """Remove tutorial + steps from SQLite and all vectors (steps + centroid) from ChromaDB."""
    with get_db_session() as session:
        t = session.get(TutorialDB, tutorial_id)
        if not t:
            return
        session.delete(t)
        session.commit()

    try:
        delete_tutorial_vectors(tutorial_id)
    except Exception:
        logging.getLogger(__name__).warning(
            "ChromaDB vector cleanup failed for tutorial %s", tutorial_id, exc_info=True
        )


@app.delete("/tutorials/{tutorial_id}", status_code=204)
def delete_tutorial(tutorial_id: str):
    with get_db_session() as session:
        t = session.get(TutorialDB, tutorial_id)
        if not t:
            raise HTTPException(status_code=404, detail="Tutorial not found")
    _delete_tutorial_data(tutorial_id)


@app.post("/tutorials/{tutorial_id}/reingest", status_code=202)
def reingest_tutorial(tutorial_id: str, background_tasks: BackgroundTasks) -> dict:
    with get_db_session() as session:
        t = session.get(TutorialDB, tutorial_id)
        if not t:
            raise HTTPException(status_code=404, detail="Tutorial not found")
        url = t.source_url
        title = t.title
        library_id = t.library_id or DEFAULT_LIBRARY_ID

    _delete_tutorial_data(tutorial_id)

    job_id = str(uuid.uuid4())
    with get_db_session() as session:
        session.add(JobDB(id=job_id, status="pending", library_id=library_id))
        session.commit()

    background_tasks.add_task(
        run_youtube_ingestion, job_id, url, title, library_id=library_id
    )
    return {"job_id": job_id}


@app.post("/ingest/images", status_code=202)
async def ingest_images_endpoint(
    background_tasks: BackgroundTasks,
    title: str = Form(..., min_length=1, max_length=MAX_TITLE_LEN),
    library_id: str = Form(default=DEFAULT_LIBRARY_ID, max_length=MAX_ID_LEN),
    files: list[UploadFile] = File(...),
) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files (max {MAX_UPLOAD_FILES})",
        )

    file_data: list[tuple[str, bytes]] = []
    total = 0
    for i, f in enumerate(files):
        data = await f.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File {f.filename or i} exceeds {MAX_UPLOAD_BYTES} bytes",
            )
        total += len(data)
        if total > MAX_TOTAL_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Upload exceeds total limit of {MAX_TOTAL_UPLOAD_BYTES} bytes",
            )
        file_data.append((f.filename or f"file_{i}", data))

    job_id = str(uuid.uuid4())
    with get_db_session() as session:
        session.add(JobDB(id=job_id, status="pending", library_id=library_id))
        session.commit()

    background_tasks.add_task(
        run_image_ingestion, job_id, file_data, title, library_id=library_id
    )
    return {"job_id": job_id}


@app.post("/ingest/notion", status_code=202)
def ingest_notion_endpoint(req: NotionIngestRequest, background_tasks: BackgroundTasks) -> dict:
    # Idempotency: canonical Notion URL
    notion_url = f"https://www.notion.so/{req.page_id.replace('-', '')}"
    with get_db_session() as session:
        existing = (
            session.query(TutorialDB)
            .filter_by(source_url=notion_url, library_id=req.library_id)
            .first()
        )
        if existing:
            return {"tutorial_id": existing.id, "step_count": len(existing.steps), "existing": True}

    job_id = str(uuid.uuid4())
    with get_db_session() as session:
        session.add(JobDB(id=job_id, status="pending", library_id=req.library_id))
        session.commit()

    background_tasks.add_task(
        run_notion_ingestion_api, job_id, req.page_id, req.title, req.notion_token,
        library_id=req.library_id,
    )
    return {"job_id": job_id}


@app.post("/ingest/drive", status_code=202)
def ingest_drive_endpoint(req: DriveIngestRequest, background_tasks: BackgroundTasks) -> dict:
    # Idempotency check
    with get_db_session() as session:
        existing = (
            session.query(TutorialDB)
            .filter_by(source_url=req.source_url, library_id=req.library_id)
            .first()
        )
        if existing:
            return {"tutorial_id": existing.id, "step_count": len(existing.steps), "existing": True}

    job_id = str(uuid.uuid4())
    with get_db_session() as session:
        session.add(JobDB(id=job_id, status="pending", library_id=req.library_id))
        session.commit()

    background_tasks.add_task(
        run_drive_ingestion, job_id, req.model_dump(), library_id=req.library_id
    )
    return {"job_id": job_id}


@app.get("/jobs")
def list_jobs(
    status: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=200),
    library_id: str = Query(default=DEFAULT_LIBRARY_ID),
) -> list:
    """Return recent jobs, optionally filtered by status (comma-separated)."""
    with get_db_session() as session:
        q = (
            session.query(JobDB)
            .filter(JobDB.library_id == library_id)
            .order_by(JobDB.created_at.desc())
        )
        if status:
            statuses = status.split(",")
            q = q.filter(JobDB.status.in_(statuses))
        jobs = q.limit(limit).all()
        return [
            {
                "job_id": j.id,
                "status": j.status,
                "stage": j.stage,
                "segments_done": j.segments_done,
                "segments_total": j.segments_total,
                "tutorial_id": j.tutorial_id,
                "step_count": j.step_count,
                "error": j.error,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "updated_at": j.updated_at.isoformat() if j.updated_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in jobs
        ]


@app.post("/watchers", status_code=201)
def create_watcher(req: WatcherCreateRequest) -> dict:
    watcher_id = str(uuid.uuid4())
    with get_db_session() as session:
        session.add(WatcherDB(
            id=watcher_id,
            library_id=req.library_id,
            source_type=req.source_type.value,
            source_id=req.source_id,
            label=req.label or req.source_id,
            config_json=req.config,
        ))
        session.commit()
    return {"watcher_id": watcher_id}


@app.get("/watchers")
def list_watchers(library_id: str = Query(default=DEFAULT_LIBRARY_ID)) -> list:
    with get_db_session() as session:
        watchers = (
            session.query(WatcherDB)
            .filter(WatcherDB.library_id == library_id)
            .order_by(WatcherDB.created_at.desc())
            .all()
        )
        return [
            {
                "id": w.id,
                "source_type": w.source_type,
                "source_id": w.source_id,
                "label": w.label,
                "last_seen_at": w.last_seen_at,
                "last_item_id": w.last_item_id,
                "active": w.active,
                "created_at": w.created_at.isoformat() if w.created_at else None,
            }
            for w in watchers
        ]


@app.delete("/watchers/{watcher_id}", status_code=204)
def delete_watcher(watcher_id: str):
    with get_db_session() as session:
        w = session.get(WatcherDB, watcher_id)
        if not w:
            raise HTTPException(status_code=404, detail="Watcher not found")
        session.delete(w)
        session.commit()


def _poll_all_active(tasks) -> list[str]:
    """Poll every active watcher, enqueuing ingestion via `tasks`. Returns new job IDs.

    `tasks` only needs an `add_task(fn, *args)` method, so this works with both
    FastAPI's BackgroundTasks and the scheduler's thread-pool shim.
    """
    import logging

    from stepwise.ingestion.watcher import poll_watcher
    total_jobs: list[str] = []
    with get_db_session() as session:
        watchers = session.query(WatcherDB).filter_by(active=True).all()
        for watcher in watchers:
            try:
                total_jobs.extend(poll_watcher(watcher, session, tasks))
            except Exception as e:
                logging.getLogger(__name__).warning("Watcher %s poll failed: %s", watcher.id, e)
        session.commit()
    return total_jobs


@app.post("/watchers/poll", status_code=202)
def poll_all_watchers(background_tasks: BackgroundTasks) -> dict:
    """Trigger a poll of all active watchers. Safe to call on a cron schedule."""
    total_jobs = _poll_all_active(background_tasks)
    return {"jobs_queued": len(total_jobs), "job_ids": total_jobs}


@app.get("/watchers/scheduler")
def get_scheduler_status() -> dict:
    """Report whether autonomous polling is running and at what interval."""
    from stepwise.ingestion import scheduler
    return scheduler.status()


@app.post("/watchers/{watcher_id}/poll", status_code=202)
def poll_watcher_endpoint(watcher_id: str, background_tasks: BackgroundTasks) -> dict:
    """Poll a single watcher immediately."""
    from stepwise.ingestion.watcher import poll_watcher
    with get_db_session() as session:
        watcher = session.get(WatcherDB, watcher_id)
        if not watcher:
            raise HTTPException(status_code=404, detail="Watcher not found")
        job_ids = poll_watcher(watcher, session, background_tasks)
        session.commit()
    return {"jobs_queued": len(job_ids), "job_ids": job_ids}


@app.post("/query")
def query(req: QueryRequest) -> StreamingResponse:
    return StreamingResponse(
        query_steps_stream(
            req.query, library_id=req.library_id, tutorial_id=req.tutorial_id,
            top_k=req.top_k, history=req.history,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/query/sync")
def query_sync(req: QueryRequest) -> dict:
    """Non-streaming query — returns JSON {answer, steps}. Used by eval, Zendesk, and tests."""
    return query_steps(
        req.query, library_id=req.library_id, tutorial_id=req.tutorial_id,
        top_k=req.top_k, history=req.history,
    )


@app.post("/feedback", status_code=201)
def submit_feedback(req: FeedbackRequest) -> dict:
    with get_db_session() as session:
        session.add(FeedbackDB(
            id=str(uuid.uuid4()),
            library_id=req.library_id,
            query=req.query,
            step_id=req.step_id,
            helpful=1 if req.helpful else -1,
        ))
        session.commit()
    return {"ok": True}


@app.post("/admin/reindex", status_code=202)
def reindex_all(background_tasks: BackgroundTasks) -> dict:
    """Re-embed all tutorials with the current embedding function.

    Run this after changing _fuse_embeddings to keep ChromaDB consistent.
    """
    background_tasks.add_task(_run_reindex)
    return {"message": "Reindex started"}


def _run_reindex() -> None:
    import logging
    log = logging.getLogger(__name__)
    from pathlib import Path

    from PIL import Image

    from stepwise.indexing.indexer import _fuse_embeddings, _get_chroma
    from stepwise.ml.registry import get_clip_encoder, get_text_encoder

    with get_db_session() as session:
        tutorials = session.query(TutorialDB).all()
        tutorial_data = [
            (t.id, t.title, t.source_url, t.source_type, t.meta,
             t.library_id or DEFAULT_LIBRARY_ID,
             [(s.id, s.title, s.description, s.visual_reference,
               s.timestamp_start, s.step_number) for s in t.steps])
            for t in tutorials
        ]

    chroma = _get_chroma()
    steps_col = chroma.get_or_create_collection("steps")
    centroids_col = chroma.get_or_create_collection("tutorial_centroids")
    text_model = get_text_encoder()
    clip_model = get_clip_encoder()

    for tid, title, source_url, source_type, meta, library_id, steps in tutorial_data:
        if not steps:
            continue
        log.info("Re-indexing %s (%d steps)", title, len(steps))
        texts = [f"{s[1]}. {s[2]}" for s in steps]
        text_embs = text_model.encode(texts, convert_to_numpy=True)

        fused = []
        for step, text_emb in zip(steps, text_embs):
            img_emb = None
            vr = step[3]
            if vr and Path(vr).exists():
                img_emb = clip_model.encode(Image.open(vr).convert("RGB"), convert_to_numpy=True)
            fused.append(_fuse_embeddings(text_emb, img_emb).tolist())

        steps_col.upsert(
            ids=[s[0] for s in steps],
            embeddings=fused,
            documents=texts,
            metadatas=[
                {"library_id": library_id, "tutorial_id": tid, "step_number": s[5],
                 "step_id": s[0], "timestamp_start": s[4] or 0,
                 "visual_reference": s[3] or ""}
                for s in steps
            ],
        )

        import numpy as np
        centroid = np.mean(fused, axis=0)
        centroid = centroid / np.linalg.norm(centroid)
        centroids_col.upsert(
            ids=[tid],
            embeddings=[centroid.tolist()],
            documents=[title or ""],
            metadatas=[{"library_id": library_id, "tutorial_id": tid}],
        )

    log.info("Reindex complete — %d tutorials", len(tutorial_data))


@app.get("/admin/consistency")
def get_vector_consistency() -> dict:
    """Report SQLite↔Chroma drift: missing vectors, orphaned vectors, stale centroids."""
    return check_vector_consistency()


@app.get("/admin/query-logs")
def get_query_logs(
    limit: int = Query(default=500, ge=1, le=2000),
    since: Optional[str] = None,
    library_id: str = Query(default=DEFAULT_LIBRARY_ID),
) -> list:
    from datetime import timedelta

    from stepwise.models import QueryLogDB
    with get_db_session() as session:
        q = (
            session.query(QueryLogDB)
            .filter(QueryLogDB.library_id == library_id)
            .order_by(QueryLogDB.created_at.desc())
        )
        if since:
            delta = {
                "24h": timedelta(hours=24),
                "7d": timedelta(days=7),
                "30d": timedelta(days=30),
            }.get(since)
            if delta:
                q = q.filter(QueryLogDB.created_at >= datetime.now(timezone.utc) - delta)
        logs = q.limit(limit).all()

        # Batch-load feedback keyed by query_text
        query_texts = [entry.query_text for entry in logs]
        fb_rows = (
            session.query(FeedbackDB).filter(FeedbackDB.query.in_(query_texts)).all()
            if query_texts else []
        )
        fb_by_query: dict[str, list] = {}
        for fb in fb_rows:
            fb_by_query.setdefault(fb.query, []).append(
                {"step_id": fb.step_id, "helpful": fb.helpful > 0}
            )

        return [
            {
                "id": entry.id,
                "query_text": entry.query_text,
                "hypothetical_text": entry.hypothetical_text,
                "tutorial_scoped": entry.tutorial_scoped,
                "tutorial_ids_searched": entry.tutorial_ids_searched,
                "steps_returned": entry.steps_returned,
                "answer_text": entry.answer_text,
                "history_length": entry.history_length,
                "latency_hyde_ms": entry.latency_hyde_ms,
                "latency_retrieval_ms": entry.latency_retrieval_ms,
                "latency_synthesis_ms": entry.latency_synthesis_ms,
                "total_latency_ms": entry.total_latency_ms,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "feedback": fb_by_query.get(entry.query_text, []),
            }
            for entry in logs
        ]


@app.get("/admin/stats")
def get_admin_stats(library_id: str = Query(default=DEFAULT_LIBRARY_ID)) -> dict:
    from datetime import timedelta

    from stepwise.models import QueryLogDB
    with get_db_session() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        base = session.query(QueryLogDB).filter(QueryLogDB.library_id == library_id)
        queries_24h = base.filter(QueryLogDB.created_at >= cutoff).count()
        queries_total = (
            session.query(QueryLogDB)
            .filter(QueryLogDB.library_id == library_id)
            .count()
        )
        return {"queries_24h": queries_24h, "queries_total": queries_total}


@app.get("/gaps")
def get_gaps(
    force: bool = False,
    library_id: str = Query(default=DEFAULT_LIBRARY_ID),
) -> list:
    """
    Analyse recent query logs for topics with poor coverage within a library.

    Results are cached per library for 1 hour. Pass ?force=true to recompute
    immediately. Returns a list of gap objects sorted by query_count descending.
    """
    from stepwise.analysis.gap_detector import detect_gaps
    return detect_gaps(force=force, library_id=library_id)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness probe: verify the DB is writable and Chroma is reachable.

    Unlike /health, this touches real dependencies, but deliberately avoids
    loading ML models so it stays cheap enough for orchestrator probes.
    Returns 503 with a per-check breakdown when a dependency is unavailable.
    """
    checks: dict[str, str] = {}
    ok = True

    # DB path writable and reachable.
    try:
        db_dir = settings.db_path.parent
        if not os.access(db_dir, os.W_OK):
            raise OSError(f"{db_dir} is not writable")
        if settings.db_path.exists() and not os.access(settings.db_path, os.W_OK):
            raise OSError(f"{settings.db_path} is not writable")
        with get_db_session() as session:
            session.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as exc:
        ok = False
        checks["db"] = f"error: {exc}"

    # Chroma reachable (no embedding models loaded).
    try:
        chromadb.PersistentClient(path=str(settings.chroma_path)).heartbeat()
        checks["chroma"] = "ok"
    except Exception as exc:
        ok = False
        checks["chroma"] = f"error: {exc}"

    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ready" if ok else "not ready", "checks": checks},
    )
