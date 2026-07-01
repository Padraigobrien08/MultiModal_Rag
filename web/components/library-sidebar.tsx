"use client";

import { useEffect, useState } from "react";
import { Play, ImageIcon, X, Loader2, AlertTriangle } from "lucide-react";

type Tutorial = {
  id: string;
  title: string;
  source_type: string;
  step_count: number;
  potential_duplicate_of?: string | null;
};

type ActiveJob = {
  job_id: string;
  status: string;
  stage: string | null;
  segments_done: number | null;
  segments_total: number | null;
};

type Props = {
  onClose: () => void;
  scopedId: string | null;
  onScopeTutorial: (t: { id: string; title: string } | null) => void;
  refreshKey?: number;
};

export function LibrarySidebar({ onClose, scopedId, onScopeTutorial, refreshKey }: Props) {
  const [tutorials, setTutorials] = useState<Tutorial[]>([]);
  const [jobs, setJobs] = useState<ActiveJob[]>([]);
  const [loading, setLoading] = useState(true);

  async function fetchAll() {
    try {
      const [tRes, jRes] = await Promise.all([
        fetch("/api/tutorials", { cache: "no-store" }),
        fetch("/api/jobs?status=pending,running", { cache: "no-store" }),
      ]);
      if (tRes.ok) setTutorials(await tRes.json());
      if (jRes.ok) setJobs(await jRes.json());
    } catch {}
    setLoading(false);
  }

  useEffect(() => { void Promise.resolve().then(() => fetchAll()); }, [refreshKey]);

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch("/api/jobs?status=pending,running", { cache: "no-store" });
        if (res.ok) {
          const next = await res.json();
          // If jobs just finished, refresh tutorials too
          if (next.length < jobs.length) fetchAll();
          else setJobs(next);
        }
      } catch {}
    }, 4000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex flex-col h-full bg-background border-l border-border/60">
      {/* Header */}
      <div className="h-14 px-4 flex items-center justify-between shrink-0 border-b border-border/40">
        <span className="text-sm font-semibold text-foreground">Library</span>
        <button
          onClick={onClose}
          className="h-7 w-7 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-white/[0.06] hover:text-foreground transition-colors"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-3 scrollbar-hide">
        {/* Active jobs */}
        {jobs.length > 0 && (
          <div className="mb-4">
            <p className="px-2 mb-1 text-[10px] font-mono uppercase tracking-wider text-muted-foreground/40">
              Processing
            </p>
            {jobs.map(job => (
              <div key={job.job_id} className="flex items-center gap-2 px-2 py-2 rounded-lg text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin text-primary shrink-0" />
                <span className="flex-1 truncate capitalize">{job.stage || job.status}</span>
                {job.stage === "structuring" && job.segments_total && (
                  <span className="font-mono text-[10px] shrink-0">{job.segments_done ?? 0}/{job.segments_total}</span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Tutorials */}
        <p className="px-2 mb-1 text-[10px] font-mono uppercase tracking-wider text-muted-foreground/40">
          {loading ? "Loading…" : `${tutorials.length} tutorial${tutorials.length !== 1 ? "s" : ""}`}
        </p>

        {!loading && tutorials.length === 0 && (
          <div className="px-2 py-8 text-center">
            <p className="text-xs text-muted-foreground/50 mb-1">No tutorials yet</p>
            <p className="text-[11px] text-muted-foreground/30">Click <span className="font-medium">+ Add</span> to ingest your first tutorial</p>
          </div>
        )}

        {tutorials.map(t => (
          <button
            key={t.id}
            onClick={() => onScopeTutorial(scopedId === t.id ? null : { id: t.id, title: t.title })}
            className={`group w-full text-left flex items-center gap-2.5 px-2 py-2.5 rounded-lg transition-colors ${
              scopedId === t.id
                ? "bg-primary/10 text-foreground border border-primary/20"
                : "hover:bg-white/[0.04] text-muted-foreground hover:text-foreground"
            }`}
          >
            <div className="h-7 w-7 rounded bg-white/[0.04] border border-border/30 flex items-center justify-center shrink-0">
              {t.source_type === "youtube"
                ? <Play className="h-3 w-3 text-red-400" />
                : <ImageIcon className="h-3 w-3 text-sky-400" />}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1">
                <p className="text-xs font-medium truncate leading-tight">{t.title}</p>
                {t.potential_duplicate_of && (
                  <span title="Possible duplicate — consider removing"><AlertTriangle className="h-3 w-3 text-yellow-500 shrink-0" /></span>
                )}
              </div>
              <p className="text-[10px] text-muted-foreground/50 mt-0.5">{t.step_count} steps</p>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
