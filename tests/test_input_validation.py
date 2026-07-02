"""Tests for public-API input validation bounds and enums."""

from unittest.mock import patch


class TestQueryValidation:
    def test_empty_query_rejected(self, app_client):
        resp = app_client.post("/query/sync", json={"query": ""})
        assert resp.status_code == 422

    def test_overlong_query_rejected(self, app_client):
        resp = app_client.post("/query/sync", json={"query": "x" * 2001})
        assert resp.status_code == 422

    def test_top_k_out_of_range_rejected(self, app_client):
        assert app_client.post("/query/sync", json={"query": "hi", "top_k": 0}).status_code == 422
        assert app_client.post("/query/sync", json={"query": "hi", "top_k": 51}).status_code == 422

    def test_too_many_history_turns_rejected(self, app_client):
        resp = app_client.post(
            "/query/sync",
            json={"query": "hi", "history": [{"role": "user", "text": "x"}] * 51},
        )
        assert resp.status_code == 422

    def test_valid_query_within_bounds_accepted(self, app_client):
        with patch("stepwise.api.app.query_steps", return_value={"answer": "ok", "steps": []}):
            resp = app_client.post("/query/sync", json={"query": "hi", "top_k": 10})
        assert resp.status_code == 200


class TestWatcherValidation:
    def test_invalid_source_type_rejected(self, app_client):
        resp = app_client.post(
            "/watchers",
            json={"source_type": "not_a_real_source", "source_id": "abc"},
        )
        assert resp.status_code == 422

    def test_valid_source_type_accepted(self, app_client):
        resp = app_client.post(
            "/watchers",
            json={"source_type": "youtube_channel", "source_id": "UC123"},
        )
        assert resp.status_code == 201


class TestListBounds:
    def test_jobs_limit_upper_bound_enforced(self, app_client):
        assert app_client.get("/jobs?limit=201").status_code == 422
        assert app_client.get("/jobs?limit=0").status_code == 422

    def test_query_logs_limit_upper_bound_enforced(self, app_client):
        assert app_client.get("/admin/query-logs?limit=2001").status_code == 422


class TestImageUploadBounds:
    def test_too_many_files_rejected(self, app_client):
        files = [("files", (f"f{i}.png", b"x", "image/png")) for i in range(101)]
        resp = app_client.post("/ingest/images", data={"title": "t"}, files=files)
        assert resp.status_code == 400
