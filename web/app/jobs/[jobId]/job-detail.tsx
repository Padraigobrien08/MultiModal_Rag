"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  ExternalLink,
  Loader2,
  RefreshCw,
  XCircle,
} from "lucide-react";

type JobEvent = {
  stage: string | null;
  level: "info" | "warning" | "error";
  message: string;
  created_at: string | null;
};

type Job = {
  job_id: string;
  status: "pending" | "running" | "done" | "error" | "cancelled";
  stage: string | null;
  segments_done: number | null;
  segments_total: number | null;
  tutorial_id: string | null;
  step_count: number | null;
  error: string | null;
  source_type: string | null;
  source_url: string | null;
  title: string | null;
  created_at: string | null;
  updated_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  retryable: boolean;
  events: JobEvent[];
};

const STAGE_LABELS: Record<string, string> = {
  downloading: "Downloading",
  transcribing: "Transcribing",
  extracting_frames: "Extracting frames",
  aligning: "Aligning",
  structuring: "Extracting steps",
  consolidating: "Consolidating",
  indexing: "Indexing",
  fetching: "Fetching",
  processing: "Processing",
};

const STATUS_META: Record<
  Job["status"],
  { label: string; className: string }
> = {
  pending: { label: "Queued", className: "text-primary border-primary/20 bg-primary/5" },
  running: { label: "Running", className: "text-primary border-primary/20 bg-primary/5" },
  done: { label: "Complete", className: "text-primary border-primary/20 bg-primary/5" },
  error: { label: "Failed", className: "text-destructive border-destructive/30 bg-destructive/5" },
  cancelled: {
    label: "Cancelled",
    className: "text-muted-foreground border-border/60 bg-white/[0.03]",
  },
};

function fmtDuration(s: number) {
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

function fmtTime(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export function JobDetail({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [job, setJob] = useState<Job | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionNote, setActionNote] = useState<string | null>(null);
  const wasActive = useRef(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/jobs/${jobId}`, { cache: "no-store" });
      if (res.status === 404) {
        setNotFound(true);
        return;
      }
      if (!res.ok) return;
      const data: Job = await res.json();
      // When a job finishes, refresh the library server components.
      const active = data.status === "pending" || data.status === "running";
      if (wasActive.current && !active) router.refresh();
      wasActive.current = active;
      setJob(data);
    } catch {
      // transient — keep last state
    }
  }, [jobId, router]);

  useEffect(() => {
    void Promise.resolve().then(load);
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [load]);

  async function handleRetry() {
    setActionBusy(true);
    setActionNote(null);
    try {
      const res = await fetch(`/api/jobs/${jobId}/retry`, { method: "POST" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setActionNote(body.detail ?? body.error ?? "Retry failed");
      } else {
        wasActive.current = true;
        await load();
      }
    } finally {
      setActionBusy(false);
    }
  }

  async function handleCancel() {
    setActionBusy(true);
    setActionNote(null);
    try {
      const res = await fetch(`/api/jobs/${jobId}/cancel`, { method: "POST" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setActionNote(body.detail ?? body.error ?? "Cancel failed");
      } else {
        setActionNote(body.note ?? null);
        await load();
      }
    } finally {
      setActionBusy(false);
    }
  }

  if (notFound) {
    return (
      <div className="max-w-3xl mx-auto px-6 py-16">
        <BackLink />
        <div className="mt-8 rounded-xl border border-dashed border-border/60 p-16 text-center">
          <p className="text-sm text-muted-foreground">Job not found.</p>
        </div>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="max-w-3xl mx-auto px-6 py-16">
        <BackLink />
        <div className="mt-8 flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading job…
        </div>
      </div>
    );
  }

  const isActive = job.status === "pending" || job.status === "running";
  const status = STATUS_META[job.status];
  const stageLabel = job.stage ? STAGE_LABELS[job.stage] ?? job.stage : null;
  const pct =
    job.stage === "structuring" && job.segments_total
      ? Math.round(((job.segments_done ?? 0) / job.segments_total) * 100)
      : null;
  const elapsed =
    job.started_at && job.completed_at
      ? Math.max(
          0,
          Math.floor(
            (new Date(job.completed_at).getTime() - new Date(job.started_at).getTime()) / 1000,
          ),
        )
      : null;

  return (
    <div className="max-w-3xl mx-auto px-6 py-14">
      <BackLink />

      {/* Header */}
      <div className="mt-6 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-3">
            <span
              className={`inline-flex items-center gap-1.5 text-xs font-mono font-medium px-2.5 py-1 rounded-full border ${status.className}`}
            >
              {isActive && <Loader2 className="h-3 w-3 animate-spin" />}
              {job.status === "done" && <CheckCircle2 className="h-3 w-3" />}
              {job.status === "error" && <AlertCircle className="h-3 w-3" />}
              {job.status === "cancelled" && <XCircle className="h-3 w-3" />}
              {status.label}
            </span>
            {job.source_type && (
              <span className="text-[11px] font-mono px-2 py-0.5 rounded-full border border-border/60 text-muted-foreground">
                {job.source_type}
              </span>
            )}
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground truncate">
            {job.title ?? "Ingestion job"}
          </h1>
          {job.source_url && !job.source_url.startsWith("images://") && (
            <a
              href={job.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 inline-flex items-center gap-1 text-xs font-mono text-muted-foreground hover:text-primary transition-colors truncate max-w-full"
            >
              {job.source_url}
              <ExternalLink className="h-3 w-3 shrink-0" />
            </a>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0">
          {isActive && (
            <button
              onClick={handleCancel}
              disabled={actionBusy}
              className="inline-flex items-center gap-1.5 h-9 px-3 rounded-lg border border-border bg-card text-sm font-medium text-muted-foreground hover:text-destructive hover:border-destructive/40 transition-all disabled:opacity-50"
            >
              <XCircle className="h-3.5 w-3.5" />
              Cancel
            </button>
          )}
          {(job.status === "error" || job.status === "cancelled") && job.retryable && (
            <button
              onClick={handleRetry}
              disabled={actionBusy}
              className="inline-flex items-center gap-1.5 h-9 px-3 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Retry
            </button>
          )}
        </div>
      </div>

      {/* Progress bar for structuring */}
      {job.status === "running" && (
        <div className="mt-6 space-y-1.5">
          <div className="flex items-center justify-between text-xs text-muted-foreground font-mono">
            <span>{stageLabel ?? "Processing"}</span>
            {job.stage === "structuring" && job.segments_total && (
              <span className="tabular-nums">
                {job.segments_done ?? 0}/{job.segments_total}
              </span>
            )}
          </div>
          <div className="h-1 rounded-full bg-border/60 overflow-hidden">
            <div
              className={`h-full bg-primary rounded-full transition-all duration-700 ${
                pct === null ? "w-1/3 opacity-60" : ""
              }`}
              style={pct === null ? undefined : { width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {/* Error */}
      {job.status === "error" && job.error && (
        <div className="mt-6 rounded-lg border border-destructive/30 bg-destructive/5 p-4">
          <p className="text-sm text-destructive leading-relaxed">{job.error}</p>
          {!job.retryable && (
            <p className="mt-2 text-xs text-muted-foreground">
              This job can&apos;t be retried automatically — re-submit it from the original source.
            </p>
          )}
        </div>
      )}

      {actionNote && (
        <p className="mt-4 text-xs text-muted-foreground font-mono">{actionNote}</p>
      )}

      {/* Done — link to tutorial */}
      {job.status === "done" && job.tutorial_id && (
        <Link
          href={`/tutorials/${job.tutorial_id}`}
          className="mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
        >
          View tutorial ({job.step_count} steps) →
        </Link>
      )}

      {/* Metadata grid */}
      <dl className="mt-8 grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
        <Meta label="Created" value={fmtTime(job.created_at)} />
        <Meta label="Started" value={fmtTime(job.started_at)} />
        <Meta label="Completed" value={fmtTime(job.completed_at)} />
        <Meta label="Duration" value={elapsed !== null ? fmtDuration(elapsed) : "—"} />
      </dl>

      {/* Event timeline */}
      <div className="mt-10">
        <div className="flex items-center gap-2 mb-4">
          <Clock className="h-3.5 w-3.5 text-muted-foreground" />
          <h2 className="text-xs font-mono font-medium text-muted-foreground uppercase tracking-widest">
            Event log
          </h2>
        </div>
        {job.events.length === 0 ? (
          <p className="text-sm text-muted-foreground">No events recorded yet.</p>
        ) : (
          <ol className="relative border-l border-border/60 ml-1.5 space-y-4">
            {job.events.map((e, i) => (
              <li key={i} className="ml-4">
                <span
                  className={`absolute -left-[5px] mt-1.5 h-2 w-2 rounded-full ${
                    e.level === "error"
                      ? "bg-destructive"
                      : e.level === "warning"
                      ? "bg-yellow-500"
                      : "bg-primary/60"
                  }`}
                />
                <div className="flex items-baseline justify-between gap-3">
                  <p
                    className={`text-sm leading-snug ${
                      e.level === "error" ? "text-destructive" : "text-foreground"
                    }`}
                  >
                    {e.message}
                  </p>
                  <time className="text-[10px] font-mono text-muted-foreground/60 shrink-0 tabular-nums">
                    {e.created_at ? new Date(e.created_at).toLocaleTimeString() : ""}
                  </time>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>

      <p className="mt-10 text-[10px] font-mono text-muted-foreground/30">{job.job_id}</p>
    </div>
  );
}

function BackLink() {
  return (
    <Link
      href="/tutorials"
      className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
    >
      <ArrowLeft className="h-3.5 w-3.5" />
      Library
    </Link>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted-foreground/60 font-mono uppercase tracking-wider text-[10px] mb-1">
        {label}
      </dt>
      <dd className="text-foreground font-mono">{value}</dd>
    </div>
  );
}
