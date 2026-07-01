"""Contract tests for POST /query (SSE) and POST /query/sync (JSON)."""

import json
from unittest.mock import patch

from stepwise.api.app import app


class TestQuerySync:
    def test_returns_json_with_answer_and_steps(self, app_client, sample_query_response):
        with patch("stepwise.api.app.query_steps", return_value=sample_query_response):
            resp = app_client.post(
                "/query/sync",
                json={"query": "how do I issue a refund?", "top_k": 3},
            )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        data = resp.json()
        assert "answer" in data
        assert "steps" in data
        assert isinstance(data["answer"], str)
        assert isinstance(data["steps"], list)
        assert len(data["steps"]) == 1
        step = data["steps"][0]
        assert step["step_id"] == "step-abc"
        assert step["tutorial_id"] == "tut-xyz"
        assert step["text"]
        assert step["timestamp_start"] == 42.0

    def test_passes_request_params_to_query_steps(self, app_client):
        with patch("stepwise.api.app.query_steps") as mock:
            mock.return_value = {"answer": "No relevant steps found.", "steps": []}
            app_client.post(
                "/query/sync",
                json={
                    "query": "undo that",
                    "tutorial_id": "tut-123",
                    "top_k": 7,
                    "history": [{"role": "user", "text": "how do I invite?"}],
                },
            )

        mock.assert_called_once_with(
            "undo that",
            tutorial_id="tut-123",
            top_k=7,
            history=[{"role": "user", "text": "how do I invite?"}],
        )

    def test_empty_retrieval_shape(self, app_client):
        with patch(
            "stepwise.api.app.query_steps",
            return_value={"answer": "No relevant steps found.", "steps": []},
        ):
            resp = app_client.post("/query/sync", json={"query": "unknown topic"})

        data = resp.json()
        assert data["steps"] == []
        assert data["answer"] == "No relevant steps found."


class TestQuerySSE:
    def _parse_sse_events(self, body: str) -> list[dict]:
        events = []
        for line in body.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        return events

    def test_sse_event_sequence(self, app_client, sample_step_result):
        def fake_stream(*_args, **_kwargs):
            yield f"data: {json.dumps({'type': 'steps', 'steps': [sample_step_result]})}\n\n"
            yield f"data: {json.dumps({'type': 'token', 'text': 'Open '})}\n\n"
            yield f"data: {json.dumps({'type': 'token', 'text': 'Refund.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        with patch("stepwise.api.app.query_steps_stream", side_effect=fake_stream):
            resp = app_client.post("/query", json={"query": "how do I refund?"})

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        events = self._parse_sse_events(resp.text)
        types = [e["type"] for e in events]
        assert types == ["steps", "token", "token", "done"]
        assert events[0]["steps"][0]["step_id"] == "step-abc"
        assert events[1]["text"] == "Open "
        assert events[2]["text"] == "Refund."

    def test_sse_empty_steps_then_done(self, app_client):
        def fake_stream(*_args, **_kwargs):
            yield f"data: {json.dumps({'type': 'steps', 'steps': []})}\n\n"

        with patch("stepwise.api.app.query_steps_stream", side_effect=fake_stream):
            resp = app_client.post("/query", json={"query": "nothing matches"})

        events = self._parse_sse_events(resp.text)
        assert events[0]["type"] == "steps"
        assert events[0]["steps"] == []

    def test_sse_content_type_and_no_cache(self, app_client):
        def fake_stream(*_args, **_kwargs):
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        with patch("stepwise.api.app.query_steps_stream", side_effect=fake_stream):
            resp = app_client.post("/query", json={"query": "test"})

        assert resp.headers.get("cache-control") == "no-cache"
        assert resp.headers.get("x-accel-buffering") == "no"


# Ensure app module is importable after conftest mocks (collection-time sanity check).
assert app.title == "Stepwise"
