"use client";

import { useState, useRef } from "react";
import { X, ImageIcon, Loader2, CheckCircle, AlertCircle } from "lucide-react";

type JobState = {
  id: string;
  status: "pending" | "running" | "done" | "error";
  stage: string | null;
  segments_done: number | null;
  segments_total: number | null;
  step_count: number | null;
  error: string | null;
};

type Tab = "youtube" | "images" | "notion";

const STAGES = ["downloading", "aligning", "structuring", "consolidating", "indexing"];

function parseNotionId(input: string): string {
  const stripped = input.replace(/-/g, "").trim();
  if (/^[0-9a-f]{32}$/i.test(stripped)) return stripped;
  const match = input.match(/([0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12})/i);
  if (match) return match[1].replace(/-/g, "");
  // Try to extract from the end of a Notion URL: /SomePage-<32hexchars>
  const urlMatch = input.match(/[0-9a-f]{32}(?:[?#]|$)/i);
  if (urlMatch) return urlMatch[0].replace(/[?#]$/, "");
  return input.trim();
}

export function IngestModal({ onClose, libraryId }: { onClose: () => void; libraryId: string }) {
  const [tab, setTab] = useState<Tab>("youtube");
  // YouTube
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  // Images
  const [files, setFiles] = useState<FileList | null>(null);
  const [imageTitle, setImageTitle] = useState("");
  // Notion
  const [notionUrl, setNotionUrl] = useState("");
  const [notionToken, setNotionToken] = useState("");
  const [notionTitle, setNotionTitle] = useState("");

  const [loading, setLoading] = useState(false);
  const [job, setJob] = useState<JobState | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function stopPoll() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }

  function pollJob(jobId: string) {
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        const data = await res.json();
        const state: JobState = {
          id: jobId, status: data.status, stage: data.stage,
          segments_done: data.segments_done, segments_total: data.segments_total,
          step_count: data.step_count, error: data.error,
        };
        setJob(state);
        if (data.status === "done" || data.status === "error") { stopPoll(); setLoading(false); }
      } catch {}
    }, 2000);
  }

  async function submitYouTube() {
    if (!url.trim()) return;
    setLoading(true);
    try {
      const res = await fetch("/api/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim(), title: title.trim() || undefined, library_id: libraryId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Failed");
      if (data.existing) {
        setJob({ id: "", status: "done", stage: null, segments_done: null, segments_total: null, step_count: data.step_count, error: null });
        setLoading(false);
      } else {
        setJob({ id: data.job_id, status: "pending", stage: null, segments_done: null, segments_total: null, step_count: null, error: null });
        pollJob(data.job_id);
      }
    } catch (err) {
      setJob({ id: "", status: "error", stage: null, segments_done: null, segments_total: null, step_count: null, error: err instanceof Error ? err.message : "Failed" });
      setLoading(false);
    }
  }

  async function submitImages() {
    if (!files?.length || !imageTitle.trim()) return;
    setLoading(true);
    const form = new FormData();
    form.append("title", imageTitle.trim());
    form.append("library_id", libraryId);
    for (const f of Array.from(files)) form.append("files", f);
    try {
      const res = await fetch("/api/ingest/images", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Failed");
      setJob({ id: data.job_id, status: "pending", stage: null, segments_done: null, segments_total: null, step_count: null, error: null });
      pollJob(data.job_id);
    } catch (err) {
      setJob({ id: "", status: "error", stage: null, segments_done: null, segments_total: null, step_count: null, error: err instanceof Error ? err.message : "Failed" });
      setLoading(false);
    }
  }

  async function submitNotion() {
    if (!notionUrl.trim() || !notionToken.trim()) return;
    setLoading(true);
    try {
      const pageId = parseNotionId(notionUrl.trim());
      const res = await fetch("/api/ingest/notion", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          page_id: pageId,
          notion_token: notionToken.trim(),
          title: notionTitle.trim() || undefined,
          library_id: libraryId,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Failed");
      if (data.existing) {
        setJob({ id: "", status: "done", stage: null, segments_done: null, segments_total: null, step_count: data.step_count, error: null });
        setLoading(false);
      } else {
        setJob({ id: data.job_id, status: "pending", stage: null, segments_done: null, segments_total: null, step_count: null, error: null });
        pollJob(data.job_id);
      }
    } catch (err) {
      setJob({ id: "", status: "error", stage: null, segments_done: null, segments_total: null, step_count: null, error: err instanceof Error ? err.message : "Failed" });
      setLoading(false);
    }
  }

  function reset() {
    stopPoll(); setJob(null); setUrl(""); setTitle(""); setFiles(null);
    setImageTitle(""); setNotionUrl(""); setNotionToken(""); setNotionTitle("");
    setLoading(false);
    if (fileRef.current) fileRef.current.value = "";
  }

  const stageIdx = job?.stage ? STAGES.indexOf(job.stage) : -1;
  const notionReady = notionUrl.trim().length > 0 && notionToken.trim().length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-card border border-border rounded-2xl w-full max-w-md mx-4 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border/60">
          <span className="font-semibold text-foreground">Add to Library</span>
          <button onClick={() => { stopPoll(); onClose(); }}
            className="h-7 w-7 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-white/[0.06] hover:text-foreground transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-6">
          {!job ? (
            <>
              {/* Tabs */}
              <div className="flex gap-1 p-1 bg-white/[0.04] rounded-lg mb-5">
                {(["youtube", "images", "notion"] as const).map(t => (
                  <button key={t} onClick={() => setTab(t)}
                    className={`flex-1 py-1.5 text-sm rounded-md font-medium transition-colors ${
                      tab === t ? "bg-white/[0.08] text-foreground" : "text-muted-foreground hover:text-foreground"
                    }`}>
                    {t === "youtube" ? "YouTube" : t === "images" ? "Screenshots" : "Notion"}
                  </button>
                ))}
              </div>

              {tab === "youtube" && (
                <div className="space-y-3">
                  <input type="url" placeholder="https://youtube.com/watch?v=…" value={url}
                    onChange={e => setUrl(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && submitYouTube()}
                    className="w-full bg-background border border-border/60 rounded-lg px-3.5 py-2.5 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 text-foreground placeholder:text-muted-foreground/40" />
                  <input type="text" placeholder="Title (optional)" value={title}
                    onChange={e => setTitle(e.target.value)}
                    className="w-full bg-background border border-border/60 rounded-lg px-3.5 py-2.5 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 text-foreground placeholder:text-muted-foreground/40" />
                  <button onClick={submitYouTube} disabled={!url.trim() || loading}
                    className="w-full py-2.5 bg-primary text-black text-sm font-semibold rounded-lg hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2">
                    {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    Ingest Tutorial
                  </button>
                </div>
              )}

              {tab === "images" && (
                <div className="space-y-3">
                  <input type="text" placeholder="Title (required)" value={imageTitle}
                    onChange={e => setImageTitle(e.target.value)}
                    className="w-full bg-background border border-border/60 rounded-lg px-3.5 py-2.5 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 text-foreground placeholder:text-muted-foreground/40" />
                  <div onClick={() => fileRef.current?.click()}
                    className="w-full border-2 border-dashed border-border/60 rounded-lg px-4 py-8 text-center cursor-pointer hover:border-primary/40 transition-colors">
                    <ImageIcon className="h-6 w-6 text-muted-foreground/30 mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">
                      {files ? `${files.length} file${files.length > 1 ? "s" : ""} selected` : "Click to select screenshots"}
                    </p>
                    <input ref={fileRef} type="file" accept="image/*" multiple className="hidden"
                      onChange={e => setFiles(e.target.files)} />
                  </div>
                  <button onClick={submitImages} disabled={!files?.length || !imageTitle.trim() || loading}
                    className="w-full py-2.5 bg-primary text-black text-sm font-semibold rounded-lg hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2">
                    {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    Ingest Screenshots
                  </button>
                </div>
              )}

              {tab === "notion" && (
                <div className="space-y-3">
                  <input type="text" placeholder="Notion page URL or page ID" value={notionUrl}
                    onChange={e => setNotionUrl(e.target.value)}
                    className="w-full bg-background border border-border/60 rounded-lg px-3.5 py-2.5 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 text-foreground placeholder:text-muted-foreground/40" />
                  <input type="password" placeholder="Notion integration token (secret_…)" value={notionToken}
                    onChange={e => setNotionToken(e.target.value)}
                    className="w-full bg-background border border-border/60 rounded-lg px-3.5 py-2.5 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 text-foreground placeholder:text-muted-foreground/40" />
                  <input type="text" placeholder="Title (optional)" value={notionTitle}
                    onChange={e => setNotionTitle(e.target.value)}
                    className="w-full bg-background border border-border/60 rounded-lg px-3.5 py-2.5 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 text-foreground placeholder:text-muted-foreground/40" />
                  <p className="text-[11px] text-muted-foreground/50 leading-relaxed">
                    Create an integration at notion.so/my-integrations and share the page with it.
                  </p>
                  <button onClick={submitNotion} disabled={!notionReady || loading}
                    className="w-full py-2.5 bg-primary text-black text-sm font-semibold rounded-lg hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2">
                    {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    Ingest Notion Page
                  </button>
                </div>
              )}
            </>
          ) : job.status === "error" ? (
            <div className="text-center py-4">
              <AlertCircle className="h-8 w-8 text-destructive mx-auto mb-3" />
              <p className="text-sm text-foreground mb-1">Ingestion failed</p>
              <p className="text-xs text-muted-foreground mb-4 max-w-xs mx-auto">{job.error}</p>
              <button onClick={reset} className="text-sm text-primary hover:underline">Try again</button>
            </div>
          ) : job.status === "done" ? (
            <div className="text-center py-4">
              <CheckCircle className="h-8 w-8 text-primary mx-auto mb-3" />
              <p className="text-sm text-foreground mb-1">Added to library</p>
              {job.step_count && <p className="text-xs text-muted-foreground mb-5">{job.step_count} steps extracted</p>}
              <div className="flex gap-2">
                <button onClick={reset} className="flex-1 py-2 text-sm border border-border/60 rounded-lg hover:bg-white/[0.04] text-muted-foreground transition-colors">
                  Add another
                </button>
                <button onClick={() => { stopPoll(); onClose(); }} className="flex-1 py-2 text-sm bg-primary text-black font-medium rounded-lg hover:bg-primary/90 transition-colors">
                  Done
                </button>
              </div>
            </div>
          ) : (
            <div className="py-2">
              <div className="flex items-center gap-2 mb-6">
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
                <span className="text-sm text-muted-foreground capitalize">
                  {job.stage === "structuring" && job.segments_total
                    ? `Structuring… ${job.segments_done ?? 0}/${job.segments_total} segments`
                    : job.stage || "Processing…"}
                </span>
              </div>
              <div className="space-y-2.5">
                {STAGES.map((s, i) => (
                  <div key={s} className="flex items-center gap-2.5">
                    <div className={`h-1.5 w-1.5 rounded-full transition-colors ${
                      i < stageIdx ? "bg-primary" : i === stageIdx ? "bg-primary animate-pulse" : "bg-white/[0.1]"
                    }`} />
                    <span className={`text-xs capitalize transition-colors ${
                      i === stageIdx ? "text-foreground" : i < stageIdx ? "text-primary/60" : "text-muted-foreground/30"
                    }`}>{s}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
