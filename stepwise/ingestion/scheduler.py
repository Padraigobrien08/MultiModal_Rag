"""
Background scheduler for autonomous watcher polling.

APScheduler runs one interval job that polls all active watchers. Each poll
enqueues ingestion work via a thread pool, so a long-running download or
transcription never blocks the next poll tick.

The thread-pool shim mirrors FastAPI's BackgroundTasks.add_task signature, so
poll_watcher() works identically whether it's driven by an HTTP request or by
the scheduler.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

log = logging.getLogger(__name__)

_scheduler = None
_executor: ThreadPoolExecutor | None = None
_interval_minutes: int = 0


class ThreadPoolTasks:
    """Duck-types fastapi.BackgroundTasks — add_task runs on a worker thread."""

    def __init__(self, executor: ThreadPoolExecutor):
        self._executor = executor

    def add_task(self, func: Callable, *args, **kwargs) -> None:
        self._executor.submit(self._run, func, *args, **kwargs)

    @staticmethod
    def _run(func: Callable, *args, **kwargs) -> None:
        try:
            func(*args, **kwargs)
        except Exception:
            log.exception("Scheduled ingestion task failed")


def start(interval_minutes: int, poll_fn: Callable[[ThreadPoolTasks], list]) -> None:
    """
    Start the interval scheduler. poll_fn receives a tasks shim and returns the
    list of job IDs it queued. Idempotent — a second call is a no-op.
    """
    global _scheduler, _executor, _interval_minutes
    if _scheduler is not None:
        return

    from apscheduler.schedulers.background import BackgroundScheduler

    _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="watcher-ingest")
    tasks = ThreadPoolTasks(_executor)
    _interval_minutes = interval_minutes

    def _job() -> None:
        try:
            job_ids = poll_fn(tasks)
            if job_ids:
                log.info("Watcher poll queued %d new ingestion job(s)", len(job_ids))
        except Exception:
            log.exception("Scheduled watcher poll failed")

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        _job, "interval", minutes=interval_minutes,
        id="watcher_poll", max_instances=1, coalesce=True,
    )
    _scheduler.start()
    log.info("Watcher scheduler started — polling every %d min", interval_minutes)


def shutdown() -> None:
    """Stop the scheduler and thread pool. Safe to call when not started."""
    global _scheduler, _executor
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    if _executor is not None:
        _executor.shutdown(wait=False)
        _executor = None


def status() -> dict:
    """Return scheduler state for the API/UI."""
    return {
        "running": _scheduler is not None,
        "interval_minutes": _interval_minutes if _scheduler is not None else None,
    }
