import numpy as np

from stepwise.ml.registry import get_text_encoder
from stepwise.models import Step

SIMILARITY_THRESHOLD = 0.92


def deduplicate_steps(steps: list[Step]) -> list[Step]:
    """Remove steps whose text is near-identical to an earlier step."""
    if len(steps) < 2:
        return steps

    texts = [f"{s.title}. {s.description}" for s in steps]
    embeddings = get_text_encoder().encode(texts, convert_to_numpy=True, normalize_embeddings=True)

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
