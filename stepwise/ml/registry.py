"""Centralized lazy loading for ML models used across Stepwise."""

from __future__ import annotations

import logging

from stepwise.config import settings

log = logging.getLogger(__name__)

_whisper_model = None
_text_encoder = None
_clip_encoder = None
_cross_encoder = None


def get_whisper_model():
    """Shared Whisper model for YouTube and Drive transcription."""
    global _whisper_model
    if _whisper_model is None:
        import whisper

        log.info("Loading Whisper model (base)…")
        _whisper_model = whisper.load_model("base")
        log.info("Whisper model ready")
    return _whisper_model


def get_text_encoder():
    """Sentence-transformer for step text embeddings and ingest-time dedup."""
    global _text_encoder
    if _text_encoder is None:
        from sentence_transformers import SentenceTransformer

        log.info("Loading text encoder %s…", settings.embedding_model)
        _text_encoder = SentenceTransformer(settings.embedding_model)
        log.info("Text encoder ready")
    return _text_encoder


def get_clip_encoder():
    """CLIP encoder for screenshot embeddings at index time."""
    global _clip_encoder
    if _clip_encoder is None:
        from sentence_transformers import SentenceTransformer

        log.info("Loading CLIP encoder (clip-ViT-B-32)…")
        _clip_encoder = SentenceTransformer("clip-ViT-B-32")
        log.info("CLIP encoder ready")
    return _clip_encoder


def get_cross_encoder():
    """Cross-encoder for query-time re-ranking."""
    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder

        log.info("Loading cross-encoder…")
        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        log.info("Cross-encoder ready")
    return _cross_encoder
