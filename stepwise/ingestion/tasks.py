"""Background ingestion tasks shared by API, CLI, and watcher."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

from stepwise.config import settings
from stepwise.ingestion import ingest_images, ingest_youtube
from stepwise.ingestion.pipeline import (
    JobTracker,
    image_consolidation_target,
    run_ingestion_pipeline,
    video_consolidation_target,
)
from stepwise.models import DEFAULT_LIBRARY_ID, Segment

log = logging.getLogger(__name__)


def run_youtube_ingestion(
    job_id: str, url: str, title: Optional[str] = None,
    library_id: str = DEFAULT_LIBRARY_ID,
) -> None:
    tracker = JobTracker(job_id)
    try:
        tracker.start_running("downloading")
        artifacts = ingest_youtube(url)
        tutorial_id = str(uuid.uuid4())
        run_ingestion_pipeline(
            source_url=url,
            title=title or artifacts["title"],
            source_type="youtube",
            meta={"video_id": artifacts["video_id"]},
            transcript=artifacts["transcript"],
            frames=artifacts["frames"],
            tutorial_id=tutorial_id,
            library_id=library_id,
            job_id=job_id,
            consolidation_target_fn=video_consolidation_target,
        )
    except Exception as exc:
        tracker.fail(str(exc))
        raise


def run_drive_ingestion(
    job_id: str, req: dict, library_id: str = DEFAULT_LIBRARY_ID
) -> None:
    tracker = JobTracker(job_id)
    try:
        tracker.start_running("aligning")
        tutorial_id = str(uuid.uuid4())
        meta: dict = {"video_id": req["video_id"]}
        if req.get("embedded_video_urls"):
            meta["embedded_video_urls"] = req["embedded_video_urls"]
        run_ingestion_pipeline(
            source_url=req["source_url"],
            title=req["title"],
            source_type=req.get("source_type", "drive"),
            meta=meta,
            transcript=req["transcript"],
            frames=req["frames"],
            tutorial_id=tutorial_id,
            library_id=req.get("library_id", library_id),
            job_id=job_id,
            consolidation_target_fn=video_consolidation_target,
        )
    except Exception as exc:
        tracker.fail(str(exc))
        raise


def run_image_ingestion(
    job_id: str, files: list[tuple[str, bytes]], title: str,
    library_id: str = DEFAULT_LIBRARY_ID,
) -> None:
    tracker = JobTracker(job_id)
    try:
        tracker.start_running("processing")
        tutorial_id = str(uuid.uuid4())
        output_dir = settings.frames_dir / tutorial_id
        artifacts = ingest_images(files, output_dir)
        frames = artifacts["frames"]
        segments = [
            Segment(
                time_start=f["timestamp"],
                time_end=f["timestamp"] + 10,
                transcript="",
                frame_paths=[f["path"]],
            )
            for f in frames
        ]
        frame_count = len(frames)

        def consolidation_fn(steps):
            return image_consolidation_target(steps, frame_count)

        run_ingestion_pipeline(
            source_url=f"images://{title}",
            title=title,
            source_type="images",
            meta={"image_count": frame_count},
            transcript=[],
            frames=[],
            tutorial_id=tutorial_id,
            library_id=library_id,
            job_id=job_id,
            segments=segments,
            consolidation_target_fn=consolidation_fn,
            image_mode=True,
        )
    except Exception as exc:
        tracker.fail(str(exc))
        raise


def run_notion_ingestion_api(
    job_id: str, page_id: str, title: Optional[str], notion_token: str,
    library_id: str = DEFAULT_LIBRARY_ID,
) -> None:
    from stepwise.ingestion.notion import ingest_notion_page

    tracker = JobTracker(job_id)
    try:
        tracker.start_running("fetching")
        artifacts = ingest_notion_page(page_id, notion_token)
        run_drive_ingestion(job_id, {
            "source_url": artifacts["url"],
            "title": title or artifacts["title"],
            "video_id": artifacts["video_id"],
            "transcript": artifacts["transcript"],
            "frames": artifacts["frames"],
            "source_type": "notion",
            "embedded_video_urls": artifacts.get("embedded_video_urls", []),
        }, library_id=library_id)
    except Exception as exc:
        tracker.fail(str(exc))
        raise


def run_drive_ingestion_from_meta(
    job_id: str, file_meta: dict, token_path_str: str | None = None,
    library_id: str = DEFAULT_LIBRARY_ID,
) -> None:
    from stepwise.ingestion.drive import ingest_drive_file

    token_path = Path(token_path_str) if token_path_str else settings.drive_token_path
    artifacts = ingest_drive_file(file_meta, token_path)
    run_drive_ingestion(job_id, {
        "source_url": artifacts["url"],
        "title": artifacts["title"],
        "video_id": artifacts["video_id"],
        "transcript": artifacts["transcript"],
        "frames": artifacts["frames"],
    }, library_id=library_id)


def run_notion_ingestion(
    job_id: str, page_id: str, title: str, notion_token: str,
    library_id: str = DEFAULT_LIBRARY_ID,
) -> None:
    from stepwise.ingestion.notion import ingest_notion_page

    artifacts = ingest_notion_page(page_id, notion_token)
    run_drive_ingestion(job_id, {
        "source_url": artifacts["url"],
        "title": title or artifacts["title"],
        "video_id": artifacts["video_id"],
        "transcript": artifacts["transcript"],
        "frames": artifacts["frames"],
        "source_type": "notion",
        "embedded_video_urls": artifacts.get("embedded_video_urls", []),
    }, library_id=library_id)
