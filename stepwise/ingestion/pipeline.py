"""Unified ingestion pipeline — align → structure → finalize → index."""

from __future__ import annotations

import logging
from collections.abc import Callable

from stepwise.alignment import align_segments
from stepwise.indexing import index_tutorial
from stepwise.indexing.dedup import check_tutorial_overlap
from stepwise.indexing.indexer import get_db_session
from stepwise.models import JobDB, Segment, Step, Tutorial
from stepwise.structuring import structure_segment
from stepwise.structuring.consolidator import consolidate_steps
from stepwise.structuring.deduplicator import deduplicate_steps
from stepwise.structuring.trivial_filter import filter_trivial_steps

log = logging.getLogger(__name__)


class JobTracker:
    """Optional progress reporting for background ingestion jobs."""

    def __init__(self, job_id: str | None = None):
        self.job_id = job_id

    def set_stage(self, stage: str) -> None:
        if not self.job_id:
            return
        with get_db_session() as session:
            job = session.get(JobDB, self.job_id)
            if job:
                job.stage = stage
                session.commit()

    def start_running(self, stage: str = "aligning") -> None:
        if not self.job_id:
            return
        with get_db_session() as session:
            job = session.get(JobDB, self.job_id)
            if job:
                job.status = "running"
                job.stage = stage
                session.commit()

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
                session.commit()

    def fail(self, error: str) -> None:
        if not self.job_id:
            return
        with get_db_session() as session:
            job = session.get(JobDB, self.job_id)
            if job:
                job.status = "error"
                job.stage = None
                job.error = error
                session.commit()


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
    check_tutorial_overlap(tutorial.id)


def run_ingestion_pipeline(
    *,
    source_url: str,
    title: str,
    source_type: str,
    meta: dict,
    transcript: list[dict],
    frames: list[dict],
    tutorial_id: str,
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
            source_url=source_url,
            title=title,
            source_type=source_type,
            steps=steps,
            meta=meta,
        )
        index_tutorial_result(tutorial)
        tracker.complete(tutorial.id, len(steps))
        return tutorial
    except Exception as exc:
        tracker.fail(str(exc))
        raise
