"""Vector lifecycle: deleting/reingesting a tutorial must leave Chroma consistent.

conftest replaces ``chromadb`` with a MagicMock for the fast contract tests. These
tests need the real vector store, so the ``real_chroma`` fixture reimports the
genuine module and points the indexer's cached client at a temp path.
"""

import importlib
import sys
import uuid

import numpy as np
import pytest

from stepwise.indexing.indexer import (
    FUSED_EMB_DIM,
    check_vector_consistency,
    delete_tutorial_vectors,
    get_db_session,
)
from stepwise.models import StepDB, TutorialDB


@pytest.fixture
def real_chroma(tmp_path, monkeypatch):
    """Point indexer/retriever at a real, empty Chroma client on a temp path."""
    saved = sys.modules.get("chromadb")
    sys.modules.pop("chromadb", None)
    real = importlib.import_module("chromadb")

    client = real.PersistentClient(path=str(tmp_path / "chroma"))
    from stepwise.indexing import indexer

    # Both indexer._get_chroma and retriever's imported copy read this global.
    monkeypatch.setattr(indexer, "_chroma_client", client)
    yield client

    if saved is not None:
        sys.modules["chromadb"] = saved


def _unit(vec: np.ndarray) -> list[float]:
    return (vec / np.linalg.norm(vec)).tolist()


def _seed_vectors(
    client, tutorial_id: str, step_ids: list[str], base: np.ndarray,
    library_id: str = "local",
):
    """Write step vectors + a centroid for a tutorial, mirroring index_tutorial."""
    embeddings = []
    rng = np.random.default_rng(abs(hash(tutorial_id)) % (2**32))
    for _ in step_ids:
        embeddings.append(_unit(base + 0.01 * rng.standard_normal(FUSED_EMB_DIM)))

    steps_col = client.get_or_create_collection("steps")
    steps_col.upsert(
        ids=step_ids,
        embeddings=embeddings,
        documents=[f"doc {sid}" for sid in step_ids],
        metadatas=[{"library_id": library_id, "tutorial_id": tutorial_id,
                    "step_id": sid, "step_number": i}
                   for i, sid in enumerate(step_ids)],
    )

    centroid = np.mean(np.array(embeddings), axis=0)
    centroids_col = client.get_or_create_collection("tutorial_centroids")
    centroids_col.upsert(
        ids=[tutorial_id],
        embeddings=[_unit(centroid)],
        documents=["title"],
        metadatas=[{"library_id": library_id, "tutorial_id": tutorial_id}],
    )


@pytest.fixture
def db_cleanup():
    """Track tutorial ids created in a test and remove them (+ steps) afterwards."""
    created: list[str] = []
    yield created
    with get_db_session() as session:
        for tid in created:
            t = session.get(TutorialDB, tid)
            if t:
                session.delete(t)
        session.commit()


def _insert_tutorial(tid: str, step_ids: list[str]):
    with get_db_session() as session:
        session.merge(TutorialDB(id=tid, source_url=f"http://x/{tid}", title="t"))
        for i, sid in enumerate(step_ids):
            session.merge(StepDB(id=sid, tutorial_id=tid, step_number=i,
                                 title="s", description="d"))
        session.commit()


# ── delete ──────────────────────────────────────────────────────────────────

def test_delete_removes_step_vectors_and_centroid(real_chroma):
    tid = f"tut-{uuid.uuid4()}"
    step_ids = [f"step-{uuid.uuid4()}" for _ in range(3)]
    _seed_vectors(real_chroma, tid, step_ids, np.ones(FUSED_EMB_DIM))

    steps_col = real_chroma.get_or_create_collection("steps")
    centroids_col = real_chroma.get_or_create_collection("tutorial_centroids")
    assert steps_col.count() == 3
    assert centroids_col.count() == 1

    delete_tutorial_vectors(tid)

    assert steps_col.get(where={"tutorial_id": tid})["ids"] == []
    assert tid not in centroids_col.get()["ids"]
    assert centroids_col.count() == 0


def test_delete_only_touches_target_tutorial(real_chroma):
    keep_tid = f"keep-{uuid.uuid4()}"
    drop_tid = f"drop-{uuid.uuid4()}"
    keep_steps = [f"k-{uuid.uuid4()}" for _ in range(2)]
    drop_steps = [f"d-{uuid.uuid4()}" for _ in range(2)]
    _seed_vectors(real_chroma, keep_tid, keep_steps, np.ones(FUSED_EMB_DIM))
    _seed_vectors(real_chroma, drop_tid, drop_steps, -np.ones(FUSED_EMB_DIM))

    delete_tutorial_vectors(drop_tid)

    steps_col = real_chroma.get_or_create_collection("steps")
    centroids_col = real_chroma.get_or_create_collection("tutorial_centroids")
    assert set(steps_col.get()["ids"]) == set(keep_steps)
    assert centroids_col.get()["ids"] == [keep_tid]


# ── reingest ────────────────────────────────────────────────────────────────

def test_reingest_leaves_no_stale_step_vectors(real_chroma):
    """Reingest = delete-by-tutorial then re-index; old step ids must not survive
    even when the new run produces entirely different step ids."""
    tid = f"tut-{uuid.uuid4()}"
    old_steps = [f"old-{uuid.uuid4()}" for _ in range(4)]
    _seed_vectors(real_chroma, tid, old_steps, np.ones(FUSED_EMB_DIM))

    # Reingest deletes vectors by tutorial_id before re-indexing.
    delete_tutorial_vectors(tid)
    new_steps = [f"new-{uuid.uuid4()}" for _ in range(2)]
    _seed_vectors(real_chroma, tid, new_steps, np.ones(FUSED_EMB_DIM))

    steps_col = real_chroma.get_or_create_collection("steps")
    ids = set(steps_col.get(where={"tutorial_id": tid})["ids"])
    assert ids == set(new_steps)
    assert not (ids & set(old_steps))
    # Exactly one centroid remains for the tutorial.
    centroids_col = real_chroma.get_or_create_collection("tutorial_centroids")
    assert centroids_col.get()["ids"].count(tid) == 1


# ── prefilter behaviour after deletion ───────────────────────────────────────

def test_prefilter_excludes_deleted_tutorial(real_chroma):
    from stepwise.retrieval.retriever import _relevant_tutorial_ids

    tid = f"tut-{uuid.uuid4()}"
    step_ids = [f"s-{uuid.uuid4()}" for _ in range(3)]
    base = np.ones(FUSED_EMB_DIM)
    _seed_vectors(real_chroma, tid, step_ids, base)

    # A query aligned with the tutorial's centroid selects it pre-deletion.
    query_vec = _unit(base)
    assert _relevant_tutorial_ids(query_vec, "local", exclude_id=None) == [tid]

    delete_tutorial_vectors(tid)

    # Centroid collection is now empty → prefilter falls back to "search all".
    assert _relevant_tutorial_ids(query_vec, "local", exclude_id=None) is None


# ── consistency check ────────────────────────────────────────────────────────

def test_consistency_clean(real_chroma, db_cleanup):
    tid = f"tut-{uuid.uuid4()}"
    step_ids = [f"s-{uuid.uuid4()}" for _ in range(2)]
    db_cleanup.append(tid)
    _insert_tutorial(tid, step_ids)
    _seed_vectors(real_chroma, tid, step_ids, np.ones(FUSED_EMB_DIM))

    report = check_vector_consistency()
    assert not any(t["tutorial_id"] == tid for t in report["tutorials_missing_vectors"])
    assert not (set(step_ids) & set(report["vectors_missing_sqlite"]))
    assert tid not in report["stale_centroids"]


def test_consistency_stale_centroid_after_partial_delete(real_chroma, db_cleanup):
    """A centroid whose tutorial row is gone is reported stale."""
    tid = f"tut-{uuid.uuid4()}"
    step_ids = [f"s-{uuid.uuid4()}" for _ in range(2)]
    _seed_vectors(real_chroma, tid, step_ids, np.ones(FUSED_EMB_DIM))
    # SQLite row never created → centroid + step vectors are orphaned.

    report = check_vector_consistency()
    assert tid in report["stale_centroids"]
    assert set(step_ids) <= set(report["vectors_missing_sqlite"])
    assert report["ok"] is False


def test_consistency_tutorial_missing_vectors(real_chroma, db_cleanup):
    tid = f"tut-{uuid.uuid4()}"
    step_ids = [f"s-{uuid.uuid4()}" for _ in range(3)]
    db_cleanup.append(tid)
    _insert_tutorial(tid, step_ids)
    # No vectors seeded for this tutorial.

    report = check_vector_consistency()
    entry = next(t for t in report["tutorials_missing_vectors"] if t["tutorial_id"] == tid)
    assert set(entry["missing_step_ids"]) == set(step_ids)
