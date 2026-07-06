# Architecture & Design Decisions

This document records the significant design decisions behind Stepwise and the
tradeoffs each one makes. It complements the pipeline walkthroughs in the
[README](../README.md) and the retrieval deep-dive in [hyde.md](hyde.md).

## System shape

Stepwise is two services plus an integration:

- **Backend** — a FastAPI app (`stepwise/`) that owns ingestion, indexing, and
  retrieval. State lives in **ChromaDB** (vectors) and **SQLite/SQLAlchemy**
  (relational).
- **Frontend** — a Next.js dashboard (`web/`) for ingesting sources and querying
  the library.
- **Zendesk sidebar** — a thin ZAF app (`zendesk-app/`) that calls the backend
  from inside a support ticket.

The rest of this document explains *why* it is shaped this way.

## Decisions

### 1. Keep the visual modality — but retrieve text-first

**Decision.** At ingest time, Claude reads the transcript *and* screenshots to
produce step descriptions, and each step is indexed as a fused **text + CLIP
image** vector. At query time, the query vector uses HyDE text with a **zero
visual half** — no CLIP embedding of the question.

**Why.** Half the information in a UI tutorial is on screen, not in the
narration. Discarding frames (transcript-only RAG) loses that. But image-to-image
matching from a text question is unreliable, so visual signal is injected once —
into the step descriptions Claude writes — rather than matched at query time.
Screenshots are returned as *evidence*, not used as a search key.

**Tradeoff.** The visual signal is only as good as Claude's description of each
frame; a subtlety Claude doesn't mention is not searchable. In exchange, queries
stay in a single well-behaved text embedding space and screenshots still ground
every answer. See [hyde.md](hyde.md) for the full embedding scheme.

### 2. HyDE for the question↔instruction gap

**Decision.** Embed a hypothetical *answer* (a Claude-generated step) instead of
the raw question.

**Why.** Questions ("how do I invite a teammate?") and instructions ("Go to
Settings → Team, click Invite…") sit in different regions of a bi-encoder's
space. Embedding an answer-shaped string closes that gap. Conversation history is
folded in so follow-ups ("how do I undo that?") resolve.

**Tradeoff.** Adds one Claude call to the query path (latency + cost), so HyDE
uses a fast model. Full rationale in [hyde.md](hyde.md).

### 3. Cross-encoder re-rank on top of bi-encoder recall

**Decision.** Retrieve candidates with the bi-encoder, then re-score the top
candidates with a `ms-marco-MiniLM` cross-encoder.

**Why.** Bi-encoders are fast but approximate; a cross-encoder reads query and
candidate together and reaches precision the bi-encoder can't. Running it only on
the shortlist keeps the cost bounded.

**Tradeoff.** Extra model to load and run per query. Worth it for precision on
the handful of results a user actually sees.

### 4. Split storage: ChromaDB for vectors, SQLite for relations

**Decision.** Vectors live in ChromaDB; tutorials, steps, jobs, and query logs
live in SQLite via SQLAlchemy.

**Why.** Each store does what it is good at — ANN search vs. relational queries,
joins, and telemetry. SQLite keeps operational overhead near zero for a
single-node deployment.

**Tradeoff.** Two stores to keep consistent, and SQLite is single-writer — fine
at this scale, a migration target if the workload grows. Multi-tenancy (per-tenant
namespacing across both stores) is deferred to a later phase — see
[roadmap.md](roadmap.md).

### 5. Per-stage Claude model configuration

**Decision.** Every Claude call site has its own model setting in
`stepwise.config.Settings` (`STRUCTURING_MODEL`, `HYDE_MODEL`,
`SYNTHESIS_MODEL`, `CONSOLIDATION_MODEL`); none are hard-coded.

**Why.** The stages have different cost/quality profiles: high-volume step
extraction wants a cheap fast model (Haiku); consolidation, where judgement
matters, is worth a stronger model (Sonnet). Separating them lets each be tuned
independently, and centralising them keeps model IDs out of the pipeline code.

**Tradeoff.** More configuration surface. Mitigated by sensible defaults; model
IDs change over time, so the defaults pin what the project was built against.

### 6. Cost-engineer the ingestion path, not the query path

**Decision.** Ingestion (the expensive, multimodal path) is optimised with
scene-change frame dedup, Haiku for extraction, and prompt caching — while
keeping the visual modality.

**Why.** Ingestion is where the multimodal LLM calls happen, so a 30-second
talking-head clip collapsing from 6 frames to 1 (a 32×32 grayscale diff) removes
cost before it ever reaches Claude, without dropping meaningful frames.

**Tradeoff.** The dedup heuristic can occasionally merge visually similar but
semantically distinct frames. The threshold is tuned to favour recall of
distinct UI states.

### 7. Unified ingestion pipeline over a normalised artifact

**Decision.** Every source — YouTube URL, Drive `.mp4`, Notion page, folder of
PNGs — is normalised to the same `transcript[] + frames[]` shape, then run
through one shared pipeline.

**Why.** One pipeline to test and harden instead of four. New sources become a
thin adapter that produces the common artifact.

**Tradeoff.** The normalised shape is the lowest common denominator; a
source-specific optimisation has to fit the shared contract or bypass it.

### 8. Streamed synthesis grounded only in retrieved steps

**Decision.** The final answer streams token-by-token over SSE and is grounded
strictly in the retrieved steps, each carrying its timestamp and frame.

**Why.** Streaming improves perceived latency for a generation-bound step;
grounding only in retrieved steps keeps answers citable and reduces
hallucination.

**Tradeoff.** SSE adds a streaming code path over a plain JSON response. A
non-streaming `POST /query/sync` is kept for callers that need a single JSON
payload (the eval harness and the Zendesk app use it).

### 9. Idempotent ingestion

**Decision.** Re-ingesting an already-indexed source is a no-op that returns the
existing record.

**Why.** Auto-ingestion watchers re-scan sources on a schedule; without
idempotency every scan would duplicate content.

**Tradeoff.** Requires a stable identity per source and a check before work. Cheap
relative to re-running the whole multimodal pipeline.

## Where to go next

- Retrieval internals and the embedding scheme: [hyde.md](hyde.md)
- How quality is measured: [evaluation.md](evaluation.md)
- What's shipped and what's planned: [roadmap.md](roadmap.md)
