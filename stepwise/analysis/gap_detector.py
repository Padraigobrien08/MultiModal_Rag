"""
Gap detector: identifies topics users ask about that the knowledge base can't answer.

Algorithm:
  1. Pull query logs where retrieval quality was poor (best distance > POOR_THRESHOLD)
     or no results were returned at all.
  2. Weight by frequency — the same query asked 10× is 10× the signal.
  3. Cluster unique query texts by cosine similarity (union-find, O(n²) — fine for
     the hundreds of queries expected).
  4. Filter out clusters whose total weighted frequency is below MIN_WEIGHT.
  5. Call Claude Haiku once per cluster to produce a structured gap description.

Distance calibration (from retriever.py):
  relevant ~0.84–1.00 · borderline ~1.17–1.35 · irrelevant ~1.42+
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

POOR_THRESHOLD = 1.1       # best-result distance above this = poorly served
MIN_WEIGHT = 2             # minimum total query hits to surface a gap
SIMILARITY_THRESHOLD = 0.80  # cosine similarity to merge queries into same cluster
MAX_RECENT = 2000          # how many recent log rows to analyse

_GAP_TOOL = {
    "name": "describe_gap",
    "description": "Describe a knowledge gap in a tutorial library.",
    "input_schema": {
        "type": "object",
        "properties": {
            "topic":           {"type": "string", "description": "Short label, 2–5 words"},
            "description":     {
                "type": "string",
                "description": "What tutorial content would fill this gap, 1–2 sentences",
            },
            "suggested_title": {
                "type": "string",
                "description": "A tutorial title that would answer these queries",
            },
            "search_terms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2–4 YouTube search terms to find relevant content",
            },
        },
        "required": ["topic", "description", "suggested_title", "search_terms"],
    },
}


@dataclass
class Gap:
    topic: str
    description: str
    suggested_title: str
    search_terms: list[str]
    query_count: int          # total weighted hits (includes duplicates)
    unique_query_count: int   # distinct query texts in this cluster
    example_queries: list[str] = field(default_factory=list)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _collect_poor_queries(session, library_id: str) -> dict[str, int]:
    """
    Return {query_text: frequency} for queries that were poorly served within
    ``library_id``. Frequency > 1 when the same query was asked multiple times.
    """
    from stepwise.models import QueryLogDB

    logs = (
        session.query(QueryLogDB)
        .filter(QueryLogDB.library_id == library_id)
        .order_by(QueryLogDB.created_at.desc())
        .limit(MAX_RECENT)
        .all()
    )

    counts: dict[str, int] = {}
    for log in logs:
        steps = log.steps_returned or []
        is_poor = (
            not steps
            or min(s.get("distance", 9.9) for s in steps) > POOR_THRESHOLD
        )
        if is_poor:
            key = log.query_text.strip().lower()
            counts[key] = counts.get(key, 0) + 1

    return counts


def _cluster(queries: list[str], weights: list[int], text_model) -> list[tuple[list[str], int]]:
    """
    Cluster queries by cosine similarity using union-find.
    Returns list of (cluster_queries, total_weight) sorted by weight desc.
    """
    if not queries:
        return []

    embs = text_model.encode(queries, convert_to_numpy=True)
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    embs = embs / np.maximum(norms, 1e-8)
    sim = embs @ embs.T  # (n, n) cosine similarity

    # Union-Find
    parent = list(range(len(queries)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(queries)):
        for j in range(i + 1, len(queries)):
            if float(sim[i, j]) >= SIMILARITY_THRESHOLD:
                parent[find(i)] = find(j)

    groups: dict[int, tuple[list[str], int]] = {}
    for i, q in enumerate(queries):
        root = find(i)
        if root not in groups:
            groups[root] = ([], 0)
        qs, w = groups[root]
        qs.append(q)
        groups[root] = (qs, w + weights[i])

    return sorted(groups.values(), key=lambda x: x[1], reverse=True)


def _describe_gap(queries: list[str], total_weight: int, client, model: str) -> Gap:
    sample = queries[:10]
    query_list = "\n".join(f"- {q}" for q in sample)

    resp = client.messages.create(
        model=model,
        max_tokens=256,
        system=(
            "You are a knowledge gap analyst for a software tutorial library. "
            "Given user queries that the system couldn't answer well, identify "
            "the missing topic and suggest how to fill it."
        ),
        tools=[_GAP_TOOL],
        tool_choice={"type": "tool", "name": "describe_gap"},
        messages=[{
            "role": "user",
            "content": f"These queries went unanswered ({total_weight} total hits):\n{query_list}",
        }],
    )

    tool_use = next(b for b in resp.content if b.type == "tool_use")
    d = tool_use.input
    return Gap(
        topic=d["topic"],
        description=d["description"],
        suggested_title=d["suggested_title"],
        search_terms=d.get("search_terms", []),
        query_count=total_weight,
        unique_query_count=len(queries),
        example_queries=queries[:5],
    )


# ── Cache ─────────────────────────────────────────────────────────────────────

# Cached per library: {library_id: (result, timestamp)}.
_cache: dict[str, tuple[list[dict], float]] = {}
CACHE_TTL = 3600.0  # 1 hour


def detect_gaps(force: bool = False, library_id: str | None = None) -> list[dict]:
    """
    Run gap detection for a library and return gap dicts sorted by query_count.

    Results are cached in-memory per library for CACHE_TTL seconds. Pass
    force=True to bypass the cache and recompute immediately.
    """
    from stepwise.config import settings

    library_id = library_id or settings.default_library_id

    cached = _cache.get(library_id)
    if not force and cached is not None and (time.monotonic() - cached[1]) < CACHE_TTL:
        return cached[0]

    import anthropic

    from stepwise.indexing.indexer import _get_text_model, get_db_session

    with get_db_session() as session:
        freq_map = _collect_poor_queries(session, library_id)

    if not freq_map:
        _cache[library_id] = ([], time.monotonic())
        return []

    queries = list(freq_map.keys())
    weights = [freq_map[q] for q in queries]

    text_model = _get_text_model()
    clusters = _cluster(queries, weights, text_model)

    significant = [(qs, w) for qs, w in clusters if w >= MIN_WEIGHT]
    if not significant:
        _cache[library_id] = ([], time.monotonic())
        return []

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    gaps: list[Gap] = []
    for cluster_queries, total_weight in significant:
        try:
            gap = _describe_gap(cluster_queries, total_weight, client, settings.structuring_model)
            gaps.append(gap)
        except Exception:
            continue

    result = [
        {
            "topic": g.topic,
            "description": g.description,
            "suggested_title": g.suggested_title,
            "search_terms": g.search_terms,
            "query_count": g.query_count,
            "unique_query_count": g.unique_query_count,
            "example_queries": g.example_queries,
        }
        for g in gaps
    ]

    _cache[library_id] = (result, time.monotonic())
    return result
