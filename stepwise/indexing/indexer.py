from pathlib import Path

import chromadb
import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from stepwise.config import settings
from stepwise.ml.registry import get_clip_encoder, get_text_encoder
from stepwise.models import StepDB, Tutorial, TutorialDB, get_engine

# Embedding dimensions — must stay in sync with the models below.
TEXT_EMB_DIM = 384   # all-MiniLM-L6-v2
IMAGE_EMB_DIM = 512  # clip-ViT-B-32 (index-time screenshot encoding only)
FUSED_EMB_DIM = TEXT_EMB_DIM + IMAGE_EMB_DIM

_engine = None
_chroma_client = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = get_engine(settings.db_path)
    return _engine


def get_db_session() -> Session:
    return Session(_get_engine())


def _get_chroma():
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=str(settings.chroma_path))
    return _chroma_client


def _get_text_model():
    return get_text_encoder()


def _get_clip_model():
    return get_clip_encoder()


def _fuse_embeddings(text_emb: np.ndarray, image_emb: np.ndarray | None) -> np.ndarray:
    """Concatenate normalised text + image embeddings, then normalise the result.

    Index time: steps with screenshots pass a CLIP image embedding; steps without
    use a zero image half. Query time: always pass image_emb=None (see
    retriever._make_query_embedding) for text-first retrieval.

    Final normalisation ensures consistent unit-norm vectors across the whole
    collection regardless of whether a step has an image. This makes L2 distance
    equivalent to cosine distance and the MAX_DISTANCE threshold reliable.
    """
    t = text_emb / np.linalg.norm(text_emb)
    i = (
        np.zeros(IMAGE_EMB_DIM, dtype=np.float32)
        if image_emb is None
        else image_emb / np.linalg.norm(image_emb)
    )
    fused = np.concatenate([t, i])
    return fused / np.linalg.norm(fused)


def migrate_chroma_default_library() -> None:
    """Tag pre-existing Chroma vectors (indexed before library scoping) into the
    default library. Metadata-only update — no re-embedding. Idempotent and
    best-effort: safe to call on every startup and a no-op once everything is
    tagged (or when Chroma is empty / mocked in tests).
    """
    import logging
    log = logging.getLogger(__name__)
    default_id = settings.default_library_id
    try:
        chroma = _get_chroma()
        for name in ("steps", "tutorial_centroids"):
            col = chroma.get_or_create_collection(name)
            result = col.get(include=["metadatas"])
            ids = result.get("ids") or []
            metas = result.get("metadatas") or []
            fix_ids, fix_metas = [], []
            for cid, meta in zip(ids, metas):
                meta = meta or {}
                if not meta.get("library_id"):
                    fix_ids.append(cid)
                    fix_metas.append({**meta, "library_id": default_id})
            if fix_ids:
                col.update(ids=fix_ids, metadatas=fix_metas)
                log.info("Tagged %d %s vectors into library '%s'",
                         len(fix_ids), name, default_id)
    except Exception:
        log.warning("Chroma library backfill skipped", exc_info=True)


def index_tutorial(tutorial: Tutorial) -> None:
    """Persist tutorial + steps to SQLite and embed steps into ChromaDB."""
    _index_relational(tutorial)
    _index_vectors(tutorial)


def _index_relational(tutorial: Tutorial) -> None:
    with get_db_session() as session:
        session.merge(TutorialDB(
            id=tutorial.id,
            library_id=tutorial.library_id,
            source_url=tutorial.source_url,
            title=tutorial.title,
            source_type=tutorial.source_type,
            meta=tutorial.meta,
        ))

        for step in tutorial.steps:
            session.merge(StepDB(
                id=step.id,
                library_id=tutorial.library_id,
                tutorial_id=step.tutorial_id,
                step_number=step.step_number,
                title=step.title,
                description=step.description,
                action_type=step.action_type,
                visual_reference=step.visual_reference,
                timestamp_start=step.timestamp_start,
                timestamp_end=step.timestamp_end,
                transcript_source=step.transcript_source,
                confidence_score=step.confidence_score,
            ))

        session.commit()


def _index_vectors(tutorial: Tutorial) -> None:
    if not tutorial.steps:
        return

    text_model = _get_text_model()
    clip_model = _get_clip_model()
    collection = _get_chroma().get_or_create_collection("steps")

    texts = [f"{s.title}. {s.description}" for s in tutorial.steps]
    text_embeddings = text_model.encode(texts, convert_to_numpy=True)

    fused_embeddings = []
    for step, text_emb in zip(tutorial.steps, text_embeddings):
        image_emb = None
        if step.visual_reference and Path(step.visual_reference).exists():
            img = Image.open(step.visual_reference).convert("RGB")
            image_emb = clip_model.encode(img, convert_to_numpy=True)
        fused_embeddings.append(_fuse_embeddings(text_emb, image_emb).tolist())

    collection.upsert(
        ids=[s.id for s in tutorial.steps],
        embeddings=fused_embeddings,
        documents=texts,
        metadatas=[
            {
                "library_id": tutorial.library_id,
                "tutorial_id": s.tutorial_id,
                "step_number": s.step_number,
                "step_id": s.id,
                "timestamp_start": s.timestamp_start or 0,
                "visual_reference": s.visual_reference or "",
            }
            for s in tutorial.steps
        ],
    )

    # Store a tutorial-level centroid for the pre-filter stage at query time.
    # Centroid = mean of all step embeddings, re-normalised to unit length.
    centroid = np.mean(fused_embeddings, axis=0)
    centroid = centroid / np.linalg.norm(centroid)
    centroids_col = _get_chroma().get_or_create_collection("tutorial_centroids")
    centroids_col.upsert(
        ids=[tutorial.id],
        embeddings=[centroid.tolist()],
        documents=[tutorial.title or ""],
        metadatas=[{"library_id": tutorial.library_id, "tutorial_id": tutorial.id}],
    )


def delete_tutorial_vectors(tutorial_id: str) -> None:
    """Remove every vector a tutorial owns from Chroma: step vectors and centroid.

    Step vectors are deleted by ``tutorial_id`` metadata (not by a caller-supplied
    step-id list) so a reingest cannot leave orphaned step vectors behind even if
    the step ids changed. The centroid is keyed by tutorial id.
    """
    chroma = _get_chroma()
    steps_col = chroma.get_or_create_collection("steps")
    steps_col.delete(where={"tutorial_id": tutorial_id})
    centroids_col = chroma.get_or_create_collection("tutorial_centroids")
    centroids_col.delete(ids=[tutorial_id])


def check_vector_consistency() -> dict:
    """Cross-check SQLite rows against Chroma vectors and report drift.

    Buckets:
      - ``tutorials_missing_vectors``: tutorials with steps in SQLite whose step
        vectors are absent from Chroma.
      - ``vectors_missing_sqlite``: step-vector ids in Chroma with no SQLite row.
      - ``stale_centroids``: centroids whose tutorial no longer exists in SQLite
        or that have no backing step vectors.
    """
    chroma = _get_chroma()
    steps_col = chroma.get_or_create_collection("steps")
    centroids_col = chroma.get_or_create_collection("tutorial_centroids")

    steps_data = steps_col.get(include=["metadatas"])
    vector_step_ids = set(steps_data["ids"])
    vector_tutorial_ids = {
        m["tutorial_id"]
        for m in steps_data["metadatas"]
        if m and m.get("tutorial_id")
    }
    centroid_ids = set(centroids_col.get()["ids"])

    with get_db_session() as session:
        tutorials = session.query(TutorialDB).all()
        sqlite_tutorial_ids = set()
        sqlite_step_ids: set[str] = set()
        tutorial_step_ids: dict[str, list[str]] = {}
        for t in tutorials:
            sqlite_tutorial_ids.add(t.id)
            step_ids = [s.id for s in t.steps]
            tutorial_step_ids[t.id] = step_ids
            sqlite_step_ids.update(step_ids)

    tutorials_missing_vectors = []
    for tid, step_ids in tutorial_step_ids.items():
        if not step_ids:
            continue  # no steps → nothing to embed
        missing = [sid for sid in step_ids if sid not in vector_step_ids]
        if missing:
            tutorials_missing_vectors.append(
                {"tutorial_id": tid, "missing_step_ids": missing}
            )

    vectors_missing_sqlite = sorted(vector_step_ids - sqlite_step_ids)
    stale_centroids = sorted(
        cid
        for cid in centroid_ids
        if cid not in sqlite_tutorial_ids or cid not in vector_tutorial_ids
    )

    return {
        "ok": not (
            tutorials_missing_vectors or vectors_missing_sqlite or stale_centroids
        ),
        "tutorials_missing_vectors": tutorials_missing_vectors,
        "vectors_missing_sqlite": vectors_missing_sqlite,
        "stale_centroids": stale_centroids,
    }
