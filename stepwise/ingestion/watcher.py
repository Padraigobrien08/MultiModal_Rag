"""
Auto-ingestion watcher.

Polls each active WatcherDB entry for new content and enqueues ingestion jobs
for anything not yet in the tutorials table. Designed to be called on a schedule
(cron, APScheduler, or a manual /watchers/poll endpoint).

Supported source types:
  youtube_channel  — parses the channel's public RSS feed; no API key needed
  drive_folder     — uses the Drive API to list files modified after last_seen_at
  notion_page      — checks last_edited_time and re-ingests if changed
  notion_database  — queries the DB for pages modified after last_seen_at
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen
from xml.etree import ElementTree

from stepwise.models import WatcherDB

log = logging.getLogger(__name__)

_YT_RSS = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
_YT_VIDEO_URL = "https://www.youtube.com/watch?v={video_id}"
_YT_NS = "http://www.w3.org/2005/Atom"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Source-specific fetchers — return list of {id, url, title, modified_at}
# ---------------------------------------------------------------------------

def _fetch_youtube_channel(watcher: "WatcherDB") -> list[dict]:
    channel_id = watcher.source_id
    url = _YT_RSS.format(channel_id=channel_id)
    try:
        with urlopen(url, timeout=15) as resp:
            xml = resp.read()
    except Exception as e:
        log.warning("YouTube RSS fetch failed for %s: %s", channel_id, e)
        return []

    root = ElementTree.fromstring(xml)
    items = []
    for entry in root.findall(f"{{{_YT_NS}}}entry"):
        yt_ns = "http://www.youtube.com/xml/schemas/2015"
        vid_el = entry.find(f"{{{yt_ns}}}videoId")
        title_el = entry.find(f"{{{_YT_NS}}}title")
        published_el = entry.find(f"{{{_YT_NS}}}published")
        if vid_el is None:
            continue
        video_id = vid_el.text or ""
        items.append({
            "id": video_id,
            "url": _YT_VIDEO_URL.format(video_id=video_id),
            "title": title_el.text if title_el is not None else video_id,
            "modified_at": published_el.text if published_el is not None else "",
        })
    return items


def _fetch_drive_folder(watcher: "WatcherDB") -> list[dict]:
    from stepwise.config import settings
    from stepwise.ingestion.drive import list_drive_changes, list_drive_files
    cfg = watcher.config_json or {}
    token_path = Path(cfg.get("token_path") or str(settings.drive_token_path))
    recursive = cfg.get("recursive", False)

    if watcher.last_seen_at:
        files = list_drive_changes(watcher.source_id, token_path, watcher.last_seen_at, recursive)
    else:
        files = list_drive_files(watcher.source_id, token_path, recursive)

    return [
        {
            "id": f["id"],
            "url": f.get("webViewLink", f"drive://{f['id']}"),
            "title": Path(f.get("name", f["id"])).stem,
            "modified_at": f.get("modifiedTime", ""),
            "_drive_meta": f,
        }
        for f in files
    ]


def _fetch_notion_database(watcher: "WatcherDB") -> list[dict]:
    from stepwise.ingestion.notion import list_notion_database
    cfg = watcher.config_json or {}
    token = cfg["notion_token"]
    pages = list_notion_database(watcher.source_id, token, modified_after=watcher.last_seen_at)
    return [
        {
            "id": p["id"],
            "url": f"https://www.notion.so/{p['id'].replace('-', '')}",
            "title": p["title"],
            "modified_at": p["last_edited_time"],
        }
        for p in pages
    ]


def _fetch_notion_page(watcher: "WatcherDB") -> list[dict]:
    """Single Notion page — returns it if modified since last_seen_at."""
    from notion_client import Client
    cfg = watcher.config_json or {}
    token = cfg["notion_token"]
    client = Client(auth=token)
    page = client.pages.retrieve(page_id=watcher.source_id)
    last_edited = page.get("last_edited_time", "")
    if watcher.last_seen_at and last_edited <= watcher.last_seen_at:
        return []
    title = ""
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            from stepwise.ingestion.notion import _rich_text_to_str
            title = _rich_text_to_str(prop.get("title", []))
            break
    return [{
        "id": watcher.source_id,
        "url": f"https://www.notion.so/{watcher.source_id.replace('-', '')}",
        "title": title or watcher.source_id,
        "modified_at": last_edited,
    }]


_FETCHERS = {
    "youtube_channel": _fetch_youtube_channel,
    "drive_folder": _fetch_drive_folder,
    "notion_database": _fetch_notion_database,
    "notion_page": _fetch_notion_page,
}


# ---------------------------------------------------------------------------
# Core poll function
# ---------------------------------------------------------------------------

def poll_watcher(watcher: "WatcherDB", session, background_tasks) -> list[str]:
    """
    Check a single watcher for new content. Enqueues background ingestion jobs
    for items not already in the tutorials table. Returns list of new job IDs.
    """
    from stepwise.models import JobDB, TutorialDB

    fetcher = _FETCHERS.get(watcher.source_type)
    if not fetcher:
        log.warning("Unknown source_type: %s", watcher.source_type)
        return []

    items = fetcher(watcher)
    if not items:
        return []

    new_job_ids: list[str] = []
    latest_modified = watcher.last_seen_at or ""

    for item in items:
        # Skip already-ingested content (check by source URL)
        existing = session.query(TutorialDB).filter_by(source_url=item["url"]).first()
        if existing:
            continue

        job_id = str(uuid.uuid4())
        session.add(JobDB(id=job_id, status="pending"))

        # Dispatch the right background task per source type
        if watcher.source_type == "youtube_channel":
            from stepwise.ingestion.tasks import run_youtube_ingestion
            background_tasks.add_task(run_youtube_ingestion, job_id, item["url"], item["title"])

        elif watcher.source_type == "drive_folder":
            cfg = watcher.config_json or {}
            meta = item["_drive_meta"]
            from stepwise.ingestion.tasks import run_drive_ingestion_from_meta
            background_tasks.add_task(
                run_drive_ingestion_from_meta, job_id, meta, cfg["token_path"]
            )

        elif watcher.source_type in ("notion_database", "notion_page"):
            cfg = watcher.config_json or {}
            from stepwise.ingestion.tasks import run_notion_ingestion
            background_tasks.add_task(
                run_notion_ingestion, job_id, item["id"], item["title"], cfg["notion_token"]
            )

        new_job_ids.append(job_id)
        if item["modified_at"] > latest_modified:
            latest_modified = item["modified_at"]

    # Update watcher state
    watcher.last_seen_at = latest_modified or _now_iso()
    if new_job_ids:
        watcher.last_item_id = items[-1]["id"]

    return new_job_ids


# Drive/Notion ingestion tasks live in stepwise.ingestion.tasks (shared with API).
