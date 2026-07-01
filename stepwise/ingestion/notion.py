"""
Notion ingestion module — comprehensive block-to-markdown conversion.

Supports a Notion page or a Notion database (collection of pages).
Pages are text-first: no video download, no Whisper, no frames.

Block types handled:
  heading_1/2/3, paragraph, bulleted/numbered list, to_do, toggle,
  quote, callout (with emoji icon), code (with language), divider,
  table, bookmark, embed, video, image, file, equation,
  column_list/column, synced_block, child_page.

Embedded YouTube/Loom videos are extracted and returned separately
so callers can decide whether to queue them for full video ingestion.
"""
from __future__ import annotations

import re


def _get_client(token: str):
    from notion_client import Client
    return Client(auth=token)


def _rich_text_to_str(rich_text: list[dict]) -> str:
    return "".join(rt.get("plain_text", "") for rt in rich_text)


# ---------------------------------------------------------------------------
# Block fetch — keeps the tree so tables/columns can reconstruct correctly
# ---------------------------------------------------------------------------

def _fetch_children(client, block_id: str) -> list[dict]:
    """
    Fetch direct children of a block and recursively populate their children
    as a '_children' key. Returns the block tree (not a flat list).
    """
    blocks: list[dict] = []
    cursor = None
    while True:
        resp = client.blocks.children.list(
            block_id=block_id, start_cursor=cursor, page_size=100
        )
        for block in resp["results"]:
            block["_children"] = (
                _fetch_children(client, block["id"])
                if block.get("has_children")
                else []
            )
            blocks.append(block)
        cursor = resp.get("next_cursor")
        if not cursor:
            break
    return blocks


# ---------------------------------------------------------------------------
# Block → Markdown
# ---------------------------------------------------------------------------

def _block_to_markdown(block: dict, depth: int = 0) -> str:
    """Convert one block (and its children) to a Markdown string."""
    btype = block["type"]
    content = block.get(btype, {})
    children = block.get("_children", [])
    indent = "  " * depth

    def child_md(d: int = depth + 1) -> str:
        s = _blocks_to_markdown(children, d)
        return ("\n" + s) if s else ""

    if btype == "heading_1":
        return "# " + _rich_text_to_str(content.get("rich_text", []))
    if btype == "heading_2":
        return "## " + _rich_text_to_str(content.get("rich_text", []))
    if btype == "heading_3":
        return "### " + _rich_text_to_str(content.get("rich_text", []))

    if btype == "paragraph":
        text = _rich_text_to_str(content.get("rich_text", []))
        return (indent + text + child_md()) if text else child_md().lstrip("\n")

    if btype == "bulleted_list_item":
        text = _rich_text_to_str(content.get("rich_text", []))
        return f"{indent}- {text}{child_md()}"

    if btype == "numbered_list_item":
        text = _rich_text_to_str(content.get("rich_text", []))
        return f"{indent}1. {text}{child_md()}"

    if btype == "to_do":
        checked = content.get("checked", False)
        text = _rich_text_to_str(content.get("rich_text", []))
        return f"{indent}{'[x]' if checked else '[ ]'} {text}{child_md()}"

    if btype == "toggle":
        text = _rich_text_to_str(content.get("rich_text", []))
        return f"{indent}▶ {text}{child_md()}"

    if btype == "quote":
        text = _rich_text_to_str(content.get("rich_text", []))
        inner = (text + child_md()).strip().splitlines()
        return "\n".join(f"> {line}" for line in inner if line)

    if btype == "callout":
        icon_data = content.get("icon", {})
        icon = (icon_data["emoji"] + " ") if icon_data.get("type") == "emoji" else ""
        text = _rich_text_to_str(content.get("rich_text", []))
        inner = (icon + text + child_md()).strip().splitlines()
        return "\n".join(f"> {line}" for line in inner if line)

    if btype == "code":
        lang = content.get("language", "")
        code = _rich_text_to_str(content.get("rich_text", []))
        caption = _rich_text_to_str(content.get("caption", []))
        result = f"```{lang}\n{code}\n```"
        return result + (f"\n_{caption}_" if caption else "")

    if btype == "divider":
        return "---"

    if btype == "table":
        rows = [
            row["table_row"].get("cells", [])
            for row in children
            if row["type"] == "table_row"
        ]
        if not rows:
            return ""
        md_rows = ["| " + " | ".join(_rich_text_to_str(c) for c in row) + " |"
                   for row in rows]
        if len(md_rows) > 1:
            sep = "| " + " | ".join(["---"] * len(rows[0])) + " |"
            md_rows.insert(1, sep)
        return "\n".join(md_rows)

    if btype == "table_row":
        # Rendered by parent table block; skip standalone
        return ""

    if btype in ("column_list", "column"):
        # Transparent layout containers — render children inline
        return child_md(depth).lstrip("\n")

    if btype == "synced_block":
        # Original block: has children. Synced copy: points to original via
        # synced_from, but Notion API returns children for both — just render them.
        return child_md(depth).lstrip("\n")

    if btype == "bookmark":
        url = content.get("url", "")
        caption = _rich_text_to_str(content.get("caption", []))
        return f"[{caption or url}]({url})" if url else ""

    if btype == "embed":
        url = content.get("url", "")
        caption = _rich_text_to_str(content.get("caption", []))
        return f"[Embed: {caption or url}]({url})" if url else ""

    if btype in ("image", "video", "file", "pdf"):
        src = content.get("file") or content.get("external") or {}
        url = src.get("url", "")
        caption = _rich_text_to_str(content.get("caption", []))
        if not url:
            return ""
        return f"[{caption or btype}]({url})"

    if btype == "equation":
        expr = content.get("expression", "")
        return f"$${expr}$$" if expr else ""

    if btype == "child_page":
        return f"[Sub-page: {content.get('title', '')}]"

    if btype == "child_database":
        return f"[Database: {content.get('title', '')}]"

    if btype in ("table_of_contents", "breadcrumb", "template", "link_preview"):
        return ""

    # Unknown block: try to salvage any rich_text
    rich_text = content.get("rich_text", [])
    return (indent + _rich_text_to_str(rich_text)) if rich_text else ""


def _blocks_to_markdown(blocks: list[dict], depth: int = 0) -> str:
    parts = [_block_to_markdown(b, depth) for b in blocks]
    return "\n\n".join(p for p in parts if p.strip())


# ---------------------------------------------------------------------------
# Video URL extraction
# ---------------------------------------------------------------------------

_VIDEO_DOMAINS = ("youtube.com", "youtu.be", "loom.com")


def _extract_video_urls(blocks: list[dict]) -> list[str]:
    """
    Recursively find YouTube/Loom URLs in video, embed, and bookmark blocks.
    These can be queued for full video ingestion by the caller.
    """
    urls: list[str] = []
    for block in blocks:
        btype = block["type"]
        content = block.get(btype, {})
        url = ""
        if btype == "video":
            src = content.get("file") or content.get("external") or {}
            url = src.get("url", "")
        elif btype in ("bookmark", "embed"):
            url = content.get("url", "")
        if url and any(d in url for d in _VIDEO_DOMAINS):
            urls.append(url)
        urls.extend(_extract_video_urls(block.get("_children", [])))
    return urls


# ---------------------------------------------------------------------------
# Markdown → transcript entries for align_segments
# ---------------------------------------------------------------------------

def _markdown_to_transcript(markdown: str) -> list[dict]:
    """
    Split Markdown into transcript-style entries that align_segments can chunk.

    Splits at heading boundaries and dividers. Each section becomes one entry
    with a synthetic 60 s timestamp, giving align_segments enough granularity
    to group by word count regardless of page length.
    """
    # Split at lines that start a heading or are a divider
    parts = re.split(r"(?m)^(?=#{1,3} )|^---$", markdown)
    entries: list[dict] = []
    t = 0.0
    for part in parts:
        text = part.strip()
        if not text or text == "---":
            continue
        entries.append({"text": text, "start": t, "duration": 60.0})
        t += 60.0
    return entries


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_notion_page(page_id: str, token: str) -> dict:
    """
    Ingest a single Notion page.

    Returns the standard artifact dict (same shape as ingest_youtube) plus
    'embedded_video_urls': list of YouTube/Loom URLs found in the page that
    the caller may want to queue for full video ingestion.
    """
    client = _get_client(token)
    page_meta = client.pages.retrieve(page_id=page_id)

    title = ""
    for prop in page_meta.get("properties", {}).values():
        if prop.get("type") == "title":
            title = _rich_text_to_str(prop.get("title", []))
            break
    if not title:
        title = page_id

    blocks = _fetch_children(client, page_id)
    markdown = _blocks_to_markdown(blocks)
    transcript = _markdown_to_transcript(markdown)
    video_urls = _extract_video_urls(blocks)

    return {
        "video_id": page_id,
        "title": title,
        "url": f"https://www.notion.so/{page_id.replace('-', '')}",
        "transcript": transcript,
        "frames": [],
        "source_type": "notion",
        "embedded_video_urls": video_urls,
    }


def list_notion_database(
    database_id: str, token: str, modified_after: str | None = None
) -> list[dict]:
    """
    List pages in a Notion database, optionally filtered by last_edited_time.
    Returns list of {id, title, last_edited_time}.
    """
    client = _get_client(token)
    filter_arg: dict = {}
    if modified_after:
        filter_arg = {
            "filter": {
                "timestamp": "last_edited_time",
                "last_edited_time": {"after": modified_after},
            }
        }

    pages: list[dict] = []
    cursor = None
    while True:
        resp = client.databases.query(
            database_id=database_id,
            start_cursor=cursor,
            page_size=100,
            **filter_arg,
        )
        for page in resp["results"]:
            title = ""
            for prop in page.get("properties", {}).values():
                if prop.get("type") == "title":
                    title = _rich_text_to_str(prop.get("title", []))
                    break
            pages.append({
                "id": page["id"],
                "title": title or page["id"],
                "last_edited_time": page.get("last_edited_time", ""),
            })
        cursor = resp.get("next_cursor")
        if not cursor:
            break

    return pages
