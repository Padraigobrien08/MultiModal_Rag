import numpy as np
from sentence_transformers import SentenceTransformer

from stepwise.models import Step

SIMILARITY_THRESHOLD = 0.92

_model = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def deduplicate_steps(steps: list[Step]) -> list[Step]:
    """Remove steps whose text is near-identical to an earlier step."""
    if len(steps) < 2:
        return steps

    texts = [f"{s.title}. {s.description}" for s in steps]
    embeddings = _get_model().encode(texts, convert_to_numpy=True, normalize_embeddings=True)

    keep = []
    kept_embeddings = []

    for step, emb in zip(steps, embeddings):
        if kept_embeddings:
            sims = np.dot(kept_embeddings, emb)
            if sims.max() >= SIMILARITY_THRESHOLD:
                continue
        keep.append(step)
        kept_embeddings.append(emb)

    return keep
