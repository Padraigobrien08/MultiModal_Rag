"""Unified ingestion pipeline — align → structure → finalize → index."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from stepwise.alignment import align_segments
from stepwise.indexing import index_tutorial
from stepwise.indexing.dedup import check_tutorial_overlap
from stepwise.indexing.indexer import get_db_session
from stepwise.models import DEFAULT_LIBRARY_ID, JobDB, JobEventDB, Segment, Step, Tutorial
from stepwise.structuring import structure_segment
from stepwise.structuring.consolidator import consolidate_steps
from stepwise.structuring.deduplicator import deduplicate_steps
from stepwise.structuring.trivial_filter import filter_trivial_steps

log = logging.getLogger(__name__)


# Human-readable event message for each stage, used when the caller doesn't
# supply an explicit one.
_STAGE_MESSAGES = {
    "downloading": "Downloading source video",
    "transcribing": "Extracting transcript",
    "extracting_frames": "Extracting frames",
    "aligning": "Aligning transcript with frames",
    "structuring": "Extracting steps",
    "consolidating": "Consolidating steps",
    "indexing": "Indexing into the vector store",
    "fetching": "Fetching source content",
    "processing": "Processing images",
}


class JobCancelled(Exception):
    """Raised inside the pipeline when a job has been cancelled cooperatively."""


class JobTracker:
    """Optional progress reporting for background ingestion jobs."""

    def __init__(self, job_id: str | None = None):
        self.job_id = job_id

    def log_event(self, message: str, *, level: str = "info", stage: str | None = None) -> None:
        """Append a job event. No-op when this tracker isn't bound to a job."""
        if not self.job_id:
            return
        with get_db_session() as session:
            session.add(
                JobEventDB(job_id=self.job_id, stage=stage, level=level, message=message)
            )
            session.commit()

    def raise_if_cancelled(self) -> None:
        """Raise JobCancelled if the job has been marked cancelled out-of-band.

        Called at stage boundaries so a cancel request stops the job at the next
        checkpoint. Running work already in flight isn't forcibly interrupted.
        """
        if not self.job_id:
            return
        with get_db_session() as session:
            job = session.get(JobDB, self.job_id)
            if job and job.status == "cancelled":
                raise JobCancelled()

    def set_stage(self, stage: str, message: str | None = None) -> None:
        self.raise_if_cancelled()
        if not self.job_id:
            return
        with get_db_session() as session:
            job = session.get(JobDB, self.job_id)
            if job:
                job.stage = stage
                session.commit()
        self.log_event(message or _STAGE_MESSAGES.get(stage, f"Stage: {stage}"), stage=stage)

    def start_running(self, stage: str = "aligning") -> None:
        self.raise_if_cancelled()
        if not self.job_id:
            return
        with get_db_session() as session:
            job = session.get(JobDB, self.job_id)
            if job:
                job.status = "running"
                job.stage = stage
                if job.started_at is None:
                    job.started_at = datetime.now(timezone.utc)
                session.commit()
        self.log_event(_STAGE_MESSAGES.get(stage, f"Stage: {stage}"), stage=stage)

    def begin_structuring(self, segments_total: int) -> None:
        if not self.job_id:
            return
        with get_db_session() as session:
            job = session.get(JobDB, self.job_id)
            if job:
                job.segments_total = segments_total
                job.segments_done = 0
                session.commit()

    def segment_done(self) -> None:
        if not self.job_id:
            return
        with get_db_session() as session:
            job = session.get(JobDB, self.job_id)
            if job:
                job.segments_done = (job.segments_done or 0) + 1
                session.commit()

    def complete(self, tutorial_id: str, step_count: int) -> None:
        if not self.job_id:
            return
        with get_db_session() as session:
            job = session.get(JobDB, self.job_id)
            if job:
                job.status = "done"
                job.stage = None
                job.tutorial_id = tutorial_id
                job.step_count = step_count
                job.completed_at = datetime.now(timezone.utc)
                session.commit()
        self.log_event(f"Completed — {step_count} step(s) indexed")

    def fail(self, error: str) -> None:
        if not self.job_id:
            return
        logging.getLogger(__name__).error("Job %s failed: %s", self.job_id, error)
        with get_db_session() as session:
            job = session.get(JobDB, self.job_id)
            if job:
                job.status = "error"
                job.stage = None
                job.error = error
                job.completed_at = datetime.now(timezone.utc)
                session.commit()
        self.log_event(error, level="error")

    def mark_cancelled(self) -> None:
        """Finalise a cancelled job (called once the worker unwinds)."""
        if not self.job_id:
            return
        with get_db_session() as session:
            job = session.get(JobDB, self.job_id)
            if job:
                job.status = "cancelled"
                job.stage = None
                if job.completed_at is None:
                    job.completed_at = datetime.now(timezone.utc)
                session.commit()
        self.log_event("Job cancelled", level="warning")


def structure_segments(
    tutorial_id: str,
    segments: list[Segment],
    tracker: JobTracker,
    *,
    image_mode: bool = False,
) -> list[Step]:
    """Run Claude structuring on each segment, reporting progress when tracked."""
    tracker.set_stage("structuring")
    tracker.begin_structuring(len(segments))

    all_steps: list[Step] = []
    step_number = 1
    for i, segment in enumerate(segments):
        kwargs = {}
        if image_mode:
            kwargs = {"image_index": i + 1, "total_images": len(segments)}
        seg_steps = structure_segment(tutorial_id, segment, step_number, **kwargs)
        all_steps.extend(seg_steps)
        step_number += len(seg_steps)
        tracker.segment_done()

    return all_steps


def finalize_steps(
    steps: list[Step],
    tracker: JobTracker,
    consolidation_target: int | None = None,
) -> list[Step]:
    """Deduplicate, filter trivial content, and optionally consolidate."""
    steps = deduplicate_steps(steps)
    steps = filter_trivial_steps(steps)

    if consolidation_target and len(steps) > consolidation_target:
        tracker.set_stage("consolidating")
        steps = consolidate_steps(steps, consolidation_target)
        for i, step in enumerate(steps, start=1):
            step.step_number = i
        steps = filter_trivial_steps(steps)

    return steps


def video_consolidation_target(steps: list[Step]) -> int | None:
    if not steps:
        return None
    last_ts = max((s.timestamp_end or 0) for s in steps)
    target = max(10, round(last_ts / 60))
    return target if len(steps) > target else None


def image_consolidation_target(steps: list[Step], frame_count: int) -> int | None:
    if not steps:
        return None
    target = max(10, frame_count)
    return target if len(steps) > max(10, frame_count // 2) else None


def index_tutorial_result(tutorial: Tutorial) -> None:
    log.info("Indexing tutorial %s (%d steps)", tutorial.id, len(tutorial.steps))
    index_tutorial(tutorial)
    check_tutorial_overlap(tutorial.id, tutorial.library_id)


def run_ingestion_pipeline(
    *,
    source_url: str,
    title: str,
    source_type: str,
    meta: dict,
    transcript: list[dict],
    frames: list[dict],
    tutorial_id: str,
    library_id: str = DEFAULT_LIBRARY_ID,
    job_id: str | None = None,
    segments: list[Segment] | None = None,
    consolidation_target_fn: Callable[[list[Step]], int | None] | None = None,
    image_mode: bool = False,
) -> Tutorial:
    """Shared path from artifacts (or pre-built segments) through indexing."""
    tracker = JobTracker(job_id)

    try:
        if segments is None:
            tracker.set_stage("aligning")
            segments = align_segments(transcript, frames)

        steps = structure_segments(
            tutorial_id, segments, tracker, image_mode=image_mode
        )
        target = consolidation_target_fn(steps) if consolidation_target_fn else None
        steps = finalize_steps(steps, tracker, target)

        tracker.set_stage("indexing")
        tutorial = Tutorial(
            id=tutorial_id,
            library_id=library_id,
            source_url=source_url,
            title=title,
            source_type=source_type,
            steps=steps,
            meta=meta,
        )
        tracker.raise_if_cancelled()
        index_tutorial_result(tutorial)
        tracker.complete(tutorial.id, len(steps))
        return tutorial
    except JobCancelled:
        # Let the calling task finalise cancellation; don't mark as failed.
        raise
    except Exception as exc:
        from stepwise.ingestion.errors import humanize_error
        tracker.fail(humanize_error(exc))
        raise
