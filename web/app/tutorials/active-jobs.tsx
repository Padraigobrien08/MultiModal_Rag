"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, AlertCircle, CheckCircle2, Clock } from "lucide-react";

type Job = {
  job_id: string;
  status: "pending" | "running" | "done" | "error";
  stage: string | null;
  segments_done: number | null;
  segments_total: number | null;
  tutorial_id: string | null;
  step_count: number | null;
  error: string | null;
  created_at: string | null;
};

const STAGE_LABELS: Record<string, string> = {
  downloading:   "Downloading",
  transcribing:  "Transcribing",
  aligning:      "Aligning",
  structuring:   "Extracting steps",
  consolidating: "Consolidating",
  indexing:      "Indexing",
};

function useElapsed(startIso: string | null) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!startIso) return;
    const start = new Date(startIso).getTime();
    const tick = () => setElapsed(Math.floor((Date.now() - start) / 1000));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [startIso]);
  return elapsed;
}

function fmt(s: number) {
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

function JobCard({ job }: { job: Job }) {
  const elapsed = useElapsed(job.status === "pending" || job.status === "running" ? job.created_at : null);
  const isActive = job.status === "pending" || job.status === "running";
  const stageLabel = job.stage ? (STAGE_LABELS[job.stage] ?? job.stage) : null;
  const pct = job.stage === "structuring" && job.segments_total
    ? Math.round(((job.segments_done ?? 0) / job.segments_total) * 100)
    : null;

  return (
    <div className={`rounded-xl border bg-card p-5 flex flex-col gap-3 transition-all ${
      job.status === "error"
        ? "border-destructive/30 bg-destructive/5"
        : isActive
        ? "border-primary/20 bg-primary/5"
        : "border-border/60"
    }`}>
      {/* Header row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {isActive && <Loader2 className="h-3.5 w-3.5 animate-spin text-primary shrink-0" />}
          {job.status === "done" && <CheckCircle2 className="h-3.5 w-3.5 text-primary shrink-0" />}
          {job.status === "error" && <AlertCircle className="h-3.5 w-3.5 text-destructive shrink-0" />}
          <span className={`text-xs font-mono font-medium uppercase tracking-widest ${
            job.status === "error" ? "text-destructive" :
            job.status === "done"  ? "text-primary"     :
                                     "text-primary"
          }`}>
            {job.status === "pending"    ? "Queued"     :
             job.status === "running"    ? (stageLabel ?? "Processing") :
             job.status === "done"       ? "Complete"   :
                                           "Failed"}
          </span>
        </div>
        {isActive && (
          <div className="flex items-center gap-1 text-[10px] font-mono text-muted-foreground">
            <Clock className="h-3 w-3" />
            {fmt(elapsed)}
          </div>
        )}
        {job.status === "done" && job.step_count && (
          <span className="text-xs font-mono text-primary">{job.step_count} steps</span>
        )}
      </div>

      {/* Stage + progress */}
      {job.status === "running" && stageLabel && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span className="font-mono">{stageLabel}</span>
            {job.stage === "structuring" && job.segments_total && (
              <span className="font-mono tabular-nums">
                {job.segments_done ?? 0}/{job.segments_total}
              </span>
            )}
          </div>
          {pct !== null && (
            <div className="h-1 rounded-full bg-border/60 overflow-hidden">
              <div
                className="h-full bg-primary rounded-full transition-all duration-700"
                style={{ width: `${pct}%` }}
              />
            </div>
          )}
          {pct === null && (
            <div className="h-1 rounded-full bg-border/60 overflow-hidden">
              <div className="h-full w-1/3 bg-primary/60 rounded-full animate-[shimmer_1.5s_infinite]"
                style={{
                  backgroundImage: "linear-gradient(90deg, transparent, rgba(0,255,136,0.4), transparent)",
                  backgroundSize: "200% 100%",
                  animation: "shimmer 1.5s infinite",
                }}
              />
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {job.status === "error" && job.error && (
        <p className="text-xs text-destructive/80 font-mono leading-relaxed">{job.error}</p>
      )}

      {/* Done — link to tutorial */}
      {job.status === "done" && job.tutorial_id && (
        <a
          href={`/tutorials/${job.tutorial_id}`}
          className="text-xs font-mono text-primary hover:underline"
        >
          → View tutorial
        </a>
      )}

      {/* Job ID → detail view */}
      <Link
        href={`/jobs/${job.job_id}`}
        className="text-[10px] font-mono text-muted-foreground/40 hover:text-primary truncate transition-colors"
      >
        {job.job_id} · details →
      </Link>
    </div>
  );
}

export function ActiveJobs() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const router = useRouter();
  const prevDoneIds = useRef(new Set<string>());

  // Also check for newly-completed jobs to trigger a library refresh
  const fetchWithCompletion = useCallback(async () => {
    try {
      // Fetch active + recently done (last 5 min)
      const res = await fetch("/api/jobs?status=pending,running", { cache: "no-store" });
      if (!res.ok) return;
      const active: Job[] = await res.json();

      // Check if anything that was previously active is now gone (completed)
      const activeIds = new Set(active.map(j => j.job_id));
      const newlyDone = [...prevDoneIds.current].filter(id => !activeIds.has(id));
      if (newlyDone.length > 0) {
        router.refresh(); // reload server component (tutorial list)
      }
      prevDoneIds.current = activeIds;
      setJobs(active);
    } catch {
      // silently ignore
    }
  }, [router]);

  useEffect(() => {
    void Promise.resolve().then(() => fetchWithCompletion());
    const id = setInterval(fetchWithCompletion, 3000);
    return () => clearInterval(id);
  }, [fetchWithCompletion]);

  if (jobs.length === 0) return null;

  return (
    <div className="mb-8 animate-fade-up">
      <div className="flex items-center gap-2 mb-4">
        <div className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
        <h2 className="text-xs font-mono font-medium text-muted-foreground uppercase tracking-widest">
          In Progress ({jobs.length})
        </h2>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {jobs.map(job => (
          <JobCard key={job.job_id} job={job} />
        ))}
      </div>
      <div className="mt-4 mb-2 h-px bg-border/40" />
    </div>
  );
}
