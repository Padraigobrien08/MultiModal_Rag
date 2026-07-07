"""Tests for ingestion job observability: events, detail API, retry, cancel."""

import uuid
from unittest.mock import patch

import pytest

from stepwise.indexing import get_db_session
from stepwise.ingestion.errors import humanize_error
from stepwise.ingestion.pipeline import JobCancelled, JobTracker
from stepwise.models import JobDB, JobEventDB


def _insert_job(**kwargs) -> str:
    job_id = str(uuid.uuid4())
    with get_db_session() as session:
        session.add(JobDB(id=job_id, **kwargs))
        session.commit()
    return job_id


def _get_job(job_id: str) -> JobDB:
    with get_db_session() as session:
        job = session.get(JobDB, job_id)
        session.expunge(job)
        return job


def _events(job_id: str) -> list[JobEventDB]:
    with get_db_session() as session:
        return (
            session.query(JobEventDB)
            .filter(JobEventDB.job_id == job_id)
            .order_by(JobEventDB.id.asc())
            .all()
        )


class TestEventLogging:
    def test_log_event_persists(self):
        job_id = _insert_job(status="pending")
        JobTracker(job_id).log_event("hello", level="warning", stage="indexing")
        events = _events(job_id)
        assert len(events) == 1
        assert events[0].message == "hello"
        assert events[0].level == "warning"
        assert events[0].stage == "indexing"

    def test_log_event_noop_without_job(self):
        JobTracker(None).log_event("ignored")  # must not raise

    def test_start_running_sets_started_at_and_logs(self):
        job_id = _insert_job(status="pending")
        JobTracker(job_id).start_running("downloading")
        job = _get_job(job_id)
        assert job.status == "running"
        assert job.started_at is not None
        assert any(e.stage == "downloading" for e in _events(job_id))

    def test_set_stage_logs_event(self):
        job_id = _insert_job(status="running")
        JobTracker(job_id).set_stage("structuring")
        assert any(e.stage == "structuring" for e in _events(job_id))

    def test_complete_and_fail_log_events(self):
        done = _insert_job(status="running")
        JobTracker(done).complete("tut-1", 3)
        assert any("Completed" in e.message for e in _events(done))

        failed = _insert_job(status="running")
        JobTracker(failed).fail("boom")
        fail_events = _events(failed)
        assert any(e.level == "error" and e.message == "boom" for e in fail_events)


class TestStatusTransitions:
    def test_pending_to_running_to_done(self):
        job_id = _insert_job(status="pending")
        tracker = JobTracker(job_id)
        tracker.start_running("aligning")
        assert _get_job(job_id).status == "running"
        tracker.complete("tut-x", 5)
        job = _get_job(job_id)
        assert job.status == "done"
        assert job.completed_at is not None
        assert job.tutorial_id == "tut-x"

    def test_fail_sets_error_and_completed(self):
        job_id = _insert_job(status="running")
        JobTracker(job_id).fail("kaboom")
        job = _get_job(job_id)
        assert job.status == "error"
        assert job.error == "kaboom"
        assert job.completed_at is not None

    def test_mark_cancelled(self):
        job_id = _insert_job(status="running")
        JobTracker(job_id).mark_cancelled()
        job = _get_job(job_id)
        assert job.status == "cancelled"
        assert job.completed_at is not None


class TestCooperativeCancellation:
    def test_raise_if_cancelled_raises(self):
        job_id = _insert_job(status="cancelled")
        with pytest.raises(JobCancelled):
            JobTracker(job_id).raise_if_cancelled()

    def test_set_stage_raises_when_cancelled(self):
        job_id = _insert_job(status="cancelled")
        with pytest.raises(JobCancelled):
            JobTracker(job_id).set_stage("indexing")

    def test_cancelled_pending_job_is_not_processed(self):
        job_id = _insert_job(status="cancelled", source_type="youtube",
                             source_url="https://youtu.be/abc")
        from stepwise.ingestion.tasks import run_youtube_ingestion

        with patch(
            "stepwise.ingestion.tasks.ingest_youtube",
            side_effect=AssertionError("should not run for a cancelled job"),
        ):
            run_youtube_ingestion(job_id, "https://youtu.be/abc", "Title")

        assert _get_job(job_id).status == "cancelled"


class TestJobDetailApi:
    def test_detail_includes_metadata_and_events(self, app_client):
        job_id = _insert_job(status="running", source_type="youtube",
                             source_url="https://youtu.be/xyz", title="Demo")
        JobTracker(job_id).set_stage("structuring")

        resp = app_client.get(f"/jobs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["source_type"] == "youtube"
        assert body["source_url"] == "https://youtu.be/xyz"
        assert body["title"] == "Demo"
        assert body["retryable"] is True
        assert isinstance(body["events"], list)
        assert any(e["stage"] == "structuring" for e in body["events"])

    def test_detail_404(self, app_client):
        resp = app_client.get("/jobs/does-not-exist")
        assert resp.status_code == 404


class TestRetry:
    def test_retry_youtube_failed_job(self, app_client):
        job_id = _insert_job(status="error", error="boom", source_type="youtube",
                             source_url="https://youtu.be/abc", title="T")
        with patch("stepwise.api.app.run_youtube_ingestion") as task:
            resp = app_client.post(f"/jobs/{job_id}/retry")
        assert resp.status_code == 202
        task.assert_called_once()
        job = _get_job(job_id)
        assert job.status == "pending"
        assert job.error is None
        assert job.completed_at is None

    def test_retry_non_retryable_source_rejected(self, app_client):
        job_id = _insert_job(status="error", error="boom", source_type="images",
                             source_url="images://foo", title="foo")
        with patch("stepwise.api.app.run_youtube_ingestion") as task:
            resp = app_client.post(f"/jobs/{job_id}/retry")
        assert resp.status_code == 422
        task.assert_not_called()

    def test_retry_non_failed_job_rejected(self, app_client):
        job_id = _insert_job(status="running", source_type="youtube",
                             source_url="https://youtu.be/abc")
        resp = app_client.post(f"/jobs/{job_id}/retry")
        assert resp.status_code == 409

    def test_retry_missing_job(self, app_client):
        resp = app_client.post("/jobs/nope/retry")
        assert resp.status_code == 404


class TestCancel:
    def test_cancel_pending_job(self, app_client):
        job_id = _insert_job(status="pending", source_type="youtube",
                             source_url="https://youtu.be/abc")
        resp = app_client.post(f"/jobs/{job_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"
        job = _get_job(job_id)
        assert job.status == "cancelled"
        assert job.completed_at is not None

    def test_cancel_running_job_defers_completion(self, app_client):
        job_id = _insert_job(status="running", source_type="youtube",
                             source_url="https://youtu.be/abc")
        resp = app_client.post(f"/jobs/{job_id}/cancel")
        assert resp.status_code == 200
        body = resp.json()
        assert "stage boundary" in body["note"]
        job = _get_job(job_id)
        assert job.status == "cancelled"
        # A running job keeps completed_at unset until the worker unwinds.
        assert job.completed_at is None

    def test_cancel_finished_job_rejected(self, app_client):
        job_id = _insert_job(status="done")
        resp = app_client.post(f"/jobs/{job_id}/cancel")
        assert resp.status_code == 409

    def test_cancel_missing_job(self, app_client):
        resp = app_client.post("/jobs/nope/cancel")
        assert resp.status_code == 404


class TestHumanizeError:
    def test_missing_ffmpeg(self):
        exc = FileNotFoundError(2, "No such file or directory", "ffmpeg")
        assert "ffmpeg" in humanize_error(exc).lower()

    def test_bad_url(self):
        msg = humanize_error(ValueError("Cannot extract video ID from URL: foo"))
        assert "url" in msg.lower()

    def test_rate_limit(self):
        msg = humanize_error(Exception("Error code: 429 rate limit exceeded"))
        assert "rate limit" in msg.lower()

    def test_unknown_falls_back_to_message(self):
        assert humanize_error(ValueError("something odd")) == "something odd"
