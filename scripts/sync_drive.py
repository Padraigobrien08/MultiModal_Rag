#!/usr/bin/env python3
"""
Sync a Google Drive folder into Stepwise.

Scans the folder for video files, ingests any that haven't been indexed yet.
Already-indexed files are skipped via source_url idempotency.

Usage:
  python scripts/sync_drive.py --folder-id <id>
  python scripts/sync_drive.py --folder-id <id> --api http://localhost:8000
  python scripts/sync_drive.py --folder-id <id> --dry-run

Setup (first time only):
  python scripts/setup_drive_auth.py
"""
import argparse
import json
import sys
import time
from pathlib import Path
import urllib.request
import urllib.error

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

TOKEN_PATH       = Path("data/drive_token.json")
CREDENTIALS_PATH = Path("data/drive_credentials.json")


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read())


def poll_job(api: str, job_id: str, label: str) -> bool:
    dots = 0
    while True:
        try:
            data = get_json(f"{api}/jobs/{job_id}")
        except Exception as e:
            print(f"\n  poll error: {e}")
            return False

        status = data.get("status")
        stage  = data.get("stage") or ""
        done   = data.get("segments_done")
        total  = data.get("segments_total")

        progress = f" [{done}/{total} segs]" if stage == "structuring" and total else (f" [{stage}]" if stage else "")
        print(f"\r  {'.' * (dots % 4):<4} {status}{progress}   ", end="", flush=True)
        dots += 1

        if status == "done":
            steps = data.get("step_count", "?")
            print(f"\r  ✓ {label} — {steps} steps{' ' * 20}")
            return True
        elif status == "error":
            print(f"\r  ✗ {label} — {data.get('error', '')[:80]}{' ' * 20}")
            return False

        time.sleep(5)


def ingest_drive_source(api: str, source_url: str, title: str, label: str,
                         artifacts: dict, dry_run: bool) -> bool:
    """
    Posts ingestion artifacts directly to the API's internal pipeline.
    Since Drive files are local artifacts (not a fetchable URL), we use
    the /ingest endpoint with a drive:// URL for idempotency, then handle
    the actual ingestion via a dedicated endpoint.
    """
    # Check idempotency first
    try:
        tutorials = get_json(f"{api}/tutorials")
        for t in tutorials:
            if t.get("source_url") == source_url:
                print(f"  ↩ Already indexed ({t.get('step_count', '?')} steps)")
                return True
    except Exception:
        pass

    if dry_run:
        print(f"  [dry-run] Would ingest: {title}")
        return True

    # Use the /ingest/drive endpoint
    try:
        resp = post_json(f"{api}/ingest/drive", {
            "source_url": source_url,
            "title": title,
            "artifacts": artifacts,
        })
    except urllib.error.HTTPError as e:
        print(f"  ✗ HTTP {e.code}: {e.read().decode()[:100]}")
        return False
    except Exception as e:
        print(f"  ✗ {e}")
        return False

    job_id = resp.get("job_id")
    if not job_id:
        print(f"  ✗ No job_id: {resp}")
        return False

    print(f"  Job: {job_id[:8]}…")
    return poll_job(api, job_id, label)


def main():
    parser = argparse.ArgumentParser(description="Sync a Google Drive folder to Stepwise")
    parser.add_argument("--folder-id", required=True, help="Google Drive folder ID")
    parser.add_argument("--api", default="http://localhost:8000", help="Stepwise API base URL")
    parser.add_argument("--dry-run", action="store_true", help="List files without ingesting")
    parser.add_argument("--token", default=str(TOKEN_PATH), help="Path to drive_token.json")
    args = parser.parse_args()

    token_path = Path(args.token)
    if not token_path.exists():
        print(f"ERROR: Token not found at {token_path}")
        print("Run first:  python scripts/setup_drive_auth.py")
        sys.exit(1)

    try:
        from stepwise.ingestion.drive import list_drive_files, ingest_drive_file, ingest_loom_url, LOOM_DOMAIN
    except ImportError as e:
        print(f"ERROR: Missing dependency: {e}")
        print("Run:  pip install google-api-python-client google-auth-oauthlib")
        sys.exit(1)

    # Check API is reachable
    try:
        get_json(f"{args.api}/health")
    except Exception:
        print(f"ERROR: Cannot reach API at {args.api}")
        sys.exit(1)

    print("Stepwise Drive Sync")
    print(f"Folder: {args.folder_id}")
    print(f"API:    {args.api}")
    if args.dry_run:
        print("Mode:   DRY RUN (no ingestion)")
    print("=" * 50)

    # List files
    print("\nScanning Drive folder...")
    try:
        files = list_drive_files(args.folder_id, token_path)
    except Exception as e:
        print(f"ERROR: Failed to list Drive folder: {e}")
        sys.exit(1)

    if not files:
        print("No video files found in folder.")
        sys.exit(0)

    print(f"Found {len(files)} video file(s):\n")
    for f in files:
        size_mb = int(f.get("size", 0)) / 1024 / 1024
        print(f"  {f['name']:<50} {size_mb:.1f} MB")

    if args.dry_run:
        print("\nDry run complete — no files ingested.")
        return

    print()
    results = {"success": 0, "skipped": 0, "failed": 0}

    for i, file_meta in enumerate(files, 1):
        name = file_meta.get("name", "unknown")
        source_url = file_meta.get("webViewLink", f"drive://{file_meta['id']}")
        print(f"\n[{i}/{len(files)}] {name}")

        # Check idempotency
        try:
            tutorials = get_json(f"{args.api}/tutorials")
            already = next((t for t in tutorials if t.get("source_url") == source_url), None)
            if already:
                print(f"  ↩ Already indexed ({already.get('step_count', '?')} steps)")
                results["skipped"] += 1
                continue
        except Exception:
            pass

        # Ingest: download + transcribe + extract frames locally, then submit to API
        print("  Downloading and processing locally...")
        try:
            is_loom = LOOM_DOMAIN in source_url
            if is_loom:
                artifacts = ingest_loom_url(source_url)
            else:
                artifacts = ingest_drive_file(file_meta, token_path)
        except Exception as e:
            print(f"  ✗ Local processing failed: {e}")
            results["failed"] += 1
            continue

        # Submit to API
        try:
            resp = post_json(f"{args.api}/ingest/drive", {
                "source_url": source_url,
                "title": artifacts["title"],
                "video_id": artifacts["video_id"],
                "transcript": artifacts["transcript"],
                "frames": artifacts["frames"],
            })
        except urllib.error.HTTPError as e:
            print(f"  ✗ API error {e.code}: {e.read().decode()[:100]}")
            results["failed"] += 1
            continue
        except Exception as e:
            print(f"  ✗ {e}")
            results["failed"] += 1
            continue

        job_id = resp.get("job_id")
        if not job_id:
            print(f"  ✗ No job_id: {resp}")
            results["failed"] += 1
            continue

        print(f"  Job: {job_id[:8]}…")
        ok = poll_job(args.api, job_id, name[:40])
        if ok:
            results["success"] += 1
        else:
            results["failed"] += 1

    print(f"\n{'=' * 50}")
    print(f"✓ Ingested:  {results['success']}")
    print(f"↩ Skipped:   {results['skipped']}")
    print(f"✗ Failed:    {results['failed']}")

    if results["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
