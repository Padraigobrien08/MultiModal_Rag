"""Tests for application settings loading."""

import importlib
from pathlib import Path

import pytest

from stepwise.config import Settings


class TestSettings:
    def test_defaults_with_required_api_key(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("WATCHER_POLL_ENABLED", "true")
        monkeypatch.delenv("DATA_DIR", raising=False)

        s = Settings()

        assert s.anthropic_api_key == "test-key"
        # Per-stage Claude model defaults (see README "Choosing Claude models").
        assert s.structuring_model == "claude-haiku-4-5-20251001"
        assert s.hyde_model == "claude-haiku-4-5"
        assert s.synthesis_model == "claude-haiku-4-5"
        assert s.consolidation_model == "claude-sonnet-4-6"
        assert s.frame_interval_seconds == 5
        assert s.embedding_model == "all-MiniLM-L6-v2"
        assert s.watcher_poll_enabled is True
        assert s.watcher_poll_interval_minutes == 30
        assert s.api_key is None
        assert s.cors_origins == "*"
        assert s.cors_origin_list() == ["*"]

    def test_env_vars_override_paths(self, monkeypatch, tmp_path):
        data = tmp_path / "custom_data"
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("DATA_DIR", str(data))
        monkeypatch.setenv("DB_PATH", str(data / "custom.db"))
        monkeypatch.setenv("CHROMA_PATH", str(data / "custom_chroma"))
        monkeypatch.setenv("FRAMES_DIR", str(data / "custom_frames"))
        monkeypatch.setenv("FRAME_INTERVAL_SECONDS", "12")
        monkeypatch.setenv("WATCHER_POLL_ENABLED", "false")

        s = Settings()

        assert s.data_dir == data
        assert s.db_path == data / "custom.db"
        assert s.chroma_path == data / "custom_chroma"
        assert s.frames_dir == data / "custom_frames"
        assert s.frame_interval_seconds == 12
        assert s.watcher_poll_enabled is False

    def test_module_creates_data_directories(self, monkeypatch, tmp_path):
        data = tmp_path / "module_data"
        frames = data / "frames"
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("DATA_DIR", str(data))
        monkeypatch.setenv("FRAMES_DIR", str(frames))

        import stepwise.config as config_module

        importlib.reload(config_module)

        assert data.is_dir()
        assert frames.is_dir()

    def test_missing_optional_env_uses_defaults(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "only-required-key")
        for key in (
            "STRUCTURING_MODEL",
            "HYDE_MODEL",
            "SYNTHESIS_MODEL",
            "CONSOLIDATION_MODEL",
            "EMBEDDING_MODEL",
            "WATCHER_POLL_INTERVAL_MINUTES",
        ):
            monkeypatch.delenv(key, raising=False)

        s = Settings()

        assert s.structuring_model == "claude-haiku-4-5-20251001"
        assert s.drive_token_path == Path("./data/drive_token.json")

    def test_model_ids_overridable_via_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("STRUCTURING_MODEL", "claude-haiku-4-5")
        monkeypatch.setenv("HYDE_MODEL", "claude-sonnet-5")
        monkeypatch.setenv("SYNTHESIS_MODEL", "claude-opus-4-8")
        monkeypatch.setenv("CONSOLIDATION_MODEL", "claude-opus-4-8")

        s = Settings()

        assert s.structuring_model == "claude-haiku-4-5"
        assert s.hyde_model == "claude-sonnet-5"
        assert s.synthesis_model == "claude-opus-4-8"
        assert s.consolidation_model == "claude-opus-4-8"

    def test_api_key_and_cors_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("API_KEY", "stepwise-secret")
        monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, https://app.example.com")

        s = Settings()

        assert s.api_key == "stepwise-secret"
        assert s.cors_origin_list() == ["http://localhost:3000", "https://app.example.com"]

    def test_missing_required_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(Exception):
            Settings(_env_file=None)
