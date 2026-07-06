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

## Measured results — 2026-07-06

Scored run committed at
[`scripts/eval_results_20260706.json`](../scripts/eval_results_20260706.json).
Corpus indexed at eval time: **11 tutorials / 317 steps** (two of the 13 corpus
videos failed to ingest; the index also held a few non-Stripe tutorials and two
test entries — see failure mode 3). `top_k=3`, all 25 queries scored by hand.

| Metric | Result |
| ------ | ------ |
| **Pass rate** | **52%** (13 / 25) |
| **Hit rate** (pass + partial) | **76%** (19 / 25) |
| ✅ PASS | 13 |
| ⚠️ PARTIAL | 6 |
| ❌ MISS | 6 |
| 💥 ERROR | 0 |
| Target | 70% pass rate |

The pass rate is **below the 70% target**; the hit rate clears it. Read
honestly, this says retrieval ranking is solid but corpus *coverage* is thin:
when the answer exists in a tutorial, retrieval usually finds it (see webhooks,
getting-started, integration below); most misses are questions the videos simply
never answer.

### By topic

| Topic | Pass | Hit (pass+partial) | Total |
| ----- | :--: | :----------------: | :---: |
| webhooks        | 3 | 3 | 3 |
| getting_started | 3 | 3 | 3 |
| integration     | 1 | 1 | 1 |
| payment_methods | 1 | 2 | 2 |
| payment_links   | 1 | 2 | 2 |
| account_setup   | 2 | 2 | 4 |
| subscriptions   | 2 | 3 | 4 |
| payouts         | 0 | 2 | 2 |
| payments        | 0 | 1 | 4 |

`payments` and `payouts` pull the average down: those buckets are dominated by
operational tickets (refunds, double charges, declines, payout timing) that the
how-to tutorials don't cover.

### Failure examples

| # | Query | Score | What happened |
| - | ----- | :---: | ------------- |
| q07 | *How do I cancel a customer's subscription?* | ❌ MISS | A cancel-capable step exists (Webhooks step 29: "update / **pause** / cancel") but wasn't ranked top-3 for this phrasing — even though the near-identical *pause* query (q08) surfaced it at #1. |
| q09 | *How do I issue a refund to a customer?* | ❌ MISS | Zero steps returned. No refund content in the corpus. |
| q10 | *A customer was charged twice — what do I do?* | ❌ MISS | Returned "Confirm Payment in the Dashboard"; no duplicate-charge/refund content exists. |
| q17 | *How do I add a new team member?* | ❌ MISS | Returned sign-in / sign-up steps; no roles/permissions content in the corpus. |
| q23 | *My customer's card was declined — what should I tell them?* | ❌ MISS | Zero steps returned. No decline-handling content. |
| q13 | *When will my payout arrive?* | ⚠️ PARTIAL | Landed in the right payouts video, but the corpus covers schedule *configuration*, not arrival timing. |
| q16 | *Can I accept payments without a website?* | ⚠️ PARTIAL | Answerable via Payment Links / Terminal, but the top hit was a generic platform-intro step, not the payment-link creation step. |

Each run also writes a machine-readable artifact to
`scripts/eval_results_<timestamp>.json` with a `scores` array (per-query
`id` / `query` / `topic` / `score` / `note`) and a `summary` block
(`pass` / `partial` / `miss` / `pass_rate` / `hit_rate`).

## Known retrieval failure modes

1. **Corpus-coverage gaps dominate.** Four of six misses are questions the
   tutorials never answer — refunds (q09), duplicate charges (q10), card
   declines (q23), team roles (q17), invoice downloads (q25). Retrieval
   correctly returns nothing or an honest "not covered" answer, but from a
   support user's view it's still a miss. The lever here is corpus breadth, not
   the retriever.

2. **Phrasing-sensitive ranking.** Near-identical intents can rank differently.
   "Pause a subscription" (q08) surfaces the right step at #1; "cancel a
   subscription" (q07) — answerable by the *same* step — pushes it out of the
   top-3. HyDE narrows this gap but doesn't close it.

3. **Cross-tutorial bleed.** The index also held a few non-Stripe tutorials
   (Claude Code) and two test entries. On generic queries a foreign step can
   slip into the top-3 (a Hostinger "API token" step appeared for "find my API
   keys"). It rarely reaches #1, but it pollutes the tail — a reminder to keep
   the index scoped to one product.

4. **Generic intro steps outrank specific ones.** Broad "what is Stripe" /
   platform-overview steps sometimes win on high-level questions (q16), burying
   the concrete how-to step that actually answers the task.

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
