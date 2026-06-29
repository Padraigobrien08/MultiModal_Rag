# HyDE — Hypothetical Document Embeddings

## The problem it solves

Dense retrieval (embedding-based search) works by measuring cosine similarity
between a query vector and a set of document vectors. The assumption is that
similar meaning → similar vector position.

The problem: **queries and documents live in different parts of the embedding
space**, even when they're semantically related.

A user asks:
> "How do I invite a team member?"

The relevant document says:
> "Invite a Team Member. Navigate to Settings → Team, click Invite, enter the
> email address, and assign a role."

These are about the same thing, but they're *linguistically different*:
one is a question, the other is an imperative instruction. Bi-encoder models
(like sentence-transformers) are trained to bring related things close together,
but this question↔answer gap is a known weakness, especially for short queries
against long declarative documents.

## The HyDE solution

**Instead of embedding the question, embed a hypothetical answer.**

1. Pass the query to an LLM: *"Write a tutorial step that would answer this question."*
2. The LLM generates something like: *"Invite a Team Member. Go to Settings → Team Members, click the Invite button, enter the recipient's email, and select their permission level."*
3. Embed **that** instead of the original query.
4. Search the index with the hypothetical embedding.

The hypothetical document is:
- In the same **style** as indexed content (declarative, action-oriented)
- In the same **vocabulary** domain
- Roughly the same **length** as what's indexed

So its vector lands much closer to real matching documents, even though the
hypothetical itself may be factually wrong or imprecise.

```
Without HyDE:                     With HyDE:

query: "how do I invite a         hypothetical: "Invite a Team
team member?"                     Member. Navigate to Settings →
        │                         Team and click Invite..."
        │                                  │
        ▼                                  ▼
[question vector]                 [answer-shaped vector]
        │                                  │
        │   ← big gap →                    │  ← smaller gap →
        ▼                                  ▼
[indexed step about inviting]     [indexed step about inviting]
```

## How Stepwise embeds steps and queries

Stepwise uses **text-first retrieval over visually enriched step descriptions**.
Screenshots matter at **ingestion** (Claude reads them when extracting steps)
and at **answer time** (retrieved steps link back to frame images), but
**query-time search is driven by text**, not by image-to-image matching.

### Index time (per step)

Each step is stored as a fused **896-dimensional** unit vector:

```
[text_norm (384-dim) | image_norm_or_zeros (512-dim)]
```

| Component | Model | Dimensions | When used |
|---|---|---|---|
| Text | `all-MiniLM-L6-v2` | 384 | Always — step title + description |
| Image | `clip-ViT-B-32` | 512 | When a screenshot file exists on disk |
| Fused | concat + L2 norm | 896 | Stored in ChromaDB |

Steps without a screenshot use a **zero image half** before the final
normalisation. Steps with a screenshot include a CLIP image embedding in the
image half. That visual signal is stored for diagnostics and future work; it is
**not** how queries are matched today.

### Query time

1. HyDE generates a hypothetical answer-shaped step (text only).
2. MiniLM embeds that text (384-dim).
3. `_make_query_embedding()` fuses it with a **zero visual half** (512-dim):

```
[text_norm (384-dim) | zeros (512-dim)]  →  L2-normalised 896-dim query vector
```

No CLIP model is loaded during query retrieval. Visual information reaches
search only through Claude-extracted step descriptions (e.g. button labels, menu
paths) that were written during multimodal structuring.

### Why the zero visual half

Using a zero image half at query time keeps query vectors in the same subspace
as text-heavy indexed steps and avoids mixing CLIP-text encodings with CLIP-image
encodings. The distance score is driven by how close the HyDE hypothetical is to
each step's **text** embedding, with indexed screenshot embeddings acting as a
secondary signal in the fused space rather than enabling image-query search.

**True visual query retrieval** (e.g. search by screenshot or CLIP-text query
embedding) is a future extension, not current behaviour.

## Trade-offs

| Pro | Con |
|---|---|
| Significantly better recall for question-style queries | Adds one LLM call before retrieval (~0.5–1s latency) |
| Closes query-document vocabulary gap | Hypothetical can occasionally mislead if LLM hallucinates an irrelevant topic |
| Honest text-first retrieval — no false claim of image search | Does not match on raw pixels or uploaded query images |
| Query vectors align with zero-image-half steps | Steps with strong CLIP image halves are a weaker text-first match |

## The hallucination doesn't matter

This is the counterintuitive part: **the LLM doesn't need to be correct**.

We throw away the hypothetical text immediately after embedding it. If the LLM
hallucinates a plausible-sounding but wrong answer, its embedding still lands
near the correct topic in vector space. The retrieval step then finds real,
verified steps from your tutorials. The synthesis step (the second Claude call)
only ever sees real indexed content.

## Original paper

Gao et al., 2022 — *Precise Zero-Shot Dense Retrieval without Relevance Labels*
[arxiv.org/abs/2212.10496](https://arxiv.org/abs/2212.10496)

The core insight from the paper: you don't need a perfectly accurate
hypothetical — you need an embedding that's *directionally correct*. LLMs are
good at generating plausible-sounding text in the right domain, which is
exactly the property that makes HyDE work.
