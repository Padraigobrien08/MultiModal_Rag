"""Tests for production ops: /ready readiness probe and job timestamps."""

import time
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from stepwise.indexing import get_db_session
from stepwise.ingestion.pipeline import JobTracker
from stepwise.models import JobDB


class TestReadyEndpoint:
    def test_ready_ok(self, app_client):
        resp = app_client.get("/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["checks"]["db"] == "ok"
        assert body["checks"]["chroma"] == "ok"

    def test_ready_reports_db_not_writable(self, app_client):
        # Simulate the DB directory being read-only.
        with patch("stepwise.api.app.os.access", return_value=False):
            resp = app_client.get("/ready")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "not ready"
        assert body["checks"]["db"].startswith("error:")

    def test_ready_reports_chroma_unavailable(self, app_client):
        with patch(
            "stepwise.api.app.chromadb.PersistentClient",
            side_effect=RuntimeError("chroma down"),
        ):
            resp = app_client.get("/ready")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "not ready"
        assert body["checks"]["chroma"].startswith("error:")
        # DB is unaffected, so its check should still pass.
        assert body["checks"]["db"] == "ok"

    def test_ready_does_not_load_ml_models(self, app_client):
        # Readiness must stay cheap: if it tries to load encoders, fail loudly.
        with patch(
            "stepwise.ml.registry.get_text_encoder",
            side_effect=AssertionError("encoder must not load on /ready"),
        ), patch(
            "stepwise.ml.registry.get_clip_encoder",
            side_effect=AssertionError("encoder must not load on /ready"),
        ):
            resp = app_client.get("/ready")
        assert resp.status_code == 200

    def test_ready_public_when_api_key_set(self, app_client):
        with patch("stepwise.config.settings.api_key", "test-secret-key"):
            resp = app_client.get("/ready")
        assert resp.status_code == 200


def _insert_job() -> str:
    job_id = str(uuid.uuid4())
    with get_db_session() as session:
        session.add(JobDB(id=job_id, status="pending"))
        session.commit()
    return job_id


def _get_job(job_id: str) -> SimpleNamespace:
    with get_db_session() as session:
        j = session.get(JobDB, job_id)
        return SimpleNamespace(
            status=j.status,
            error=j.error,
            created_at=j.created_at,
            updated_at=j.updated_at,
            completed_at=j.completed_at,
        )


class TestJobTimestamps:
    def test_created_and_updated_at_set_on_insert(self):
        job = _get_job(_insert_job())
        assert job.created_at is not None
        assert job.updated_at is not None
        assert job.completed_at is None

    def test_updated_at_advances_on_stage_change(self):
        job_id = _insert_job()
        before = _get_job(job_id).updated_at
        time.sleep(0.01)  # ensure a measurable timestamp delta
        JobTracker(job_id).set_stage("structuring")
        after = _get_job(job_id).updated_at
        assert after > before

    def test_complete_sets_completed_at(self):
        job_id = _insert_job()
        JobTracker(job_id).complete("tut-123", 5)
        job = _get_job(job_id)
        assert job.status == "done"
        assert job.completed_at is not None
        assert job.completed_at >= job.created_at

    def test_fail_sets_completed_at(self):
        job_id = _insert_job()
        JobTracker(job_id).fail("boom")
        job = _get_job(job_id)
        assert job.status == "error"
        assert job.error == "boom"
        assert job.completed_at is not None

    def test_job_api_exposes_timestamps(self, app_client):
        job_id = _insert_job()
        JobTracker(job_id).complete("tut-999", 2)
        resp = app_client.get(f"/jobs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["created_at"] is not None
        assert body["updated_at"] is not None
        assert body["completed_at"] is not None
