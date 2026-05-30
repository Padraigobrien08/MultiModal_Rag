"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  ArrowLeft, Plus, Trash2, RefreshCw, Loader2, CheckCircle2,
  AlertCircle, Clock, Rss, HardDrive, FileText, Database,
} from "lucide-react";

type Watcher = {
  id: string;
  source_type: string;
  source_id: string;
  label: string;
  last_seen_at: string | null;
  last_item_id: string | null;
  active: boolean;
  created_at: string | null;
};

type SourceType = "youtube_channel" | "drive_folder" | "notion_page" | "notion_database";

const SOURCE_LABELS: Record<SourceType, string> = {
  youtube_channel:  "YouTube Channel",
  drive_folder:     "Google Drive Folder",
  notion_page:      "Notion Page",
  notion_database:  "Notion Database",
};

const SOURCE_ICONS: Record<SourceType, React.ReactNode> = {
  youtube_channel:  <Rss className="h-3.5 w-3.5" />,
  drive_folder:     <HardDrive className="h-3.5 w-3.5" />,
  notion_page:      <FileText className="h-3.5 w-3.5" />,
  notion_database:  <Database className="h-3.5 w-3.5" />,
};

const SOURCE_ID_PLACEHOLDER: Record<SourceType, string> = {
  youtube_channel:  "Channel ID (e.g. UCxxxxxx…)",
  drive_folder:     "Folder URL or folder ID",
  notion_page:      "Page URL or page ID",
  notion_database:  "Database URL or database ID",
};

const SOURCE_ID_HINT: Record<SourceType, string> = {
  youtube_channel:  "Find it in the channel URL: youtube.com/channel/UC…",
  drive_folder:     "Copy from the Drive URL: drive.google.com/drive/folders/…",
  notion_page:      "The 32-char hex ID at the end of the page URL",
  notion_database:  "The 32-char hex ID at the end of the database URL",
};

function needsNotionToken(t: SourceType) {
  return t === "notion_page" || t === "notion_database";
}

function extractSourceId(raw: string, type: SourceType): string {
  const s = raw.trim();
  if (type === "drive_folder") {
    const m = s.match(/\/folders\/([a-zA-Z0-9_-]+)/);
    return m ? m[1] : s;
  }
  if (type === "youtube_channel") {
    const m = s.match(/\/channel\/([A-Za-z0-9_-]+)/);
    return m ? m[1] : s;
  }
  if (type === "notion_page" || type === "notion_database") {
    // Extract 32-char hex ID from URL or return as-is
    const hex = s.replace(/-/g, "");
    if (/^[0-9a-f]{32}$/i.test(hex)) return hex;
    const m = s.match(/([0-9a-f]{32})(?:[?#]|$)/i);
    return m ? m[1] : s;
  }
  return s;
}

function fmtDate(iso: string | null) {
  if (!iso) return "Never";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
}

function PollResult({ result }: { result: { jobs_queued: number } | null }) {
  if (!result) return null;
  return (
    <div className={`flex items-center gap-1.5 text-xs font-mono rounded-lg px-3 py-1.5 ${
      result.jobs_queued > 0
        ? "bg-primary/10 text-primary border border-primary/20"
        : "bg-white/[0.04] text-muted-foreground border border-border/60"
    }`}>
      {result.jobs_queued > 0
        ? <><CheckCircle2 className="h-3 w-3" />{result.jobs_queued} job{result.jobs_queued !== 1 ? "s" : ""} queued</>
        : <><Clock className="h-3 w-3" />Nothing new</>
      }
    </div>
  );
}

function WatcherCard({
  watcher,
  onDelete,
  onPoll,
}: {
  watcher: Watcher;
  onDelete: (id: string) => void;
  onPoll: (id: string) => Promise<{ jobs_queued: number }>;
}) {
  const [polling, setPolling] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [pollResult, setPollResult] = useState<{ jobs_queued: number } | null>(null);

  async function handlePoll() {
    setPolling(true);
    setPollResult(null);
    try {
      const result = await onPoll(watcher.id);
      setPollResult(result);
    } finally {
      setPolling(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    onDelete(watcher.id);
  }

  const icon = SOURCE_ICONS[watcher.source_type as SourceType] ?? <Rss className="h-3.5 w-3.5" />;
  const typeLabel = SOURCE_LABELS[watcher.source_type as SourceType] ?? watcher.source_type;

  return (
    <div className="rounded-xl border border-border/60 bg-card p-5 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-muted-foreground">{icon}</span>
            <span className="text-[11px] font-mono text-muted-foreground/60">{typeLabel}</span>
          </div>
          <p className="text-sm font-medium text-foreground truncate">{watcher.label}</p>
          <p className="text-[11px] font-mono text-muted-foreground/40 truncate mt-0.5">{watcher.source_id}</p>
        </div>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="h-7 w-7 rounded-lg flex items-center justify-center text-muted-foreground/40 hover:text-destructive hover:bg-destructive/10 transition-colors shrink-0"
          title="Remove watcher"
        >
          {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
        </button>
      </div>

      <div className="flex items-center justify-between gap-3 pt-1 border-t border-border/40">
        <div className="text-[11px] font-mono text-muted-foreground/50">
          Last checked: {fmtDate(watcher.last_seen_at)}
        </div>
        <div className="flex items-center gap-2">
          {pollResult && <PollResult result={pollResult} />}
          <button
            onClick={handlePoll}
            disabled={polling}
            className="flex items-center gap-1.5 h-7 px-3 rounded-lg border border-border/60 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-white/[0.06] disabled:opacity-40 transition-colors"
          >
            {polling ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
            Poll
          </button>
        </div>
      </div>
    </div>
  );
}

export default function WatchersPage() {
  const [watchers, setWatchers] = useState<Watcher[]>([]);
  const [loading, setLoading] = useState(true);
  const [pollingAll, setPollingAll] = useState(false);
  const [pollAllResult, setPollAllResult] = useState<{ jobs_queued: number } | null>(null);
  const [showForm, setShowForm] = useState(false);

  // Form state
  const [sourceType, setSourceType] = useState<SourceType>("youtube_channel");
  const [sourceId, setSourceId] = useState("");
  const [label, setLabel] = useState("");
  const [notionToken, setNotionToken] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const fetchWatchers = useCallback(async () => {
    try {
      const res = await fetch("/api/watchers");
      if (res.ok) setWatchers(await res.json());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchWatchers(); }, [fetchWatchers]);

  async function handlePollAll() {
    setPollingAll(true);
    setPollAllResult(null);
    try {
      const res = await fetch("/api/watchers/poll", { method: "POST" });
      if (res.ok) setPollAllResult(await res.json());
    } finally {
      setPollingAll(false);
      fetchWatchers();
    }
  }

  async function handlePollOne(id: string) {
    const res = await fetch(`/api/watchers/${id}/poll`, { method: "POST" });
    const result = res.ok ? await res.json() : { jobs_queued: 0 };
    fetchWatchers();
    return result;
  }

  async function handleDelete(id: string) {
    await fetch(`/api/watchers/${id}`, { method: "DELETE" });
    setWatchers(prev => prev.filter(w => w.id !== id));
  }

  async function handleSubmit() {
    if (!sourceId.trim()) return;
    setSubmitting(true);
    setFormError(null);
    try {
      const config: Record<string, string> = {};
      if (needsNotionToken(sourceType) && notionToken.trim()) {
        config.notion_token = notionToken.trim();
      }

      const res = await fetch("/api/watchers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_type: sourceType,
          source_id: extractSourceId(sourceId, sourceType),
          label: label.trim() || extractSourceId(sourceId, sourceType),
          config,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail ?? "Failed to create watcher");
      }

      setSourceId(""); setLabel(""); setNotionToken(""); setShowForm(false);
      fetchWatchers();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed");
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit = sourceId.trim().length > 0 &&
    (!needsNotionToken(sourceType) || notionToken.trim().length > 0);

  return (
    <div className="max-w-4xl mx-auto px-6 py-14">
      {/* Header */}
      <div className="flex items-start justify-between mb-10">
        <div className="animate-fade-up">
          <Link href="/tutorials" className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground mb-4 transition-colors">
            <ArrowLeft className="h-3 w-3" />
            Library
          </Link>
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-primary/20 bg-primary/5 mb-4 ml-4">
            <Rss className="h-3 w-3 text-primary" />
            <span className="text-xs font-mono text-primary font-medium">Auto-Ingest</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight text-foreground mb-2">
            Watched Sources
          </h1>
          <p className="text-muted-foreground text-sm">
            New content is detected automatically. Hit Poll to check now, or set up a cron job on{" "}
            <code className="text-xs bg-white/[0.06] px-1.5 py-0.5 rounded font-mono">POST /api/watchers/poll</code>.
          </p>
        </div>

        <div className="flex items-center gap-2 mt-8">
          {pollAllResult && <PollResult result={pollAllResult} />}
          {watchers.length > 0 && (
            <button
              onClick={handlePollAll}
              disabled={pollingAll}
              className="flex items-center gap-1.5 h-9 px-4 rounded-lg border border-border bg-card text-sm font-medium text-foreground hover:bg-white/[0.06] disabled:opacity-40 transition-all shrink-0"
            >
              {pollingAll ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              Poll All
            </button>
          )}
          <button
            onClick={() => { setShowForm(v => !v); setFormError(null); }}
            className="flex items-center gap-1.5 h-9 px-4 rounded-lg bg-primary text-black text-sm font-semibold hover:bg-primary/90 transition-colors shrink-0"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Source
          </button>
        </div>
      </div>

      {/* Add source form */}
      {showForm && (
        <div className="mb-8 rounded-xl border border-border/60 bg-card p-6 space-y-4 animate-fade-up">
          <h2 className="text-sm font-semibold text-foreground">New Watched Source</h2>

          {/* Source type */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {(Object.keys(SOURCE_LABELS) as SourceType[]).map(t => (
              <button
                key={t}
                onClick={() => { setSourceType(t); setSourceId(""); }}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-medium transition-colors ${
                  sourceType === t
                    ? "border-primary/40 bg-primary/10 text-primary"
                    : "border-border/60 text-muted-foreground hover:border-border hover:text-foreground"
                }`}
              >
                {SOURCE_ICONS[t]}
                {SOURCE_LABELS[t]}
              </button>
            ))}
          </div>

          {/* Fields */}
          <div className="space-y-3">
            <div>
              <input
                type="text"
                placeholder={SOURCE_ID_PLACEHOLDER[sourceType]}
                value={sourceId}
                onChange={e => setSourceId(e.target.value)}
                className="w-full bg-background border border-border/60 rounded-lg px-3.5 py-2.5 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 text-foreground placeholder:text-muted-foreground/40"
              />
              <p className="text-[11px] text-muted-foreground/50 mt-1.5 pl-0.5">{SOURCE_ID_HINT[sourceType]}</p>
            </div>

            <input
              type="text"
              placeholder="Label (optional)"
              value={label}
              onChange={e => setLabel(e.target.value)}
              className="w-full bg-background border border-border/60 rounded-lg px-3.5 py-2.5 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 text-foreground placeholder:text-muted-foreground/40"
            />

            {needsNotionToken(sourceType) && (
              <div>
                <input
                  type="password"
                  placeholder="Notion integration token (secret_…)"
                  value={notionToken}
                  onChange={e => setNotionToken(e.target.value)}
                  className="w-full bg-background border border-border/60 rounded-lg px-3.5 py-2.5 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 text-foreground placeholder:text-muted-foreground/40"
                />
                <p className="text-[11px] text-muted-foreground/50 mt-1.5 pl-0.5">
                  Create at notion.so/my-integrations and share your page/database with it.
                </p>
              </div>
            )}
          </div>

          {formError && (
            <div className="flex items-center gap-2 text-xs text-destructive">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" />
              {formError}
            </div>
          )}

          <div className="flex gap-2 pt-1">
            <button
              onClick={() => { setShowForm(false); setFormError(null); }}
              className="flex-1 py-2 text-sm border border-border/60 rounded-lg hover:bg-white/[0.04] text-muted-foreground transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={!canSubmit || submitting}
              className="flex-1 py-2 text-sm bg-primary text-black font-semibold rounded-lg hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
            >
              {submitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Watch Source
            </button>
          </div>
        </div>
      )}

      {/* Watcher list */}
      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-8">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      ) : watchers.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border/60 p-20 text-center">
          <div className="h-12 w-12 rounded-xl bg-white/[0.04] border border-border/60 flex items-center justify-center mx-auto mb-4">
            <Rss className="h-5 w-5 text-muted-foreground" />
          </div>
          <p className="text-sm text-muted-foreground mb-4">No watched sources yet.</p>
          <button
            onClick={() => setShowForm(true)}
            className="inline-flex items-center gap-1.5 h-9 px-4 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            Add your first source
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {watchers.map(w => (
            <WatcherCard
              key={w.id}
              watcher={w}
              onDelete={handleDelete}
              onPoll={handlePollOne}
            />
          ))}
        </div>
      )}

      {/* Link to active jobs */}
      {watchers.length > 0 && (
        <p className="text-xs text-muted-foreground/50 text-center mt-10">
          Queued ingestion jobs appear on the{" "}
          <Link href="/tutorials" className="text-primary hover:underline">Library</Link> page.
        </p>
      )}
    </div>
  );
}
