# Roadmap

The maintained roadmap for Stepwise. The original design sketch is archived at
[`docs/archive/stepwise_to_zendesk_roadmap.html`](archive/stepwise_to_zendesk_roadmap.html);
this document supersedes it.

Status legend: ✅ shipped · 🚧 in progress · 🔭 planned.

## Phase 1 — Validate retrieval on real content ✅

Prove the retriever returns the right video and the right moment for real
support questions.

- Ingest tutorial videos via YouTube URLs or Drive downloads.
- Replay common support tickets as queries and score the results.
- Track where retrieval fails — wrong video, wrong segment, no result.

**Exit criteria:** ≥70% of test queries return a relevant step + timestamp.
Measured by the 25-query harness — see [evaluation.md](evaluation.md).

## Phase 2 — Google Drive connector ✅

Ingest from a Drive folder without manual steps.

- OAuth flow to connect a Drive folder.
- Watch the folder for new video files — download, transcribe, ingest through
  the existing pipeline.
- Reuse ingestion idempotency so re-scans skip already-ingested files.

**Exit criteria:** point it at a Drive folder and it ingests everything
automatically. Auto-ingestion watchers (Drive, YouTube channels, Notion
databases) ship in 0.1.0.

## Phase 3 — Zendesk sidebar app ✅

Surface relevant steps on the active support ticket.

- Zendesk Apps Framework (ZAF) sidebar reads the current ticket subject + body.
- Queries the backend and returns the top results with timestamps.
- One-click insert drops a timestamped link into the reply composer.
- Publicly deployable backend so the sidebar can reach it.

**Exit criteria:** an agent sees relevant video suggestions without leaving
Zendesk. The sidebar integration (`zendesk-app/`) ships in 0.1.0.

## Phase 4 — Productise for other teams 🔭

Turn the single-tenant tool into something another team can self-serve. Not
scoped for the current milestone.

- Auth + multi-tenancy — per-tenant namespacing in ChromaDB and SQLite.
- Onboarding flow — connect Drive, connect Zendesk, ingest, done.
- Billing — seat-based or usage-based.
- Zendesk Marketplace listing.

**Exit criteria:** a new team can sign up, connect their sources, and query
their own library within minutes.
