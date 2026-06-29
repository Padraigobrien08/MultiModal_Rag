"""Tests for text-first query embedding construction."""

from unittest.mock import MagicMock, patch

import numpy as np

from stepwise.indexing.indexer import (
    FUSED_EMB_DIM,
    IMAGE_EMB_DIM,
    TEXT_EMB_DIM,
    _fuse_embeddings,
)
from stepwise.retrieval.retriever import _chromadb_lookup, _make_query_embedding


class TestMakeQueryEmbedding:
    def test_fused_dimension_is_896(self):
        text = np.random.default_rng(0).standard_normal(TEXT_EMB_DIM).astype(np.float32)
        fused = _make_query_embedding(text)
        assert fused.shape == (FUSED_EMB_DIM,)
        assert FUSED_EMB_DIM == TEXT_EMB_DIM + IMAGE_EMB_DIM

    def test_vector_is_l2_normalized(self):
        text = np.random.default_rng(1).standard_normal(TEXT_EMB_DIM).astype(np.float32)
        fused = _make_query_embedding(text)
        assert np.isclose(np.linalg.norm(fused), 1.0, rtol=1e-5)

    def test_uses_zero_image_half_before_final_normalize(self):
        text = np.ones(TEXT_EMB_DIM, dtype=np.float32)
        fused = _make_query_embedding(text)

        t_norm = text / np.linalg.norm(text)
        expected = np.concatenate([t_norm, np.zeros(IMAGE_EMB_DIM, dtype=np.float32)])
        expected = expected / np.linalg.norm(expected)
        assert np.allclose(fused, expected)

    def test_equivalent_to_fuse_with_none(self):
        text = np.random.default_rng(2).standard_normal(TEXT_EMB_DIM).astype(np.float32)
        assert np.allclose(_make_query_embedding(text), _fuse_embeddings(text, None))

    def test_does_not_load_clip_model(self):
        with patch("stepwise.indexing.indexer._get_clip_model") as mock_clip:
            text = np.ones(TEXT_EMB_DIM, dtype=np.float32)
            _make_query_embedding(text)
        mock_clip.assert_not_called()


class TestChromadbLookupNoClip:
    def test_lookup_does_not_load_clip_model(self):
        mock_collection = MagicMock()
        mock_collection.count.return_value = 0
        mock_collection.query.return_value = {"ids": [[]], "documents": [[]],
                                               "metadatas": [[]], "distances": [[]]}

        mock_chroma = MagicMock()
        mock_chroma.get_or_create_collection.return_value = mock_collection

        mock_text_model = MagicMock()
        mock_text_model.encode.return_value = np.ones(TEXT_EMB_DIM, dtype=np.float32)

        with (
            patch("stepwise.retrieval.retriever._hypothetical_step", return_value="hypo step."),
            patch("stepwise.retrieval.retriever._get_text_model", return_value=mock_text_model),
            patch("stepwise.retrieval.retriever._get_chroma", return_value=mock_chroma),
            patch("stepwise.indexing.indexer._get_clip_model") as mock_clip,
        ):
            _chromadb_lookup("how do I refund?", None, 5, [])

        mock_clip.assert_not_called()
