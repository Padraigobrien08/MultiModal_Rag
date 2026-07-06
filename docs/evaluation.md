# Retrieval evaluation

How we measure Stepwise retrieval quality, and the results of the retrieval
tuning pass.

## What we measure

`scripts/eval_queries.json` holds 25 simulated Stripe support tickets. Each
query carries ground-truth targets so the eval can score itself:

| field | meaning |
| --- | --- |
| `expected_video_ids` | ingested tutorial(s) whose steps actually answer the query, by YouTube `video_id` (stable across re-ingests, unlike UUID tutorial IDs) |
| `coverage` | `full` — a tutorial directly covers it · `partial` — a tutorial touches it · `none` — **no** ingested tutorial covers it, so the correct behavior is to return no steps |
| `expected_topics` | legacy topic hints (kept for reference) |

`intended_corpus_video_ids` lists the 7 Stripe tutorials the eval is designed
around. Ground truth was assigned by reading the actual extracted step titles of
each ingested tutorial, not by inspecting retrieval output.

## Three metrics — do not conflate them

A no-answer win on an uncovered query is **not** the same as retrieving the
right step. Reporting only the combined number inflates the picture, so the
harness (`scripts/run_eval.py`) reports three separate metrics:

1. **Answerable retrieval pass rate** *(the headline / conservative metric)* —
   over queries whose corpus has coverage (`full`/`partial`): PASS if the top
   step is in an expected tutorial, PARTIAL if any top-k step is, MISS otherwise.
2. **No-answer calibration** — over uncovered (`coverage: none`) queries: the
   fraction that correctly return no steps instead of surfacing something
   irrelevant.
3. **Overall support success** — strict PASS across all 25 (answerable-PASS +
   no-answer-correct). Reported for completeness, but never quoted alone: it
   climbs whenever *either* sub-metric does, so it hides regressions.

Per query the runner also reports retrieved tutorial/step IDs, L2 distance,
cross-encoder score, `expected_in_top_k`, and any **cross-corpus bleed** (steps
from tutorials outside the intended corpus).

## Clean-corpus vs full-index mode, and why bleed matters

The index holds 10 tutorials but only 7 are the intended Stripe corpus. The rest
— a 182-step and a 24-step *Claude Code* tutorial, a test-image tutorial, and an
empty "test" drive tutorial — are **cross-corpus bleed**: unrelated content that
can surface in Stripe answers.

- **Full-index mode** (default) searches everything, so bleed is possible and is
  reported as a first-class metric. This is the realistic production condition
  today, where multiple corpora share one index.
- **Clean-corpus mode** (`--clean-corpus`) restricts the search to
  `intended_corpus_video_ids`, bypassing the centroid pre-filter. Bleed is 0 by
  construction — it isolates *ranking* quality from *scoping* failures.

The gap between the two modes is the cost of not scoping the index. The eval can
enforce that boundary, but users need it in the product itself — that is what the
workspace/library scoping work is for.

## Running it

```bash
# Offline smoke path — validates the queries file + scoring logic, no network/models
python scripts/run_eval.py --self-check

# In-process (no server; loads models, needs ANTHROPIC_API_KEY)
python scripts/run_eval.py --in-process

# Clean-corpus mode — restrict retrieval to the 7 intended tutorials only
python scripts/run_eval.py --in-process --clean-corpus

# Against a running API
python scripts/run_eval.py --api http://localhost:8000

# Legacy manual 1/2/3 scoring
python scripts/run_eval.py --in-process --interactive
```

Timestamped runs are written to `scripts/eval_results_*.json` (git-ignored
scratch). The curated, committed benchmarks live in `docs/eval/`.

## Before / after (full index)

Committed artifacts:
[`docs/eval/baseline_full_index.json`](eval/baseline_full_index.json) (pre-tuning)
and
[`docs/eval/retrieval_quality_pass_full_index.json`](eval/retrieval_quality_pass_full_index.json)
(after). Both were produced by one A/B run that **pins the HyDE hypothetical and
candidate fetch per query**, then applies the old vs new post-processing to the
*same* candidates — so the delta reflects the tuning, not HyDE's run-to-run
variance.

| metric | before | after |
| --- | --- | --- |
| **Answerable retrieval pass rate** *(headline)* | 82% (14/17) | **82% (14/17)** |
| No-answer calibration | 12% (1/8) | **75% (6/8)** |
| Overall support success | 60% (15/25) | 80% (20/25) |
| Queries with cross-corpus bleed | 3 | 1 |

The tuning's value is concentrated where it should be: **answerable retrieval is
unchanged** (the relevance gate does not clip real answers), while no-answer
calibration and bleed improve sharply. The headline metric is deliberately the
one that did *not* move, so we are not claiming credit for no-answer wins.

> HyDE is generative, so absolute numbers drift by ~±1–2 queries between draws;
> the committed artifacts are a single self-consistent snapshot. The *shape*
> (answerable flat, no-answer up, bleed down) is stable across draws.

### What changed

1. **Cross-encoder relevance gate** (`stepwise/retrieval/retriever.py`). After
   re-ranking, two floors:
   - `MIN_CE_SCORE = -6.5` — if even the best step is below it, return no steps
     (no-answer). This threads a genuinely narrow band: the weakest
     legitimately-covered query ("SEPA/BACS", CE ≈ −6.3) sits just above the
     strongest uncovered query (CE ≈ −7.0). −6.5 protects the former while
     rejecting the latter, but the margin is thin.
   - `CE_DROP_GAP = 7.0` — drop tail steps scoring far below the best kept step.
2. **Cross-encoder now runs for a single candidate too** (previously skipped when
   only one survived the distance filter), so a lone weak match can be rejected.
3. **Clean-corpus mode** (`allowed_tutorial_ids` on `_chromadb_lookup`, exposed
   via `run_eval.py --clean-corpus`).
4. **`distance` and `ce_score` are now returned per step** by `/query` and
   `/query/sync`.
5. **Unified grounded-answer instruction.** `/query/sync` previously omitted the
   "if the steps don't answer the question, say so clearly" line that `/query`
   had; both now use the identical synthesis prompt. This is the real backstop
   for the no-answer cases the CE floor can't catch (below).

## Remaining failure modes

- **Semantically-adjacent gaps (q12 "test card numbers", q17 "add team member").**
  No covering tutorial exists, but retrieval surfaces topically-near steps
  (secret-key retrieval, account-settings) that the cross-encoder rates as
  *positively* relevant (CE +4…+6). No CE floor can reject these without also
  dropping genuinely-covered queries, so no-answer calibration tops out here.
  The unified no-answer synthesis prompt is the second line of defense; the real
  fix is ingesting the missing subscription / refund / team tutorials.
- **Ranking near-ties on multi-tutorial queries (q21, q24, q25).** The expected
  tutorial is retrieved but not at rank 1 (e.g. q21 "integrate into my website"
  ranks the payment-methods tutorial just above the integration tutorial), so
  they score PARTIAL rather than PASS.
- **Mildly-positive bleed.** The CE floor removes strongly-negative foreign
  matches (Claude Code steps at −9…−11) but not mild ones (≈ +2.8). Clean-corpus
  mode removes them entirely; in production the fix is scoping the index, not
  thresholding.
- **Corpus quality.** Several `stripe_corpus.json` topics were never ingested
  (`subscriptions`, `refunds`, `team_management`), and the `account_setup` video
  (`ArD4oZDtL_0`) is low quality — its "steps" are about anti-detect browsers and
  MAC-address spoofing, not legitimate Stripe setup.
