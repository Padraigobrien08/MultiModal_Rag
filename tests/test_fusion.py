"""Tests for fused text+image embedding construction."""

import numpy as np
import pytest

from stepwise.indexing.indexer import _fuse_embeddings

TEXT_DIM = 384
IMAGE_DIM = 512


def _unit_vector(dim: int, peak_index: int = 0) -> np.ndarray:
    v = np.zeros(dim, dtype=np.float32)
    v[peak_index] = 1.0
    return v


class TestFuseEmbeddings:
    def test_fused_dimension_text_plus_image(self):
        text = _unit_vector(TEXT_DIM, 0)
        image = _unit_vector(IMAGE_DIM, 1)

        fused = _fuse_embeddings(text, image)

        assert fused.shape == (TEXT_DIM + IMAGE_DIM,)
        assert fused.dtype == np.float32

    def test_fused_vector_is_l2_normalized(self):
        text = np.random.default_rng(0).standard_normal(TEXT_DIM).astype(np.float32)
        image = np.random.default_rng(1).standard_normal(IMAGE_DIM).astype(np.float32)

        fused = _fuse_embeddings(text, image)

        assert pytest.approx(np.linalg.norm(fused), rel=1e-5) == 1.0

    def test_missing_image_uses_zero_image_half(self):
        text = _unit_vector(TEXT_DIM, 0)

        fused = _fuse_embeddings(text, None)

        assert fused.shape == (TEXT_DIM + IMAGE_DIM,)
        t_norm = text / np.linalg.norm(text)
        expected = np.concatenate([t_norm, np.zeros(IMAGE_DIM, dtype=np.float32)])
        expected = expected / np.linalg.norm(expected)
        assert np.allclose(fused, expected)

        # Passing a zero vector is not equivalent to None — norm(0) divides by zero.
        with np.errstate(invalid="ignore"):
            fused_zero_arg = _fuse_embeddings(text, np.zeros(IMAGE_DIM, dtype=np.float32))
        assert not np.allclose(fused, fused_zero_arg, equal_nan=True)

    def test_provided_image_changes_fused_vector(self):
        text = _unit_vector(TEXT_DIM, 0)
        image_a = _unit_vector(IMAGE_DIM, 0)
        image_b = _unit_vector(IMAGE_DIM, 1)

        fused_a = _fuse_embeddings(text, image_a)
        fused_b = _fuse_embeddings(text, image_b)

        assert not np.allclose(fused_a, fused_b)

    def test_non_unit_input_vectors_are_normalized(self):
        text = np.ones(TEXT_DIM, dtype=np.float32) * 5.0
        image = np.ones(IMAGE_DIM, dtype=np.float32) * 3.0

        fused = _fuse_embeddings(text, image)

        assert pytest.approx(np.linalg.norm(fused), rel=1e-5) == 1.0

    def test_mismatched_image_dimensions_concatenate_without_error(self):
        # Current behavior: no dimension validation — wrong image size changes output dim.
        # TODO: consider validating image_emb.shape == (512,) at index/query time.
        text = _unit_vector(TEXT_DIM, 0)
        short_image = _unit_vector(128, 0)

        fused = _fuse_embeddings(text, short_image)

        assert fused.shape == (TEXT_DIM + 128,)
