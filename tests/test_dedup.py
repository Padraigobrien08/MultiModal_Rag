"""Tests for retrieval and ingest-time step deduplication."""

from unittest.mock import MagicMock, patch

import numpy as np

from stepwise.models import Step
from stepwise.retrieval.retriever import _dedup_results
from stepwise.structuring.deduplicator import SIMILARITY_THRESHOLD, deduplicate_steps


def _triple(text: str, step_id: str, dist: float = 1.0) -> tuple:
    meta = {"step_id": step_id, "step_number": 1, "tutorial_id": "t1"}
    return (text, meta, dist)


def _step(step_id: str, title: str, description: str) -> Step:
    return Step(
        id=step_id,
        tutorial_id="t1",
        step_number=1,
        title=title,
        description=description,
    )


class TestDedupResults:
    def test_collapses_near_duplicate_texts(self):
        triples = [
            _triple("Issue a refund from the order page.", "a", 0.9),
            _triple("Issue a refund from the order page", "b", 1.0),  # ≥85% similar
            _triple("Configure API keys in settings.", "c", 1.1),
        ]

        result = _dedup_results(triples)

        assert len(result) == 2
        assert result[0][1]["step_id"] == "a"  # best-ranked copy kept
        assert result[1][1]["step_id"] == "c"

    def test_preserves_distinct_texts(self):
        triples = [
            _triple("Invite a team member.", "a", 0.8),
            _triple("Rotate API credentials.", "b", 0.9),
            _triple("Export billing history.", "c", 1.0),
        ]

        result = _dedup_results(triples)

        assert [t[1]["step_id"] for t in result] == ["a", "b", "c"]

    def test_ordering_is_stable_for_kept_items(self):
        triples = [
            _triple("Alpha step text.", "first", 0.5),
            _triple("Beta step text.", "second", 0.6),
            _triple("Gamma step text.", "third", 0.7),
        ]

        result = _dedup_results(triples)

        assert [t[1]["step_id"] for t in result] == ["first", "second", "third"]

    def test_threshold_at_85_percent(self):
        base = "Navigate to billing settings and update payment method."
        near_dup = base[:-1]  # tiny edit, still very similar
        distinct = "Completely unrelated topic about webhooks."

        triples = [
            _triple(base, "keep", 0.5),
            _triple(near_dup, "drop", 0.6),
            _triple(distinct, "also_keep", 0.7),
        ]

        result = _dedup_results(triples)
        kept_ids = {t[1]["step_id"] for t in result}

        assert "keep" in kept_ids
        assert "also_keep" in kept_ids
        assert "drop" not in kept_ids


class TestDeduplicateSteps:
    def test_collapses_embedding_similar_steps(self):
        steps = [
            _step("s1", "Invite user", "Go to team settings and invite."),
            _step("s2", "Invite teammate", "Open team settings and invite them."),
            _step("s3", "Export data", "Download CSV from reports."),
        ]
        emb_similar_a = np.array([1.0, 0.0], dtype=np.float32)
        emb_similar_b = np.array([0.99, 0.14], dtype=np.float32)  # cos sim > 0.92
        emb_distinct = np.array([0.0, 1.0], dtype=np.float32)

        mock_model = MagicMock()
        mock_model.encode.return_value = np.stack([emb_similar_a, emb_similar_b, emb_distinct])

        with patch("stepwise.structuring.deduplicator.get_text_encoder", return_value=mock_model):
            result = deduplicate_steps(steps)

        assert len(result) == 2
        assert result[0].id == "s1"
        assert result[1].id == "s3"

    def test_preserves_order_of_kept_steps(self):
        steps = [
            _step("s1", "A", "First."),
            _step("s2", "B", "Second."),
        ]
        mock_model = MagicMock()
        mock_model.encode.return_value = np.stack(
            [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
        )

        with patch("stepwise.structuring.deduplicator.get_text_encoder", return_value=mock_model):
            result = deduplicate_steps(steps)

        assert [s.id for s in result] == ["s1", "s2"]

    def test_short_list_unchanged(self):
        steps = [_step("s1", "Only", "One step.")]
        assert deduplicate_steps(steps) == steps

    def test_similarity_threshold_constant(self):
        assert SIMILARITY_THRESHOLD == 0.92
