"""Tests for ingest idempotency — no duplicate jobs for existing source URLs."""

from unittest.mock import MagicMock, patch


class _FakeSessionCtx:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *_args):
        return False


def _mock_session_with_existing(existing=None):
    session = MagicMock()
    query = session.query.return_value
    filter_by = query.filter_by.return_value
    filter_by.first.return_value = existing
    return session


class TestIngestIdempotency:
    def test_existing_canonical_url_returns_tutorial_without_job(self, app_client):
        existing = MagicMock()
        existing.id = "tut-existing"
        existing.steps = [1, 2, 3]

        session = _mock_session_with_existing(existing)

        with patch(
            "stepwise.api.app.get_db_session",
            side_effect=lambda: _FakeSessionCtx(session),
        ):
            resp = app_client.post(
                "/ingest",
                json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            )

        assert resp.status_code == 202
        data = resp.json()
        assert data["existing"] is True
        assert data["tutorial_id"] == "tut-existing"
        assert data["step_count"] == 3
        assert "job_id" not in data

    def test_youtu_be_url_normalized_before_lookup(self, app_client):
        existing = MagicMock()
        existing.id = "tut-short"
        existing.steps = []

        session = _mock_session_with_existing(existing)

        with patch(
            "stepwise.api.app.get_db_session",
            side_effect=lambda: _FakeSessionCtx(session),
        ):
            resp = app_client.post(
                "/ingest",
                json={"url": "https://youtu.be/dQw4w9WgXcQ"},
            )

        assert resp.json()["existing"] is True
        session.query.return_value.filter_by.assert_called_with(
            source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            library_id="local",
        )

    def test_new_url_queues_background_job(self, app_client):
        session = MagicMock()
        query = session.query.return_value
        query.filter_by.return_value.first.return_value = None

        with patch(
            "stepwise.api.app.get_db_session",
            side_effect=lambda: _FakeSessionCtx(session),
        ), patch("stepwise.api.app.run_youtube_ingestion"):
            resp = app_client.post(
                "/ingest",
                json={"url": "https://www.youtube.com/watch?v=brand_new_id"},
            )

        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        assert data.get("existing") is not True
        assert session.add.called

    def test_notion_ingest_existing_page_skips_job(self, app_client):
        existing = MagicMock()
        existing.id = "notion-tut"
        existing.steps = [1]

        session = _mock_session_with_existing(existing)

        with patch(
            "stepwise.api.app.get_db_session",
            side_effect=lambda: _FakeSessionCtx(session),
        ):
            resp = app_client.post(
                "/ingest/notion",
                json={
                    "page_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    "notion_token": "secret_test",
                },
            )

        data = resp.json()
        assert data["existing"] is True
        assert data["tutorial_id"] == "notion-tut"
