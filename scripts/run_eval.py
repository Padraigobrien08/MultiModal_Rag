#!/usr/bin/env python3
"""
Retrieval eval runner for Stepwise.

Scores the 25 simulated Stripe support queries in scripts/eval_queries.json
against their ground-truth targets (expected_video_ids + coverage) and prints
retrieval diagnostics: retrieved tutorial/step IDs, L2 distances, cross-encoder
scores, whether an expected tutorial appeared in the top-k, and any
cross-corpus bleed.

Transports:
  (default)      POST /query/sync on a running API   (needs --api server up)
  --in-process   call the retriever directly          (no server; loads models)

Modes:
  (default)      auto-score against ground truth + diagnostics
  --clean-corpus restrict retrieval to intended_corpus_video_ids (in-process
                 only) so eval runs against only the intended corpus, avoiding
                 cross-corpus bleed
  --interactive  prompt for a manual 1/2/3 score per query (legacy)
  --self-check   validate the queries file + scoring logic offline (no network,
                 no models) — the smoke path

Usage:
  python scripts/run_eval.py --in-process
  python scripts/run_eval.py --in-process --clean-corpus
  python scripts/run_eval.py --api http://localhost:8000
  python scripts/run_eval.py --self-check
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent

# Manual scoring options (legacy --interactive mode)
SCORE_OPTIONS = {
    "1": ("PASS",    "✅", "Directly relevant — right video, right step"),
    "2": ("PARTIAL", "⚠️", "Vaguely related but not the best answer"),
    "3": ("MISS",    "❌", "Wrong topic entirely"),
    "s": ("SKIP",    "⏭", "Skip this query"),
}


# ── Ground-truth auto-scoring ───────────────────────────────────────────────

def auto_score(query: dict, got_video_ids: list[str], corpus: set[str]) -> tuple[str, dict]:
    """Score retrieval against ground truth. Returns (verdict, diagnostics).

    coverage == "none": the correct behavior is to return no steps, so PASS iff
    nothing came back. Otherwise PASS when the top step is in an expected
    tutorial, PARTIAL when any top-k step is, MISS otherwise.
    """
    expected = set(query.get("expected_video_ids") or [])
    coverage = query.get("coverage", "unknown")
    bleed = [v for v in got_video_ids if v and v not in corpus]
    expected_in_top_k = any(v in expected for v in got_video_ids)

    if coverage == "none":
        verdict = "PASS" if not got_video_ids else "MISS"
    elif got_video_ids and got_video_ids[0] in expected:
        verdict = "PASS"
    elif expected_in_top_k:
        verdict = "PARTIAL"
    else:
        verdict = "MISS"

    return verdict, {
        "expected_in_top_k": expected_in_top_k,
        "bleed_video_ids": bleed,
    }


# ── Transports ──────────────────────────────────────────────────────────────

def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def run_http(api: str, query: str, top_k: int) -> dict:
    return post_json(f"{api}/query/sync", {"query": query, "top_k": top_k})


class InProcessRunner:
    """Call the retriever directly. Optionally restrict to a clean corpus."""

    def __init__(self, clean_corpus_video_ids: list[str] | None):
        # Imported lazily so --self-check and --api modes never load ML models.
        from stepwise.indexing import get_db_session
        from stepwise.models import TutorialDB
        from stepwise.retrieval import retriever

        self._retriever = retriever
        self._vid_by_tid = {}
        self._allowed = None
        with get_db_session() as session:
            for t in session.query(TutorialDB).all():
                self._vid_by_tid[t.id] = (t.meta or {}).get("video_id")
        if clean_corpus_video_ids is not None:
            wanted = set(clean_corpus_video_ids)
            self._allowed = [
                tid for tid, vid in self._vid_by_tid.items() if vid in wanted
            ]

    def run(self, query: str, top_k: int) -> dict:
        docs, metas, distances, timing = self._retriever._chromadb_lookup(
            query, None, top_k, [], allowed_tutorial_ids=self._allowed
        )
        ce = timing.get("ce_scores", {})
        steps = [
            {
                "step_id": m["step_id"],
                "step_number": m["step_number"],
                "tutorial_id": m["tutorial_id"],
                "video_id": self._vid_by_tid.get(m["tutorial_id"]),
                "distance": round(float(d), 4),
                "ce_score": ce.get(m["step_id"]),
                "text": doc,
            }
            for doc, m, d in zip(docs, metas, distances)
        ]
        return {"answer": "", "steps": steps}


# ── Rendering ───────────────────────────────────────────────────────────────

def step_video_ids(result: dict) -> list[str]:
    return [s.get("video_id") for s in result.get("steps", [])]


def print_diagnostics(result: dict) -> None:
    steps = result.get("steps", [])
    if not steps:
        print("  Steps:  (none — no-answer)")
        return
    print(f"  Steps ({len(steps)}):  vid          #   dist    ce")
    for s in steps:
        ce = s.get("ce_score")
        ce_str = f"{ce:6.2f}" if isinstance(ce, (int, float)) else "     -"
        dist = s.get("distance")
        dist_str = f"{dist:.3f}" if isinstance(dist, (int, float)) else "  -  "
        print(
            f"    {str(s.get('video_id')):12} #{str(s.get('step_number','?')):3} "
            f"{dist_str}  {ce_str}   {s.get('step_id','')[:12]}"
        )


def interactive_score(result: dict) -> tuple[str, str]:
    print_diagnostics(result)
    print()
    for k, (label, icon, desc) in SCORE_OPTIONS.items():
        print(f"  [{k}] {icon} {label:8s} — {desc}")
    while True:
        raw = input("  Score: ").strip().lower()
        if raw in SCORE_OPTIONS:
            label, _, _ = SCORE_OPTIONS[raw]
            note = input("  Note (optional): ").strip() if raw in ("2", "3") else ""
            return label, note
        print("  Enter 1, 2, 3, or s")


# ── Self-check (offline smoke path) ─────────────────────────────────────────

def self_check(queries: list[dict], corpus: set[str]) -> int:
    """Validate the queries file and auto-scoring logic without any network."""
    problems = []
    ids = set()
    for q in queries:
        qid = q.get("id", "?")
        if qid in ids:
            problems.append(f"{qid}: duplicate id")
        ids.add(qid)
        for field in ("id", "ticket", "coverage"):
            if not q.get(field):
                problems.append(f"{qid}: missing {field}")
        cov = q.get("coverage")
        if cov not in ("full", "partial", "none"):
            problems.append(f"{qid}: bad coverage {cov!r}")
        exp = q.get("expected_video_ids")
        if exp is None:
            problems.append(f"{qid}: missing expected_video_ids")
        elif cov == "none" and exp:
            problems.append(f"{qid}: coverage none but has expected_video_ids")
        elif cov != "none" and not exp:
            problems.append(f"{qid}: coverage {cov} but no expected_video_ids")
        for v in exp or []:
            if v not in corpus:
                problems.append(f"{qid}: expected {v} not in intended corpus")

    # Exercise the scoring logic on synthetic retrievals.
    cases = [
        ({"coverage": "full", "expected_video_ids": ["A"]}, ["A", "B"], "PASS"),
        ({"coverage": "full", "expected_video_ids": ["A"]}, ["B", "A"], "PARTIAL"),
        ({"coverage": "full", "expected_video_ids": ["A"]}, ["B", "C"], "MISS"),
        ({"coverage": "none", "expected_video_ids": []},    [],         "PASS"),
        ({"coverage": "none", "expected_video_ids": []},    ["A"],      "MISS"),
    ]
    for q, got, want in cases:
        verdict, _ = auto_score(q, got, {"A", "B", "C"})
        if verdict != want:
            problems.append(f"scoring: {q['coverage']} {got} -> {verdict}, want {want}")

    if problems:
        print("SELF-CHECK FAILED:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print(f"SELF-CHECK OK — {len(queries)} queries, scoring logic verified.")
    return 0


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--in-process", action="store_true",
                        help="Call the retriever directly instead of the HTTP API")
    parser.add_argument("--clean-corpus", action="store_true",
                        help="Restrict retrieval to intended_corpus_video_ids "
                             "(in-process only)")
    parser.add_argument("--interactive", action="store_true",
                        help="Manually score each query (legacy 1/2/3)")
    parser.add_argument("--self-check", action="store_true",
                        help="Validate the queries file + scoring offline")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    data = json.loads((BASE_DIR / "eval_queries.json").read_text())
    queries = data["queries"]
    corpus = set(data.get("intended_corpus_video_ids", []))

    if args.self_check:
        return self_check(queries, corpus)

    if args.clean_corpus and not args.in_process:
        parser.error("--clean-corpus requires --in-process")

    runner = None
    if args.in_process:
        runner = InProcessRunner(sorted(corpus) if args.clean_corpus else None)

    print("Stepwise — Retrieval Eval")
    transport = "in-process" + (" (clean corpus)" if args.clean_corpus else "") \
        if args.in_process else f"HTTP {args.api}"
    print(f"Transport: {transport}  |  top_k={args.top_k}  |  queries={len(queries)}")
    print("=" * 64)

    scores = []
    for i, q in enumerate(queries, 1):
        print(f"\n{'─' * 64}")
        print(f"[{i:02d}/{len(queries)}]  {q['id'].upper()}  cov={q['coverage']}  "
              f"expected={q.get('expected_video_ids')}")
        print(f"  Query: \"{q['ticket']}\"")

        try:
            result = runner.run(q["ticket"], args.top_k) if runner \
                else run_http(args.api, q["ticket"], args.top_k)
        except urllib.error.HTTPError as e:
            print(f"  ✗ HTTP {e.code}: {e.read().decode()[:100]}")
            scores.append({"id": q["id"], "score": "ERROR", "note": f"HTTP {e.code}"})
            continue
        except Exception as e:
            print(f"  ✗ Error: {e}")
            scores.append({"id": q["id"], "score": "ERROR", "note": str(e)})
            continue

        got = step_video_ids(result)
        if args.interactive:
            verdict, note = interactive_score(result)
            diag = {"expected_in_top_k": any(v in (q.get("expected_video_ids") or [])
                                             for v in got),
                    "bleed_video_ids": [v for v in got if v and v not in corpus]}
        else:
            verdict, diag = auto_score(q, got, corpus)
            note = ""
            print_diagnostics(result)

        icon = {"PASS": "✅", "PARTIAL": "⚠️", "MISS": "❌"}.get(verdict, "•")
        extras = []
        if diag["expected_in_top_k"]:
            extras.append("expected✓in-top-k")
        if diag["bleed_video_ids"]:
            extras.append(f"BLEED={diag['bleed_video_ids']}")
        print(f"  → {icon} {verdict}   {'  '.join(extras)}")
        scores.append({
            "id": q["id"], "query": q["ticket"], "coverage": q["coverage"],
            "score": verdict, "note": note,
            "retrieved_video_ids": got,
            "expected_in_top_k": diag["expected_in_top_k"],
            "bleed_video_ids": diag["bleed_video_ids"],
        })

    _summarize(scores, queries, args)
    return 0


def _pct(n: int, d: int) -> float:
    return round(n / d * 100, 1) if d else 0.0


def compute_metrics(scores: list[dict]) -> dict:
    """Split results into three metrics that must not be conflated:

    1. answerable_retrieval — over queries whose corpus has coverage
       (full/partial): did the expected tutorial/step show up?
    2. no_answer_calibration — over uncovered (coverage=none) queries: did we
       correctly return no steps instead of surfacing something irrelevant?
    3. overall_support_success — strict PASS across all queries (the combined
       number; reported but never used alone, since no-answer wins inflate it).
    """
    counted = [s for s in scores if s["score"] in ("PASS", "PARTIAL", "MISS")]
    answerable = [s for s in counted if s.get("coverage") in ("full", "partial")]
    uncovered = [s for s in counted if s.get("coverage") == "none"]

    ans_pass = [s for s in answerable if s["score"] == "PASS"]
    ans_partial = [s for s in answerable if s["score"] == "PARTIAL"]
    na_correct = [s for s in uncovered if s["score"] == "PASS"]  # returned nothing
    overall_pass = [s for s in counted if s["score"] == "PASS"]

    return {
        "answerable_retrieval": {
            "total": len(answerable),
            "pass": len(ans_pass),
            "partial": len(ans_partial),
            "pass_rate": _pct(len(ans_pass), len(answerable)),
            "hit_rate": _pct(len(ans_pass) + len(ans_partial), len(answerable)),
        },
        "no_answer_calibration": {
            "total": len(uncovered),
            "correct": len(na_correct),
            "accuracy": _pct(len(na_correct), len(uncovered)),
        },
        "overall_support_success": {
            "total": len(counted),
            "success": len(overall_pass),
            "success_rate": _pct(len(overall_pass), len(counted)),
        },
        "errors": len([s for s in scores if s["score"] == "ERROR"]),
        "bleed_queries": len([s for s in counted if s.get("bleed_video_ids")]),
    }


def _summarize(scores: list[dict], queries: list[dict], args) -> None:
    print(f"\n{'=' * 64}\nRESULTS SUMMARY\n{'=' * 64}")
    m = compute_metrics(scores)
    ar, na, ov = (m["answerable_retrieval"], m["no_answer_calibration"],
                  m["overall_support_success"])

    print("\n  1. Answerable retrieval  (queries whose corpus has coverage)")
    print(f"     pass_rate: {ar['pass_rate']:.0f}%  "
          f"({ar['pass']}/{ar['total']} PASS, {ar['partial']} PARTIAL, "
          f"hit_rate {ar['hit_rate']:.0f}%)")
    print("\n  2. No-answer calibration  (uncovered queries returning no steps)")
    print(f"     accuracy:  {na['accuracy']:.0f}%  ({na['correct']}/{na['total']})")
    print("\n  3. Overall support success  (strict PASS across all queries)")
    print(f"     success:   {ov['success_rate']:.0f}%  ({ov['success']}/{ov['total']})")
    print(f"\n  Cross-corpus bleed: {m['bleed_queries']}/{ov['total']} queries")
    if m["errors"]:
        print(f"  💥 ERROR: {m['errors']}")
    print("\n  Headline metric = answerable retrieval pass_rate (conservative).")
    print(f"  {'🟢 TARGET MET' if ar['pass_rate'] >= 70 else '🔴 BELOW TARGET'}"
          "  (target: 70%)")

    misses = [s for s in scores if s["score"] == "MISS"]
    if misses:
        print("\n  Misses to investigate:")
        for s in misses:
            print(f"    {s['id']}  [{s.get('coverage')}]  {s.get('query','')}")

    out_path = BASE_DIR / f"eval_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps({"scores": scores, "metrics": m}, indent=2))
    print(f"\n  Results saved → {out_path.name}")


if __name__ == "__main__":
    sys.exit(main())
