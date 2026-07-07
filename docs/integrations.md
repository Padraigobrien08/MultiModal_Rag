# Integrations

Stepwise is built to plug into the tools your team already uses. There are two
kinds of integration, and it helps to keep them separate:

- **Surfaces** — *where answers show up.* A support agent should see the relevant
  step without leaving their helpdesk. Surfaces call the query API and render the
  result. Zendesk ships today; Intercom, Help Scout, and Slack are planned.
- **Sources** — *where content comes from.* These pull tutorials in and run them
  through the ingestion pipeline. YouTube, Google Drive, Notion, and image
  uploads ship today.

Both sides talk to the same backend API, so adding a new surface or a new source
is a small, well-defined change — see [Adding a source adapter](#adding-a-new-source-adapter).

```
  SOURCES  ──►  Ingestion pipeline  ──►  Index (ChromaDB + SQLite)  ──►  Query API  ──►  SURFACES
  YouTube                                                                             Zendesk
  Drive                                                                               Intercom  (planned)
  Notion                                                                              Slack     (planned)
  Images
```

---

## Surfaces

### Zendesk sidebar — *current*

The [`zendesk-app/`](../zendesk-app) directory is a Zendesk Apps Framework (ZAF)
app that renders in the **ticket sidebar**. It reads the active ticket's subject
and description, sends them to Stepwise, and shows the top matching steps with
timestamps. One click inserts a timestamped link into the reply composer.

**How it works**

1. On load, the iframe reads `ticket.subject` + `ticket.description` via the ZAF SDK.
2. It POSTs `{ query, top_k: 5 }` to `POST /query/sync` on your Stepwise backend.
3. It renders the `answer` summary and each returned step (`tutorial_title`,
   `text`, `timestamp_start`, and a deep link built from `video_id` / `source_url`).
4. **Insert link** appends a timestamped link via `ticket.comment.appendText`.

**Setup**

1. **Deploy the backend** somewhere Zendesk can reach it (the repo ships a
   `Dockerfile` and `railway.toml`; any public HTTPS host works). Note the URL.
2. **Package the app.** From `zendesk-app/`, zip the contents (or use
   [`zcli`](https://github.com/zendesk/zcli): `zcli apps:package`).
3. **Upload it** in Zendesk: *Admin Center → Apps and integrations → Zendesk
   Support apps → Upload private app.*
4. **Configure parameters** (defined in [`manifest.json`](../zendesk-app/manifest.json)):
   - `api_url` *(required)* — your backend URL, e.g. `https://your-stepwise-api.railway.app`
   - `api_key` *(optional, secure)* — sent as the `X-API-Key` header if set.
5. Open any ticket. The **Stepwise** panel appears in the sidebar and auto-runs a
   search against the ticket text. Use **Search again** to re-run after editing.

**Local development.** Serve the app with `zcli apps:server` from `zendesk-app/`
and append `?zcli_apps=true` to a Zendesk ticket URL to load your local build.

### Intercom / Help Scout — *planned*

The same surface contract applies: read the conversation text, call
`POST /query/sync`, render steps, and offer a one-click insert. Neither is built
yet; the intended adapter shape is:

- **Intercom** — a [Canvas Kit](https://developers.intercom.com/docs/canvas-kit)
  app in the Inbox. On `initialize`/`submit`, read the conversation, call
  `/query/sync`, and return a canvas of step cards. "Insert" writes a note or a
  reply draft.
- **Help Scout** — a [dynamic app (sidebar)](https://developer.helpscout.com/apps/)
  that receives the conversation on load, calls `/query/sync`, and renders steps
  as HTML in the sidebar.

Because both only need the query endpoint, a new surface is essentially: *fetch
the conversation text → `POST /query/sync` → render `answer` + `steps`.* No
backend changes required.

### Slack bot — *planned (concept)*

A Slack bot makes Stepwise useful outside the helpdesk — for internal support,
onboarding, and "how do I…" questions in team channels.

Concept:

- **Slash command** `/stepwise how do I issue a refund?` → call `/query/sync` →
  reply with the answer and step cards (Block Kit), each linking to the exact
  timestamp.
- **@mention** in a thread → treat the thread text as the query.
- **Bring your support videos** (below) pairs naturally: drop a Loom/YouTube link
  in a channel and a bot reaction queues it for ingestion.

This is a thin wrapper over the same two endpoints (`/query/sync` to answer,
`/ingest*` to queue content) plus Slack's Events/Slash-command API.

---

## Sources

All sources converge on one function, `run_ingestion_pipeline(...)` in
[`stepwise/ingestion/pipeline.py`](../stepwise/ingestion/pipeline.py), which runs
**align → structure → finalize → index**. An adapter's only job is to produce
the raw artifacts that pipeline consumes.

| Source | Module | API endpoint | Notes |
| --- | --- | --- | --- |
| **YouTube** | [`youtube.py`](../stepwise/ingestion/youtube.py) | `POST /ingest` | Captions via `youtube-transcript-api`, Whisper fallback; frames via `yt-dlp` + `ffmpeg`. |
| **Google Drive** | [`drive.py`](../stepwise/ingestion/drive.py) | `POST /ingest/drive` | Downloads video files, Whisper transcript, `ffmpeg` frames. Same artifact shape as YouTube. Loom share URLs handled as URL sources. |
| **Notion** | [`notion.py`](../stepwise/ingestion/notion.py) | `POST /ingest/notion` | Text-first: block-tree → markdown, no video/frames. Embedded YouTube/Loom links are surfaced so callers can queue them for full video ingestion. |
| **Images** | [`images.py`](../stepwise/ingestion/images.py) | `POST /ingest/images` | Screenshot sets or a ZIP (zip-bomb guarded). Frames only, no transcript. |

Auto-ingestion **watchers** (Drive folders, YouTube channels, Notion databases)
poll their source and queue new items automatically — see
[`watcher.py`](../stepwise/ingestion/watcher.py) and
[`scheduler.py`](../stepwise/ingestion/scheduler.py).

### "Bring your support videos" workflow

The fastest path from "we have a folder of screencasts" to "our agents can cite
them in tickets":

1. **Pick a source you already have.**
   - Screencasts in a **Google Drive** folder → connect the folder (OAuth) and
     let the watcher ingest everything.
   - Public tutorials on **YouTube** → paste URLs, or point a channel watcher at
     your uploads.
   - Written docs in **Notion** → ingest a page or a database; embedded
     Loom/YouTube links get picked up too.
   - One-off **screenshots** → drag a set (or a ZIP) into `POST /ingest/images`.

2. **Queue it.** Each source has an endpoint that returns a `job_id`
   (`202 Accepted`). Ingestion is idempotent — re-submitting an already-ingested
   URL returns the existing tutorial instead of duplicating it.

   ```bash
   # YouTube
   curl -X POST "$STEPWISE_API/ingest" \
     -H 'Content-Type: application/json' \
     -d '{"url": "https://youtu.be/VIDEO_ID"}'
   # → {"job_id": "…"}
   ```

3. **Watch the job.** Poll `GET /jobs/{job_id}` for `status`/`stage`
   (`aligning → structuring → indexing → complete`).

4. **Query it.** Ask a real support question and confirm you get the right step
   and timestamp:

   ```bash
   curl -X POST "$STEPWISE_API/query/sync" \
     -H 'Content-Type: application/json' \
     -d '{"query": "How do I issue a refund?", "top_k": 5}'
   # → {"answer": "…", "steps": [{tutorial_title, text, timestamp_start, video_id, …}]}
   ```

5. **Surface it** in Zendesk (above) so agents see it without leaving the ticket.

---

## Adding a new source adapter

Adding a source is three small pieces: an **adapter** that produces artifacts, a
**task** that runs the pipeline, and an **API endpoint** that queues the task.

**1. Write the adapter** in `stepwise/ingestion/<source>.py`. Return the artifact
shape the pipeline expects. For a video/audio source, mirror
[`ingest_youtube`](../stepwise/ingestion/youtube.py):

```python
def ingest_<source>(ref: str) -> dict:
    return {
        "video_id": "...",          # stable id for this item
        "title": "...",
        "url": "...",               # canonical source URL (used for idempotency)
        "transcript": [             # {text, start, duration} per segment
            {"text": "...", "start": 0.0, "duration": 3.2},
        ],
        "frames": [                 # {path, timestamp} — [] for text-only sources
            {"path": "/…/frame_0001.jpg", "timestamp": 0.0},
        ],
    }
```

For a **text-first** source (like Notion), skip transcript timing and frames and
build `Segment` objects yourself, then pass them to the pipeline via the
`segments=` argument — see how `notion.py` is wired in `tasks.py`.

**2. Add a task** in [`tasks.py`](../stepwise/ingestion/tasks.py) that calls the
shared pipeline with a distinct `source_type`:

```python
def run_<source>_ingestion(job_id: str, ref: str) -> None:
    artifacts = ingest_<source>(ref)
    run_ingestion_pipeline(
        source_url=artifacts["url"],
        title=artifacts["title"],
        source_type="<source>",     # shows up on results; keep it short + lowercase
        meta={...},
        transcript=artifacts["transcript"],
        frames=artifacts["frames"],
        tutorial_id=str(uuid.uuid4()),
        job_id=job_id,
    )
```

**3. Add an endpoint** in [`stepwise/api/app.py`](../stepwise/api/app.py),
following the existing `/ingest/*` handlers: check idempotency against
`source_url`, create a `JobDB` row, queue the task with `background_tasks`, and
return `{"job_id": ...}` with `202`.

**4. Export** the adapter from
[`stepwise/ingestion/__init__.py`](../stepwise/ingestion/__init__.py) and add a
test alongside the others in `tests/`.

That's it — retrieval, the Zendesk sidebar, and any future surface all work
against your new source with no further changes, because everything downstream
reads from the same index.

---

## See also

- [Architecture](architecture.md) — how ingestion, indexing, and retrieval fit together.
- [Roadmap](roadmap.md) — shipped vs. planned phases (Drive connector, Zendesk app, productisation).
- [Evaluation](evaluation.md) — the retrieval quality harness.
