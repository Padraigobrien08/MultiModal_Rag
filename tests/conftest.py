"""Shared pytest fixtures — env and heavy deps must be configured before stepwise imports."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# Isolate test data and disable background schedulers before Settings loads.
_test_root = tempfile.mkdtemp(prefix="stepwise_test_")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used-in-unit-tests")
os.environ.setdefault("WATCHER_POLL_ENABLED", "false")
os.environ["DATA_DIR"] = _test_root
os.environ["DB_PATH"] = str(Path(_test_root) / "stepwise.db")
os.environ["CHROMA_PATH"] = str(Path(_test_root) / "chroma")
os.environ["FRAMES_DIR"] = str(Path(_test_root) / "frames")

# Prevent model downloads / heavy ML stacks during API import for contract tests.
for _mod in (
    "sentence_transformers",
    "whisper",
    "openai_whisper",
    "chromadb",
    "cv2",
):
    sys.modules.setdefault(_mod, MagicMock())

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def app_client():
    from stepwise.api.app import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def sample_step_result() -> dict:
    return {
        "step_number": 1,
        "step_id": "step-abc",
        "tutorial_id": "tut-xyz",
        "tutorial_title": "How to refund",
        "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "source_type": "youtube",
        "video_id": "dQw4w9WgXcQ",
        "timestamp_start": 42.0,
        "visual_reference": "/data/frames/tut-xyz/frame_0001.jpg",
        "text": "Issue a refund. Open the order and click Refund.",
    }


@pytest.fixture
def sample_query_response(sample_step_result: dict) -> dict:
    return {
        "answer": "Open the order and click Refund to issue a refund.",
        "steps": [sample_step_result],
    }
