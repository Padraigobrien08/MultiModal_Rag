import difflib
import json
import logging
import time
import uuid
from collections.abc import Generator

import anthropic
import numpy as np

from stepwise.config import settings
from stepwise.indexing.indexer import _fuse_embeddings, _get_chroma, _get_text_model, get_db_session
from stepwise.ml.registry import get_cross_encoder
from stepwise.models import QueryLogDB, TutorialDB

log = logging.getLogger(__name__)

_client = None

TOP_K = 5
FETCH_K = 15        # candidates fetched before cross-encoder re-ranking
FAST_MODEL = "claude-haiku-4-5"

# After embedding normalisation, unit-norm vectors give L2 distance in [0, 2].
# Empirical calibration: relevant ~0.84–1.00, borderline ~1.17–1.35, irrelevant ~1.42+.
MAX_DISTANCE = 1.4

# Tutorial pre-filter: only restrict to top tutorials if the best centroid is
# within this distance. If all tutorials are far, search across all.
CENTROID_THRESHOLD = 1.1
TOP_TUTORIALS = 3


# ── Lazy-loaded models ────────────────────────────────────────────────────────

def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def _get_cross_encoder():
    return get_cross_encoder()


# ── HyDE ─────────────────────────────────────────────────────────────────────

def _hypothetical_step(query: str, history: list[dict]) -> str:
    """Generate a fake step that would answer the query (HyDE).

    Uses conversation history so follow-up queries like 'how do I undo that?'
    generate contextually correct hypotheticals.
    """
    messages = [
        {"role": m["role"], "content": m["text"]}
        for m in history[-3:]
        if m.get("text")
    ]
    messages.append({"role": "user", "content": query})

    response = _get_client().messages.create(
        model=FAST_MODEL,
        max_tokens=120,
        system=(
            "Write a single software tutorial step that directly answers the question. "
            "Format: 'Action title. Detailed description of the action.' "
            "Be specific and imperative. Output only the step text, nothing else."
        ),
        messages=messages,
    )
    return response.content[0].text.strip()


# ── Tutorial pre-filter ───────────────────────────────────────────────────────

def _relevant_tutorial_ids(query_embedding: list[float], exclude_id: str | None) -> list[str] | None:
    """Return tutorial IDs to restrict search to, or None (search all).

    Queries the tutorial_centroids collection. If no centroid is close enough,
    returns None so the full step collection is searched.
    """
    centroids_col = _get_chroma().get_or_create_collection("tutorial_centroids")
    if centroids_col.count() == 0:
        return None

    n = min(TOP_TUTORIALS, centroids_col.count())
    results = centroids_col.query(
        query_embeddings=[query_embedding],
        n_results=n,
        include=["metadatas", "distances"],
    )
    if not results["ids"][0]:
        return None

    best_dist = results["distances"][0][0]
    if best_dist > CENTROID_THRESHOLD:
        return None  # nothing is close — don't restrict

    return [m["tutorial_id"] for m in results["metadatas"][0]]


def _make_query_embedding(text_emb: np.ndarray) -> np.ndarray:
    """Build a query vector in the same fused space as indexed steps (896-dim).

    Text-first retrieval: queries embed HyDE hypothetical text only. The visual
    half is literal zeros — not CLIP-text — so query vectors align with steps
    whose on-screen content was distilled into Claude-extracted descriptions.

    Screenshot CLIP embeddings are stored at index time for diagnostics and
    future visual-query work; they are not used at query time today.
    """
    return _fuse_embeddings(text_emb, None)


# ── Core lookup ───────────────────────────────────────────────────────────────

def _chromadb_lookup(
    query: str,
    tutorial_id: str | None,
    top_k: int,
    history: list[dict],
) -> tuple[list[str], list[dict], list[float], dict]:
    """Return (docs, metas, distances, timing_meta): HyDE → pre-filter → fetch → cross-encode → dedup."""
    t0 = time.monotonic()

    hypo = _hypothetical_step(query, history)
    t_hyde = int((time.monotonic() - t0) * 1000)

    t1 = time.monotonic()
    text_emb = _get_text_model().encode(hypo, convert_to_numpy=True)
    query_embedding = _make_query_embedding(text_emb).tolist()

    collection = _get_chroma().get_or_create_collection("steps")

    # Determine the where clause
    tutorial_ids_searched = None
    if tutorial_id:
        where = {"tutorial_id": {"$eq": tutorial_id}}
    else:
        relevant_ids = _relevant_tutorial_ids(query_embedding, exclude_id=tutorial_id)
        tutorial_ids_searched = relevant_ids
        if relevant_ids and len(relevant_ids) == 1:
            where = {"tutorial_id": {"$eq": relevant_ids[0]}}
        elif relevant_ids:
            where = {"tutorial_id": {"$in": relevant_ids}}
        else:
            where = None

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(FETCH_K, collection.count()),
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    t_retrieval = int((time.monotonic() - t1) * 1000)

    timing = {
        "hypothetical_text": hypo,
        "tutorial_ids_searched": tutorial_ids_searched,
        "latency_hyde_ms": t_hyde,
        "latency_retrieval_ms": t_retrieval,
        "ce_scores": {},  # filled below
    }

    if not results["ids"][0]:
        return [], [], [], timing

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    distances = results["distances"][0]

    triples = [
        (d, m, dist)
        for d, m, dist in zip(docs, metas, distances)
        if dist <= MAX_DISTANCE
    ]
    if not triples:
        return [], [], [], timing

    # Cross-encoder re-rank — capture scores for logging
    if len(triples) > 1:
        try:
            ce = _get_cross_encoder()
            pairs = [(query, doc) for doc, _, _ in triples]
            scores = ce.predict(pairs).tolist()
            timing["ce_scores"] = {
                m["step_id"]: round(float(s), 4)
                for (_, m, _), s in zip(triples, scores)
            }
            ranked = sorted(zip(triples, scores), key=lambda x: x[1], reverse=True)
            triples = [t for t, _ in ranked]
        except Exception:
            log.warning("Cross-encoder re-ranking failed, falling back to distance order")

    if tutorial_id:
        triples.sort(key=lambda t: t[1].get("step_number", 0))

    triples = _dedup_results(triples)
    triples = triples[:top_k]

    docs_f, metas_f, dists_f = zip(*triples)
    return list(docs_f), list(metas_f), list(dists_f), timing


def _dedup_results(triples: list[tuple]) -> list[tuple]:
    """Drop steps ≥85% similar to an already-kept step (best-ranked copy wins)."""
    kept: list[tuple] = []
    kept_texts: list[str] = []
    for doc, meta, dist in triples:
        low = doc.lower()
        if any(difflib.SequenceMatcher(None, low, t).ratio() >= 0.85 for t in kept_texts):
            continue
        kept.append((doc, meta, dist))
        kept_texts.append(low)
    return kept


# ── Tutorial info helpers ─────────────────────────────────────────────────────

def _fetch_tutorial_info(metas: list[dict]) -> dict[str, dict]:
    unique_ids = list({m["tutorial_id"] for m in metas})
    info: dict[str, dict] = {}
    with get_db_session() as session:
        for tid in unique_ids:
            t = session.get(TutorialDB, tid)
            if t:
                video_id = (t.meta or {}).get("video_id") if t.meta else None
                info[tid] = {
                    "tutorial_title": t.title,
                    "source_url": t.source_url,
                    "source_type": t.source_type,
                    "video_id": video_id,
                }
    return info


def _build_steps_out(docs: list[str], metas: list[dict], tutorial_info: dict[str, dict]) -> list[dict]:
    return [
        {
            "step_number": m["step_number"],
            "step_id": m["step_id"],
            "tutorial_id": m["tutorial_id"],
            "timestamp_start": m.get("timestamp_start"),
            "visual_reference": m.get("visual_reference") or None,
            "text": doc,
            **tutorial_info.get(m["tutorial_id"], {}),
        }
        for doc, m in zip(docs, metas)
    ]


def _write_query_log(
    query: str,
    tutorial_id: str | None,
    history: list[dict],
    metas: list[dict],
    distances: list[float],
    timing: dict,
    answer_text: str,
    latency_synthesis_ms: int,
    total_latency_ms: int,
) -> None:
    """Fire-and-forget write to query_logs table."""
    try:
        ce_scores = timing.get("ce_scores", {})
        steps_returned = [
            {
                "step_id": m["step_id"],
                "distance": round(float(d), 4),
                "ce_score": ce_scores.get(m["step_id"]),
            }
            for m, d in zip(metas, distances)
        ]
        with get_db_session() as session:
            session.add(QueryLogDB(
                id=str(uuid.uuid4()),
                query_text=query,
                hypothetical_text=timing.get("hypothetical_text"),
                tutorial_scoped=tutorial_id,
                tutorial_ids_searched=timing.get("tutorial_ids_searched"),
                steps_returned=steps_returned,
                answer_text=answer_text,
                history_length=len(history),
                latency_hyde_ms=timing.get("latency_hyde_ms"),
                latency_retrieval_ms=timing.get("latency_retrieval_ms"),
                latency_synthesis_ms=latency_synthesis_ms,
                total_latency_ms=total_latency_ms,
            ))
            session.commit()
    except Exception:
        log.exception("Failed to write query log")


def _build_synthesis_messages(context: str, query: str, history: list[dict]) -> list[dict]:
    """Build Claude messages with conversation history for multi-turn context."""
    messages = []
    for msg in history[-4:]:
        role = msg.get("role")
        text = msg.get("text") or msg.get("answer") or ""
        if role in ("user", "assistant") and text:
            messages.append({"role": role, "content": text})
    messages.append({"role": "user", "content": f"Context steps:\n{context}\n\nQuestion: {query}"})
    return messages


# ── Public API ────────────────────────────────────────────────────────────────

def query_steps_stream(
    query: str,
    tutorial_id: str | None = None,
    top_k: int = TOP_K,
    history: list[dict] | None = None,
) -> Generator[str, None, None]:
    """SSE generator: yields steps immediately, then streams the Claude answer."""
    history = history or []
    t_start = time.monotonic()

    docs, metas, distances, timing = _chromadb_lookup(query, tutorial_id, top_k, history)

    if not docs:
        yield f"data: {json.dumps({'type': 'steps', 'steps': []})}\n\n"
        _write_query_log(query, tutorial_id, history, [], [], timing, "", 0,
                         int((time.monotonic() - t_start) * 1000))
        return

    tutorial_info = _fetch_tutorial_info(metas)
    steps_out = _build_steps_out(docs, metas, tutorial_info)
    yield f"data: {json.dumps({'type': 'steps', 'steps': steps_out})}\n\n"

    context = "\n".join(
        f"Step {m['step_number']} [{m.get('timestamp_start', 0):.0f}s]: {doc}"
        for doc, m in zip(docs, metas)
    )
    messages = _build_synthesis_messages(context, query, history)

    t_synth = time.monotonic()
    answer_parts: list[str] = []
    with _get_client().messages.stream(
        model=FAST_MODEL,
        max_tokens=300,
        system=(
            "You are a tutorial assistant. Answer the user's question in 1-3 sentences "
            "using ONLY the provided context steps. Be direct. "
            "If the steps don't answer the question, say so clearly."
        ),
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            answer_parts.append(text)
            yield f"data: {json.dumps({'type': 'token', 'text': text})}\n\n"

    latency_synthesis = int((time.monotonic() - t_synth) * 1000)
    total_latency = int((time.monotonic() - t_start) * 1000)
    _write_query_log(query, tutorial_id, history, metas, distances, timing,
                     "".join(answer_parts), latency_synthesis, total_latency)

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


def query_steps(
    query: str,
    tutorial_id: str | None = None,
    top_k: int = TOP_K,
    history: list[dict] | None = None,
) -> dict:
    """Synchronous version (used by Zendesk sidebar and tests)."""
    history = history or []
    t_start = time.monotonic()
    docs, metas, distances, timing = _chromadb_lookup(query, tutorial_id, top_k, history)

    if not docs:
        _write_query_log(query, tutorial_id, history, [], [], timing, "", 0,
                         int((time.monotonic() - t_start) * 1000))
        return {"answer": "No relevant steps found.", "steps": []}

    tutorial_info = _fetch_tutorial_info(metas)
    steps_out = _build_steps_out(docs, metas, tutorial_info)
    context = "\n".join(
        f"Step {m['step_number']} [{m.get('timestamp_start', 0):.0f}s]: {doc}"
        for doc, m in zip(docs, metas)
    )
    messages = _build_synthesis_messages(context, query, history)
    t_synth = time.monotonic()
    response = _get_client().messages.create(
        model=FAST_MODEL,
        max_tokens=300,
        system=(
            "You are a tutorial assistant. Answer the user's question in 1-3 sentences "
            "using ONLY the provided context steps. Be direct."
        ),
        messages=messages,
    )
    answer = response.content[0].text.strip()
    latency_synthesis = int((time.monotonic() - t_synth) * 1000)
    _write_query_log(query, tutorial_id, history, metas, distances, timing,
                     answer, latency_synthesis, int((time.monotonic() - t_start) * 1000))
    return {"answer": answer, "steps": steps_out}
