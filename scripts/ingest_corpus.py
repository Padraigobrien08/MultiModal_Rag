#!/usr/bin/env python3
"""
Ingest the Stripe tutorial corpus into Stepwise.
Usage: python scripts/ingest_corpus.py [--api http://localhost:8000]
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def poll_job(api: str, job_id: str, label: str) -> bool:
    """Poll until job is done or error. Returns True on success."""
    dots = 0
    while True:
        try:
            data = get_json(f"{api}/jobs/{job_id}")
        except Exception as e:
            print(f"\n  ✗ Poll error: {e}")
            return False

        status = data.get("status")
        stage  = data.get("stage") or ""
        done   = data.get("segments_done")
        total  = data.get("segments_total")

        progress = ""
        if stage == "structuring" and total:
            progress = f" [{done}/{total} segments]"
        elif stage:
            progress = f" [{stage}]"

        print(f"\r  {'.' * (dots % 4):<4} {status}{progress}   ", end="", flush=True)
        dots += 1

        if status == "done":
            steps = data.get("step_count", "?")
            print(f"\r  ✓ Done — {steps} steps extracted{' ' * 20}")
            return True
        elif status == "error":
            print(f"\r  ✗ Error: {data.get('error')}{' ' * 20}")
            return False

        time.sleep(4)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument(
        "--sequential", action="store_true", help="Submit one at a time (avoids rate limits)"
    )
    parser.add_argument(
        "--library", default="local",
        help="Library/workspace id to ingest into (default: local)",
    )
    args = parser.parse_args()

    corpus_path = BASE_DIR / "stripe_corpus.json"
    corpus = json.loads(corpus_path.read_text())
    videos = corpus["videos"]

    print("Stepwise corpus ingestion")
    print(f"API: {args.api}")
    print(f"Library: {args.library}")
    print(f"Videos: {len(videos)}")
    print("=" * 50)

    results = {"success": [], "skipped": [], "failed": []}
    active_jobs = []  # list of (job_id, video)

    # ── Phase 1: fire all ingestion requests immediately ──────────────────────
    print("\nSubmitting all jobs...")
    for i, video in enumerate(videos, 1):
        url   = video["url"]
        topic = video["topic"]
        label = video.get("notes", url)

        print(f"  [{i:2d}/{len(videos)}] {topic}: {label[:55]}")
        try:
            resp = post_json(f"{args.api}/ingest", {"url": url, "library_id": args.library})
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"         ✗ HTTP {e.code}: {body[:80]}")
            results["failed"].append({"url": url, "error": f"HTTP {e.code}"})
            continue
        except Exception as e:
            print(f"         ✗ {e}")
            results["failed"].append({"url": url, "error": str(e)})
            continue

        if resp.get("existing"):
            tid   = resp.get("tutorial_id", "?")
            steps = resp.get("step_count", "?")
            print(f"         ↩ Already indexed ({steps} steps, {tid[:8]}…)")
            results["skipped"].append(url)
            continue

        job_id = resp.get("job_id")
        if not job_id:
            print("         ✗ No job_id in response")
            results["failed"].append({"url": url, "error": "no job_id"})
            continue

        print(f"         ✓ Queued  job={job_id[:8]}…")
        active_jobs.append((job_id, video))

        if args.sequential:
            # Wait for this job to finish before submitting the next
            ok = poll_job(args.api, job_id, video.get("notes", url))
            if ok:
                results["success"].append(url)
            else:
                results["failed"].append({"url": url, "error": "job failed"})
            active_jobs.clear()
            time.sleep(5)
        else:
            time.sleep(20)  # stagger starts to avoid simultaneous Claude API calls

    if not active_jobs:
        print("\nNothing to poll.")
    else:
        # ── Phase 2: poll all jobs concurrently until all finish ──────────────
        print(f"\nPolling {len(active_jobs)} jobs (updates every 5s)...\n")
        pending = {job_id: video for job_id, video in active_jobs}
        finished = {}

        while pending:
            time.sleep(5)
            still_pending = {}
            for job_id, video in pending.items():
                try:
                    data = get_json(f"{args.api}/jobs/{job_id}")
                except Exception:
                    still_pending[job_id] = video
                    continue

                status = data.get("status")
                stage  = data.get("stage") or ""
                done   = data.get("segments_done")
                total  = data.get("segments_total")
                label  = video.get("notes", "")[:40]

                if status == "done":
                    steps = data.get("step_count", "?")
                    print(f"  ✓ {label:<42} {steps} steps")
                    results["success"].append(video["url"])
                    finished[job_id] = data
                elif status == "error":
                    err = (data.get("error") or "")[:60]
                    print(f"  ✗ {label:<42} {err}")
                    results["failed"].append({"url": video["url"], "error": err})
                    finished[job_id] = data
                else:
                    # still running — keep in pending, print progress line
                    progress = ""
                    if stage == "structuring" and total:
                        progress = f"{done}/{total} segs"
                    elif stage:
                        progress = stage
                    print(f"  … {label:<42} {progress}")
                    still_pending[job_id] = video

            pending = still_pending
            if pending:
                print(f"  — {len(pending)} still running —")
                print()

    # Summary
    print("\n" + "=" * 50)
    print(f"✓ Ingested:  {len(results['success'])}")
    print(f"↩ Skipped:   {len(results['skipped'])} (already indexed)")
    print(f"✗ Failed:    {len(results['failed'])}")

    if results["failed"]:
        print("\nFailed URLs:")
        for f in results["failed"]:
            print(f"  {f['url']}  —  {f['error']}")

    if results["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
