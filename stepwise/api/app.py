import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import chromadb

from stepwise.models import Tutorial, JobDB, TutorialDB, StepDB, FeedbackDB, WatcherDB
from stepwise.config import settings
from stepwise.ingestion import ingest_youtube, ingest_images
from stepwise.alignment import align_segments
from stepwise.structuring import structure_steps, structure_segment
from stepwise.structuring.deduplicator import deduplicate_steps
from stepwise.structuring.consolidator import consolidate_steps
from stepwise.structuring.trivial_filter import filter_trivial_steps
from stepwise.indexing import index_tutorial, get_db_session
from stepwise.indexing.dedup import check_tutorial_overlap
from stepwise.retrieval import query_steps, query_steps_stream

app = FastAPI(title="Stepwise", version="0.1.0")


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Zendesk iframes can come from any subdomain
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _mark_zombie_jobs():
    """Any job still running/pending from a previous process will never finish."""
    with get_db_session() as session:
        session.query(JobDB).filter(
            JobDB.status.in_(["pending", "running"])
        ).update({"status": "error", "error": "Server restarted while job was in progress"})
        session.commit()


class IngestRequest(BaseModel):
    url: str
    title: Optional[str] = None


class DriveIngestRequest(BaseModel):
    source_url: str
    title: str
    video_id: str
    transcript: list[dict]   # [{text, start, duration}]
    frames: list[dict]       # [{path, timestamp}]


class QueryRequest(BaseModel):
    query: str
    tutorial_id: Optional[str] = None
    top_k: int = 5
    history: list[dict] = []  # [{role, text}] — last N exchanges for multi-turn context


class FeedbackRequest(BaseModel):
    query: str
    step_id: str
    helpful: bool


class NotionIngestRequest(BaseModel):
    page_id: str
    notion_token: str
    title: Optional[str] = None


class WatcherCreateRequest(BaseModel):
    source_type: str   # youtube_channel | drive_folder | notion_page | notion_database
    source_id: str
    label: Optional[str] = None
    config: dict = {}  # token_path, notion_token, recursive, etc.


def _set_stage(job_id: str, stage: str) -> None:
    with get_db_session() as session:
        job = session.get(JobDB, job_id)
        job.stage = stage
        session.commit()


def _run_ingestion(job_id: str, url: str, title: Optional[str]) -> None:
    with get_db_session() as session:
        job = session.get(JobDB, job_id)
        job.status = "running"
        job.stage = "downloading"
        session.commit()

    try:
        _set_stage(job_id, "downloading")
        artifacts = ingest_youtube(url)

        _set_stage(job_id, "aligning")
        segments = align_segments(artifacts["transcript"], artifacts["frames"])

        _set_stage(job_id, "structuring")
        tutorial_id = str(uuid.uuid4())

        # Structure segment-by-segment and report progress
        with get_db_session() as session:
            job = session.get(JobDB, job_id)
            job.segments_total = len(segments)
            job.segments_done = 0
            session.commit()

        all_steps = []
        step_number = 1
        for segment in segments:
            seg_steps = structure_segment(tutorial_id, segment, step_number)
            all_steps.extend(seg_steps)
            step_number += len(seg_steps)
            with get_db_session() as session:
                job = session.get(JobDB, job_id)
                job.segments_done = (job.segments_done or 0) + 1
                session.commit()

        steps = deduplicate_steps(all_steps)
        steps = filter_trivial_steps(steps)

        # Consolidate to ~1 step per minute of video
        if steps:
            last_ts = max((s.timestamp_end or 0) for s in steps)
            target = max(10, round(last_ts / 60))
            if len(steps) > target:
                _set_stage(job_id, "consolidating")
                steps = consolidate_steps(steps, target)
                # Re-number after consolidation
                for i, s in enumerate(steps, start=1):
                    s.step_number = i
                # Filter again — consolidation can reintroduce trivial content
                steps = filter_trivial_steps(steps)

        _set_stage(job_id, "indexing")
        tutorial = Tutorial(
            id=tutorial_id,
            source_url=url,
            title=title or artifacts["title"],
            source_type="youtube",
            steps=steps,
            meta={"video_id": artifacts["video_id"]},
        )
        index_tutorial(tutorial)
        check_tutorial_overlap(tutorial_id)

        with get_db_session() as session:
            job = session.get(JobDB, job_id)
            job.status = "done"
            job.stage = None
            job.tutorial_id = tutorial_id
            job.step_count = len(steps)
            session.commit()

    except Exception as e:
        with get_db_session() as session:
            job = session.get(JobDB, job_id)
            job.status = "error"
            job.stage = None
            job.error = str(e)
            session.commit()


@app.post("/ingest", status_code=202)
def ingest(req: IngestRequest, background_tasks: BackgroundTasks) -> dict:
    canonical = _canonical_url(req.url)
    with get_db_session() as session:
        existing = session.query(TutorialDB).filter_by(source_url=canonical).first()
        if existing:
            return {"tutorial_id": existing.id, "step_count": len(existing.steps), "existing": True}
        # Also check against the raw URL in case it was previously stored unnormalised
        existing = session.query(TutorialDB).filter_by(source_url=req.url).first()
        if existing:
            return {"tutorial_id": existing.id, "step_count": len(existing.steps), "existing": True}

    job_id = str(uuid.uuid4())
    with get_db_session() as session:
        session.add(JobDB(id=job_id, status="pending"))
        session.commit()

    background_tasks.add_task(_run_ingestion, job_id, req.url, req.title)
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
def list_tutorials() -> list:
    with get_db_session() as session:
        tutorials = session.query(TutorialDB).order_by(TutorialDB.id).all()
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
    """Remove tutorial + steps from SQLite and vectors from ChromaDB."""
    with get_db_session() as session:
        t = session.get(TutorialDB, tutorial_id)
        if not t:
            return
        step_ids = [s.id for s in t.steps]
        session.delete(t)
        session.commit()

    if step_ids:
        try:
            chroma = chromadb.PersistentClient(path=str(settings.chroma_path))
            collection = chroma.get_or_create_collection("steps")
            collection.delete(ids=step_ids)
        except Exception:
            pass  # ChromaDB delete is best-effort


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

    _delete_tutorial_data(tutorial_id)

    job_id = str(uuid.uuid4())
    with get_db_session() as session:
        session.add(JobDB(id=job_id, status="pending"))
        session.commit()

    background_tasks.add_task(_run_ingestion, job_id, url, title)
    return {"job_id": job_id}


def _run_image_ingestion(job_id: str, files: list[tuple[str, bytes]], title: str) -> None:
    with get_db_session() as session:
        job = session.get(JobDB, job_id)
        job.status = "running"
        job.stage = "processing"
        session.commit()

    try:
        tutorial_id = str(uuid.uuid4())
        output_dir = settings.frames_dir / tutorial_id

        _set_stage(job_id, "aligning")
        artifacts = ingest_images(files, output_dir)
        frames = artifacts["frames"]

        # Each image becomes its own segment
        from stepwise.models import Segment
        segments = [
            Segment(time_start=f["timestamp"], time_end=f["timestamp"] + 10,
                    transcript="", frame_paths=[f["path"]])
            for f in frames
        ]

        _set_stage(job_id, "structuring")
        with get_db_session() as session:
            job = session.get(JobDB, job_id)
            job.segments_total = len(segments)
            job.segments_done = 0
            session.commit()

        all_steps = []
        step_number = 1
        for i, segment in enumerate(segments):
            seg_steps = structure_segment(tutorial_id, segment, step_number,
                                          image_index=i + 1, total_images=len(segments))
            all_steps.extend(seg_steps)
            step_number += len(seg_steps)
            with get_db_session() as session:
                job = session.get(JobDB, job_id)
                job.segments_done = (job.segments_done or 0) + 1
                session.commit()

        steps = deduplicate_steps(all_steps)
        steps = filter_trivial_steps(steps)

        if steps and len(steps) > max(10, len(frames) // 2):
            _set_stage(job_id, "consolidating")
            steps = consolidate_steps(steps, max(10, len(frames)))
            for i, s in enumerate(steps, start=1):
                s.step_number = i
            steps = filter_trivial_steps(steps)

        _set_stage(job_id, "indexing")
        tutorial = Tutorial(
            id=tutorial_id,
            source_url=f"images://{title}",
            title=title,
            source_type="images",
            steps=steps,
            meta={"image_count": len(frames)},
        )
        index_tutorial(tutorial)
        check_tutorial_overlap(tutorial_id)

        with get_db_session() as session:
            job = session.get(JobDB, job_id)
            job.status = "done"
            job.stage = None
            job.tutorial_id = tutorial_id
            job.step_count = len(steps)
            session.commit()

    except Exception as e:
        with get_db_session() as session:
            job = session.get(JobDB, job_id)
            job.status = "error"
            job.stage = None
            job.error = str(e)
            session.commit()


@app.post("/ingest/images", status_code=202)
async def ingest_images_endpoint(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    files: list[UploadFile] = File(...),
) -> dict:
    file_data = [(f.filename or f"file_{i}", await f.read()) for i, f in enumerate(files)]

    job_id = str(uuid.uuid4())
    with get_db_session() as session:
        session.add(JobDB(id=job_id, status="pending"))
        session.commit()

    background_tasks.add_task(_run_image_ingestion, job_id, file_data, title)
    return {"job_id": job_id}


def _run_drive_ingestion(job_id: str, req: dict) -> None:
    """Background task for Drive-sourced ingestion. Artifacts already extracted locally."""
    with get_db_session() as session:
        job = session.get(JobDB, job_id)
        job.status = "running"
        job.stage = "aligning"
        session.commit()

    try:
        _set_stage(job_id, "aligning")
        segments = align_segments(req["transcript"], req["frames"])

        _set_stage(job_id, "structuring")
        tutorial_id = str(uuid.uuid4())

        with get_db_session() as session:
            job = session.get(JobDB, job_id)
            job.segments_total = len(segments)
            job.segments_done = 0
            session.commit()

        all_steps = []
        step_number = 1
        for segment in segments:
            seg_steps = structure_segment(tutorial_id, segment, step_number)
            all_steps.extend(seg_steps)
            step_number += len(seg_steps)
            with get_db_session() as session:
                job = session.get(JobDB, job_id)
                job.segments_done = (job.segments_done or 0) + 1
                session.commit()

        steps = deduplicate_steps(all_steps)
        steps = filter_trivial_steps(steps)

        if steps:
            last_ts = max((s.timestamp_end or 0) for s in steps)
            target = max(10, round(last_ts / 60))
            if len(steps) > target:
                _set_stage(job_id, "consolidating")
                steps = consolidate_steps(steps, target)
                for i, s in enumerate(steps, start=1):
                    s.step_number = i
                steps = filter_trivial_steps(steps)

        _set_stage(job_id, "indexing")
        meta: dict = {"video_id": req["video_id"]}
        if req.get("embedded_video_urls"):
            meta["embedded_video_urls"] = req["embedded_video_urls"]

        tutorial = Tutorial(
            id=tutorial_id,
            source_url=req["source_url"],
            title=req["title"],
            source_type=req.get("source_type", "drive"),
            steps=steps,
            meta=meta,
        )
        index_tutorial(tutorial)
        check_tutorial_overlap(tutorial_id)

        with get_db_session() as session:
            job = session.get(JobDB, job_id)
            job.status = "done"
            job.stage = None
            job.tutorial_id = tutorial_id
            job.step_count = len(steps)
            session.commit()

    except Exception as e:
        with get_db_session() as session:
            job = session.get(JobDB, job_id)
            job.status = "error"
            job.stage = None
            job.error = str(e)
            session.commit()


def _run_notion_ingestion_api(job_id: str, page_id: str, title: Optional[str], notion_token: str) -> None:
    from stepwise.ingestion.notion import ingest_notion_page
    with get_db_session() as session:
        job = session.get(JobDB, job_id)
        job.status = "running"
        job.stage = "fetching"
        session.commit()
    try:
        artifacts = ingest_notion_page(page_id, notion_token)
        _run_drive_ingestion(job_id, {
            "source_url": artifacts["url"],
            "title": title or artifacts["title"],
            "video_id": artifacts["video_id"],
            "transcript": artifacts["transcript"],
            "frames": artifacts["frames"],
            "source_type": "notion",
            "embedded_video_urls": artifacts.get("embedded_video_urls", []),
        })
    except Exception as e:
        with get_db_session() as session:
            job = session.get(JobDB, job_id)
            job.status = "error"
            job.stage = None
            job.error = str(e)
            session.commit()


@app.post("/ingest/notion", status_code=202)
def ingest_notion_endpoint(req: NotionIngestRequest, background_tasks: BackgroundTasks) -> dict:
    # Idempotency: canonical Notion URL
    notion_url = f"https://www.notion.so/{req.page_id.replace('-', '')}"
    with get_db_session() as session:
        existing = session.query(TutorialDB).filter_by(source_url=notion_url).first()
        if existing:
            return {"tutorial_id": existing.id, "step_count": len(existing.steps), "existing": True}

    job_id = str(uuid.uuid4())
    with get_db_session() as session:
        session.add(JobDB(id=job_id, status="pending"))
        session.commit()

    background_tasks.add_task(_run_notion_ingestion_api, job_id, req.page_id, req.title, req.notion_token)
    return {"job_id": job_id}


@app.post("/ingest/drive", status_code=202)
def ingest_drive_endpoint(req: DriveIngestRequest, background_tasks: BackgroundTasks) -> dict:
    # Idempotency check
    with get_db_session() as session:
        existing = session.query(TutorialDB).filter_by(source_url=req.source_url).first()
        if existing:
            return {"tutorial_id": existing.id, "step_count": len(existing.steps), "existing": True}

    job_id = str(uuid.uuid4())
    with get_db_session() as session:
        session.add(JobDB(id=job_id, status="pending"))
        session.commit()

    background_tasks.add_task(_run_drive_ingestion, job_id, req.model_dump())
    return {"job_id": job_id}


@app.get("/jobs")
def list_jobs(status: Optional[str] = None, limit: int = 20) -> list:
    """Return recent jobs, optionally filtered by status (comma-separated)."""
    with get_db_session() as session:
        q = session.query(JobDB).order_by(JobDB.created_at.desc())
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
            }
            for j in jobs
        ]


@app.post("/watchers", status_code=201)
def create_watcher(req: WatcherCreateRequest) -> dict:
    watcher_id = str(uuid.uuid4())
    with get_db_session() as session:
        session.add(WatcherDB(
            id=watcher_id,
            source_type=req.source_type,
            source_id=req.source_id,
            label=req.label or req.source_id,
            config_json=req.config,
        ))
        session.commit()
    return {"watcher_id": watcher_id}


@app.get("/watchers")
def list_watchers() -> list:
    with get_db_session() as session:
        watchers = session.query(WatcherDB).order_by(WatcherDB.created_at.desc()).all()
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


@app.post("/watchers/poll", status_code=202)
def poll_all_watchers(background_tasks: BackgroundTasks) -> dict:
    """Trigger a poll of all active watchers. Safe to call on a cron schedule."""
    from stepwise.ingestion.watcher import poll_watcher
    with get_db_session() as session:
        watchers = session.query(WatcherDB).filter_by(active=True).all()
        total_jobs: list[str] = []
        for watcher in watchers:
            try:
                job_ids = poll_watcher(watcher, session, background_tasks)
                total_jobs.extend(job_ids)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Watcher %s poll failed: %s", watcher.id, e)
        session.commit()
    return {"jobs_queued": len(total_jobs), "job_ids": total_jobs}


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
        query_steps_stream(req.query, tutorial_id=req.tutorial_id, top_k=req.top_k, history=req.history),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/feedback", status_code=201)
def submit_feedback(req: FeedbackRequest) -> dict:
    with get_db_session() as session:
        session.add(FeedbackDB(
            id=str(uuid.uuid4()),
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
    from stepwise.indexing.indexer import _get_chroma, _get_text_model, _get_clip_model, _fuse_embeddings
    from pathlib import Path
    from PIL import Image

    with get_db_session() as session:
        tutorials = session.query(TutorialDB).all()
        tutorial_data = [
            (t.id, t.title, t.source_url, t.source_type, t.meta,
             [(s.id, s.title, s.description, s.visual_reference,
               s.timestamp_start, s.step_number) for s in t.steps])
            for t in tutorials
        ]

    chroma = _get_chroma()
    steps_col = chroma.get_or_create_collection("steps")
    centroids_col = chroma.get_or_create_collection("tutorial_centroids")
    text_model = _get_text_model()
    clip_model = _get_clip_model()

    for tid, title, source_url, source_type, meta, steps in tutorial_data:
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
                {"tutorial_id": tid, "step_number": s[5], "step_id": s[0],
                 "timestamp_start": s[4] or 0, "visual_reference": s[3] or ""}
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
            metadatas=[{"tutorial_id": tid}],
        )

    log.info("Reindex complete — %d tutorials", len(tutorial_data))


@app.get("/admin/query-logs")
def get_query_logs(limit: int = 500, since: Optional[str] = None) -> list:
    from stepwise.models import QueryLogDB
    from datetime import timedelta
    with get_db_session() as session:
        q = session.query(QueryLogDB).order_by(QueryLogDB.created_at.desc())
        if since:
            delta = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}.get(since)
            if delta:
                q = q.filter(QueryLogDB.created_at >= datetime.now(timezone.utc) - delta)
        logs = q.limit(limit).all()

        # Batch-load feedback keyed by query_text
        query_texts = [l.query_text for l in logs]
        fb_rows = session.query(FeedbackDB).filter(FeedbackDB.query.in_(query_texts)).all() if query_texts else []
        fb_by_query: dict[str, list] = {}
        for fb in fb_rows:
            fb_by_query.setdefault(fb.query, []).append({"step_id": fb.step_id, "helpful": fb.helpful > 0})

        return [
            {
                "id": l.id,
                "query_text": l.query_text,
                "hypothetical_text": l.hypothetical_text,
                "tutorial_scoped": l.tutorial_scoped,
                "tutorial_ids_searched": l.tutorial_ids_searched,
                "steps_returned": l.steps_returned,
                "answer_text": l.answer_text,
                "history_length": l.history_length,
                "latency_hyde_ms": l.latency_hyde_ms,
                "latency_retrieval_ms": l.latency_retrieval_ms,
                "latency_synthesis_ms": l.latency_synthesis_ms,
                "total_latency_ms": l.total_latency_ms,
                "created_at": l.created_at.isoformat() if l.created_at else None,
                "feedback": fb_by_query.get(l.query_text, []),
            }
            for l in logs
        ]


@app.get("/admin/stats")
def get_admin_stats() -> dict:
    from stepwise.models import QueryLogDB
    from datetime import timedelta
    with get_db_session() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        queries_24h = session.query(QueryLogDB).filter(QueryLogDB.created_at >= cutoff).count()
        queries_total = session.query(QueryLogDB).count()
        return {"queries_24h": queries_24h, "queries_total": queries_total}


@app.get("/gaps")
def get_gaps(force: bool = False) -> list:
    """
    Analyse recent query logs for topics with poor coverage.

    Results are cached for 1 hour. Pass ?force=true to recompute immediately.
    Returns a list of gap objects sorted by query_count descending.
    """
    from stepwise.analysis.gap_detector import detect_gaps
    return detect_gaps(force=force)


@app.get("/health")
def health():
    return {"status": "ok"}
