"""
Ingest-time duplicate detection.

After a tutorial is indexed, _check_tutorial_overlap() samples its step
embeddings, finds nearest neighbours from other tutorials, and flags the
tutorial in its meta if it substantially overlaps an existing one.

This runs as a background task so it never blocks the ingest response.
"""
import logging
import random

from stepwise.indexing.indexer import _get_chroma, get_db_session
from stepwise.models import TutorialDB

log = logging.getLogger(__name__)

# Step-level distance below which two steps are considered near-duplicates.
# Empirically: identical steps land ~0.0–0.1; paraphrases ~0.2–0.4.
_STEP_DUP_DISTANCE = 0.4

# If this fraction of sampled steps have a near-duplicate in another tutorial,
# flag that tutorial as a potential duplicate.
_OVERLAP_THRESHOLD = 0.5

# Max steps to sample per tutorial (keep the check fast).
_SAMPLE_SIZE = 20


def check_tutorial_overlap(tutorial_id: str, library_id: str) -> None:
    """
    Background task: compare the new tutorial's steps against the existing index
    within the same library. Writes `meta.potential_duplicate_of = <other_tutorial_id>`
    if significant overlap is detected. Safe to call multiple times — idempotent.
    """
    try:
        col = _get_chroma().get_or_create_collection("steps")

        result = col.get(
            where={"tutorial_id": {"$eq": tutorial_id}},
            include=["embeddings"],
        )
        embeddings = result.get("embeddings")
        if not result["ids"] or embeddings is None or len(embeddings) == 0:
            return

        step_ids = result["ids"]

        # Sample for efficiency on large tutorials
        n = min(_SAMPLE_SIZE, len(step_ids))
        indices = random.sample(range(len(step_ids)), n)
        sample_embs = [embeddings[i] for i in indices]
        sample_ids = {step_ids[i] for i in indices}

        overlap: dict[str, int] = {}
        for emb in sample_embs:
            neighbors = col.query(
                query_embeddings=[emb],
                n_results=3,
                where={"library_id": {"$eq": library_id}},
                include=["metadatas", "distances"],
            )
            for meta, dist in zip(
                neighbors["metadatas"][0], neighbors["distances"][0]
            ):
                other_tid = meta.get("tutorial_id")
                other_step_id = meta.get("step_id")
                # Skip self-hits and steps we sampled
                if (
                    not other_tid
                    or other_tid == tutorial_id
                    or other_step_id in sample_ids
                ):
                    continue
                if dist <= _STEP_DUP_DISTANCE:
                    overlap[other_tid] = overlap.get(other_tid, 0) + 1

        flagged = None
        for other_tid, count in overlap.items():
            if count / n >= _OVERLAP_THRESHOLD:
                flagged = other_tid
                break

        with get_db_session() as session:
            t = session.get(TutorialDB, tutorial_id)
            if t:
                m = dict(t.meta or {})
                if flagged:
                    m["potential_duplicate_of"] = flagged
                    log.warning(
                        "Tutorial %s flagged as potential duplicate of %s "
                        "(%.0f%% step overlap)",
                        tutorial_id,
                        flagged,
                        (overlap[flagged] / n) * 100,
                    )
                else:
                    m.pop("potential_duplicate_of", None)
                t.meta = m
                session.commit()

    except Exception:
        log.exception("Overlap check failed for tutorial %s", tutorial_id)
