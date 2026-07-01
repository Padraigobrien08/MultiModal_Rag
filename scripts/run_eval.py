#!/usr/bin/env python3
"""
Phase 1 retrieval eval runner for Stepwise.

Runs 25 simulated Stripe support queries, shows results, and asks you
to score each one. Outputs a summary report with pass rate.

Usage:
  python scripts/run_eval.py [--api http://localhost:8000] [--auto]

Uses POST /query/sync (JSON). The streaming endpoint is POST /query (SSE).

Flags:
  --auto      Skip interactive scoring, just dump all results (for quick inspection)
  --top-k 3   Number of steps to retrieve per query (default 3)
"""
import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent

SCORE_OPTIONS = {
    "1": ("PASS",    "✅", "Directly relevant — right video, right step"),
    "2": ("PARTIAL", "⚠️", "Vaguely related but not the best answer"),
    "3": ("MISS",    "❌", "Wrong topic entirely"),
    "s": ("SKIP",    "⏭", "Skip this query"),
}


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fmt_ts(s):
    if s is None:
        return ""
    m, sec = divmod(int(s), 60)
    return f"{m}:{sec:02d}"


def run_query(api: str, query: str, top_k: int) -> dict:
    return post_json(f"{api}/query/sync", {"query": query, "top_k": top_k})


def print_result(result: dict, query_text: str):
    print(f"\n  Answer: {result.get('answer', '(none)')[:200]}")
    steps = result.get("steps", [])
    if not steps:
        print("  Steps:  (none returned)")
        return
    print(f"  Steps ({len(steps)}):")
    for s in steps:
        ts = fmt_ts(s.get("timestamp_start"))
        ts_str = f" @ {ts}" if ts else ""
        text = s.get("text", "")[:120]
        print(f"    [{s.get('step_number', '?')}]{ts_str}  {text}")


def interactive_score(q: dict, result: dict) -> tuple[str, str]:
    """Show result, prompt for score. Returns (score_key, note)."""
    print_result(result, q["ticket"])
    print()
    for k, (label, icon, desc) in SCORE_OPTIONS.items():
        print(f"  [{k}] {icon} {label:8s} — {desc}")
    while True:
        raw = input("  Score: ").strip().lower()
        if raw in SCORE_OPTIONS:
            label, icon, _ = SCORE_OPTIONS[raw]
            note = ""
            if raw in ("2", "3"):
                note = input("  Note (optional): ").strip()
            return label, note
        print("  Enter 1, 2, 3, or s")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--auto", action="store_true", help="Dump results without scoring")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    queries_path = BASE_DIR / "eval_queries.json"
    queries = json.loads(queries_path.read_text())["queries"]

    print("Stepwise — Phase 1 Retrieval Eval")
    print(f"API: {args.api}  |  top_k={args.top_k}  |  queries={len(queries)}")
    print("=" * 60)

    if args.auto:
        print("AUTO mode — printing results only, no scoring\n")

    scores = []

    for i, q in enumerate(queries, 1):
        print(f"\n{'─' * 60}")
        print(f"[{i:02d}/{len(queries)}]  {q['id'].upper()}  [{q['topic']}]")
        print(f"  Query: \"{q['ticket']}\"")

        try:
            result = run_query(args.api, q["ticket"], args.top_k)
        except urllib.error.HTTPError as e:
            print(f"  ✗ HTTP {e.code}: {e.read().decode()[:100]}")
            scores.append({"id": q["id"], "query": q["ticket"], "topic": q["topic"],
                           "score": "ERROR", "note": f"HTTP {e.code}"})
            continue
        except Exception as e:
            print(f"  ✗ Error: {e}")
            scores.append({"id": q["id"], "query": q["ticket"], "topic": q["topic"],
                           "score": "ERROR", "note": str(e)})
            continue

        if args.auto:
            print_result(result, q["ticket"])
            scores.append({"id": q["id"], "query": q["ticket"], "topic": q["topic"],
                           "score": "UNSCORED", "note": ""})
        else:
            score, note = interactive_score(q, result)
            scores.append({"id": q["id"], "query": q["ticket"], "topic": q["topic"],
                           "score": score, "note": note})
            icon = SCORE_OPTIONS[[k for k,v in SCORE_OPTIONS.items() if v[0]==score][0]][1]
            print(f"  → {icon} {score}")

    # Summary
    print(f"\n{'=' * 60}")
    print("RESULTS SUMMARY")
    print(f"{'=' * 60}")

    counted = [s for s in scores if s["score"] not in ("SKIP", "UNSCORED", "ERROR")]
    passes  = [s for s in counted if s["score"] == "PASS"]
    partial = [s for s in counted if s["score"] == "PARTIAL"]
    misses  = [s for s in counted if s["score"] == "MISS"]
    errors  = [s for s in scores  if s["score"] == "ERROR"]

    if counted:
        pass_rate = len(passes) / len(counted) * 100
        hit_rate  = (len(passes) + len(partial)) / len(counted) * 100
        print(f"\n  ✅ PASS:    {len(passes):2d}  ({pass_rate:.0f}%)")
        print(f"  ⚠️  PARTIAL: {len(partial):2d}")
        print(f"  ❌ MISS:    {len(misses):2d}")
        if errors:
            print(f"  💥 ERROR:   {len(errors):2d}")
        print(f"\n  Pass rate:     {pass_rate:.0f}%")
        print(f"  Hit rate:      {hit_rate:.0f}%  (pass + partial)")
        print("  Target:        70% pass rate")
        print()
        if pass_rate >= 70:
            print("  🟢 PHASE 1 EXIT CRITERIA MET — ready to build on top")
        elif hit_rate >= 70:
            print("  🟡 HIT RATE OK but pass rate below 70% — review partials")
        else:
            print("  🔴 BELOW TARGET — fix embedding/chunking before Phase 2")

    # By topic breakdown
    if counted:
        topics = sorted(set(s["topic"] for s in counted))
        print("\n  By topic:")
        for topic in topics:
            t_scores = [s for s in counted if s["topic"] == topic]
            t_pass   = sum(1 for s in t_scores if s["score"] == "PASS")
            print(f"    {topic:20s}  {t_pass}/{len(t_scores)}")

    # Misses detail
    if misses:
        print("\n  Misses to investigate:")
        for s in misses:
            note = f"  — {s['note']}" if s["note"] else ""
            print(f"    {s['id']}  {s['query']}{note}")

    # Save results
    out_path = BASE_DIR / f"eval_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps({"scores": scores, "summary": {
        "total": len(queries),
        "counted": len(counted),
        "pass": len(passes),
        "partial": len(partial),
        "miss": len(misses),
        "error": len(errors),
        "pass_rate": round(len(passes) / len(counted) * 100, 1) if counted else 0,
        "hit_rate":  round((len(passes) + len(partial)) / len(counted) * 100, 1) if counted else 0,
    }}, indent=2))
    print(f"\n  Results saved → {out_path.name}")


if __name__ == "__main__":
    main()
