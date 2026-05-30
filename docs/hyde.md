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
        │   ← big gap →                    │  ← small gap →
        ▼                                  ▼
[indexed step about inviting]     [indexed step about inviting]
```

## Why it also fixes our specific asymmetry

In Stepwise, indexed steps are embedded as:

```
[text_norm (768-dim) | clip_image_norm_or_zeros (512-dim)]
```

Most steps have no screenshot, so the CLIP half is **zeros**.

Before HyDE, the query was embedded as:

```
[text_norm (768-dim) | clip_text_norm (512-dim)]
```

The CLIP half of the query is a text-encoding, the CLIP half of most indexed
steps is zeros. These don't cancel — they add a constant ~1.0 noise term to
every distance, making all results look equally distant.

With HyDE, the hypothetical is text-only, so we embed it as:

```
[text_norm (768-dim) | zeros (512-dim)]
```

Now query and indexed steps are in **the same subspace**. The distance is
purely driven by how semantically close the hypothetical is to each step.

## Trade-offs

| Pro | Con |
|---|---|
| Significantly better recall for question-style queries | Adds one LLM call before retrieval (~0.5–1s latency) |
| Closes query-document vocabulary gap | Hypothetical can occasionally mislead if LLM hallucinates an irrelevant topic |
| Free accuracy improvement — no re-indexing needed | The hallucination risk is low in practice because we only use the *embedding*, not the text itself |
| Fixes the CLIP-half asymmetry in our embedding scheme | |

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
