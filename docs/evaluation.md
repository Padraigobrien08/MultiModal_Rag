# Evaluation — Retrieval Quality

This document describes how Stepwise's retrieval quality is measured, so the
claims in the README are **auditable** rather than just descriptive. It covers
the 25-query harness, the scoring rubric, the target, and how to run the eval
safely.

The harness lives in [`scripts/run_eval.py`](../scripts/run_eval.py); the query
set is [`scripts/eval_queries.json`](../scripts/eval_queries.json).

## What the eval measures

Stepwise turns tutorial videos into a retrieval system that answers a support
question with the exact step and screenshot. The eval asks a simple question:

> Given a realistic support ticket, does the retriever return the **right video
> and the right step**?

It does **not** measure answer fluency, latency, or ingestion accuracy — only
whether retrieval surfaces the correct step for a query.

## The query set

25 queries in [`scripts/eval_queries.json`](../scripts/eval_queries.json), each
a paraphrased Stripe support ticket. Every entry has this shape:

```json
{
  "id": "q01",
  "ticket": "How do I find my API keys?",
  "topic": "account_setup",
  "expected_topics": ["account_setup", "getting_started"]
}
```

- `ticket` — the query text sent to the API.
- `topic` — the primary topic, used for the per-topic breakdown.
- `expected_topics` — the topic(s) a correct result should come from. This field
  documents the intended answer for a human scorer; **the current harness does
  not auto-check it** (scoring is manual — see below). It is a hook for future
  automated scoring.

Topic coverage across the 25 queries:

| Topic            | Queries |
| ---------------- | ------- |
| account_setup    | 4       |
| payments         | 4       |
| subscriptions    | 4       |
| webhooks         | 3       |
| getting_started  | 3       |
| payouts          | 2       |
| payment_links    | 2       |
| payment_methods  | 2       |
| integration      | 1       |

The queries run against the 13-video Stripe tutorial corpus in
[`scripts/stripe_corpus.json`](../scripts/stripe_corpus.json), ingested with
[`scripts/ingest_corpus.py`](../scripts/ingest_corpus.py).

## Scoring rubric

For each query the harness prints the returned answer and the retrieved steps
(step number, timestamp, text), then asks the operator to score it. Scoring is
**human judgement** — there is no automated relevance oracle.

| Score       | Meaning                                          |
| ----------- | ------------------------------------------------ |
| ✅ PASS      | Directly relevant — right video, right step      |
| ⚠️ PARTIAL  | Vaguely related but not the best answer          |
| ❌ MISS      | Wrong topic entirely                             |
| ⏭ SKIP      | Excluded from the count (e.g. bad query)         |
| 💥 ERROR     | The request failed (HTTP / network); not counted |

Two headline metrics are computed over the **counted** queries (everything
except SKIP, ERROR, and unscored):

- **Pass rate** = `PASS / counted`
- **Hit rate** = `(PASS + PARTIAL) / counted`

## Target

**70% pass rate** is the Phase 1 exit criterion. The harness reports the outcome
directly:

- 🟢 `pass_rate >= 70%` — Phase 1 exit criteria met.
- 🟡 `hit_rate >= 70%` but `pass_rate < 70%` — review the partials.
- 🔴 otherwise — fix embedding/chunking before building further.

## Sample result summary

Below is the **shape** of a completed interactive run (illustrative format, not
measured numbers). Reproduce real numbers by running the eval yourself — see the
next section.

```
============================================================
RESULTS SUMMARY
============================================================

  ✅ PASS:    <n>  (<pass_rate>%)
  ⚠️  PARTIAL: <n>
  ❌ MISS:    <n>

  Pass rate:     <pass_rate>%
  Hit rate:      <hit_rate>%  (pass + partial)
  Target:        70% pass rate

  By topic:
    account_setup         <pass>/<total>
    payments              <pass>/<total>
    ...
```

Each run also writes a machine-readable artifact to
`scripts/eval_results_<timestamp>.json` with a `scores` array (per-query
`id` / `query` / `topic` / `score` / `note`) and a `summary` block
(`pass` / `partial` / `miss` / `pass_rate` / `hit_rate`).

**Last known result:** no scored run is committed to the repo yet. The
`scripts/eval_results_*.json` artifacts currently checked in are `--auto`
(unscored) inspection dumps, so their `pass_rate` is `0` by construction, not a
measured score. Run the interactive harness to produce a citable pass rate and
commit the resulting JSON next to this doc.

## How to run the eval

The eval drives a **running** Stepwise API; it does not import the pipeline
directly. Three steps: configure, ingest, evaluate.

### 1. Configure

The only required secret is the Anthropic API key:

```bash
cp .env.example .env
# edit .env → ANTHROPIC_API_KEY=sk-ant-...
```

### 2. Start the API and ingest the corpus

```bash
uvicorn stepwise.api.app:app --port 8000        # terminal 1
python scripts/ingest_corpus.py                 # terminal 2 (one-time per corpus)
```

Ingestion is idempotent — already-indexed videos are skipped. Add
`--sequential` if you hit Anthropic rate limits.

### 3. Run the eval

```bash
python scripts/run_eval.py                 # interactive scoring (produces a pass rate)
python scripts/run_eval.py --auto          # dump results only, no scoring
python scripts/run_eval.py --top-k 3       # steps retrieved per query (default 3)
python scripts/run_eval.py --api http://localhost:8000
```

## External services & keys

| Dependency               | Used for                                          | Key / cost                                        |
| ------------------------ | ------------------------------------------------- | ------------------------------------------------- |
| **Anthropic API**        | Step structuring (ingest), HyDE + answer synthesis (query) | `ANTHROPIC_API_KEY` — **spends real tokens** |
| **YouTube (via yt-dlp)** | Downloading the 13 corpus videos at ingest time   | No key; network access; subject to YouTube's ToS  |
| **sentence-transformers / CLIP** | Local embeddings for retrieval            | No key; model weights downloaded on first use     |

## Running it safely

- **It costs money.** A full run makes Anthropic calls for ingesting 13 videos
  (once) plus HyDE and synthesis for all 25 queries. Ingest once, then re-run
  the query eval as needed.
- **Dry-run first.** Use `--auto` to sanity-check that the API responds and the
  corpus is indexed before committing to interactive scoring.
- **Never commit secrets.** `.env` is git-ignored; see
  [SECURITY.md](../SECURITY.md).
- **Keep it local.** Point `--api` only at a server you control; the eval sends
  the query text and reads back answers.
- **Rate limits.** Ingest with `--sequential` if you see HTTP 429s from
  Anthropic.
