"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import {
  AlertTriangle, RefreshCw, Loader2, ExternalLink, ChevronDown,
  ChevronUp, Search, BookOpen, Rss,
} from "lucide-react";

type Gap = {
  topic: string;
  description: string;
  suggested_title: string;
  search_terms: string[];
  query_count: number;
  unique_query_count: number;
  example_queries: string[];
};

function youtubeSearchUrl(terms: string[]) {
  return `https://www.youtube.com/results?search_query=${encodeURIComponent(terms.join(" "))}`;
}

function GapCard({ gap, index }: { gap: Gap; index: number }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="rounded-xl border border-border/60 bg-card overflow-hidden animate-fade-up"
      style={{ animationDelay: `${index * 50}ms` }}
    >
      {/* Header */}
      <div className="px-5 pt-5 pb-4">
        <div className="flex items-start justify-between gap-3 mb-3">
          <h3 className="text-base font-semibold text-foreground leading-snug">
            {gap.topic}
          </h3>
          <span className="shrink-0 inline-flex items-center gap-1 text-xs font-mono font-semibold px-2 py-0.5 rounded-full bg-destructive/10 text-destructive border border-destructive/20">
            {gap.query_count}×
          </span>
        </div>
        <p className="text-sm text-muted-foreground leading-relaxed">
          {gap.description}
        </p>
      </div>

      {/* Suggested tutorial */}
      <div className="mx-5 mb-4 px-3.5 py-2.5 rounded-lg bg-primary/5 border border-primary/15">
        <p className="text-[11px] font-mono text-primary/60 mb-0.5 uppercase tracking-wide">
          Suggested tutorial
        </p>
        <p className="text-sm font-medium text-foreground">{gap.suggested_title}</p>
      </div>

      {/* Search terms */}
      {gap.search_terms.length > 0 && (
        <div className="px-5 mb-4 flex flex-wrap gap-1.5">
          {gap.search_terms.map(term => (
            <span
              key={term}
              className="inline-flex items-center text-xs font-mono px-2 py-0.5 rounded bg-white/[0.05] border border-border/50 text-muted-foreground"
            >
              {term}
            </span>
          ))}
        </div>
      )}

      {/* Example queries (collapsible) */}
      {gap.example_queries.length > 0 && (
        <div className="border-t border-border/40">
          <button
            onClick={() => setExpanded(v => !v)}
            className="w-full flex items-center justify-between px-5 py-2.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <span className="font-mono">
              {gap.unique_query_count} example quer{gap.unique_query_count === 1 ? "y" : "ies"}
            </span>
            {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
          {expanded && (
            <div className="px-5 pb-4 space-y-1.5">
              {gap.example_queries.map((q, i) => (
                <p key={i} className="text-xs text-muted-foreground/70 font-mono pl-2 border-l border-border/40">
                  &ldquo;{q}&rdquo;
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="border-t border-border/40 px-5 py-3 flex gap-2">
        <a
          href={youtubeSearchUrl(gap.search_terms.length ? gap.search_terms : [gap.suggested_title])}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 h-8 px-3 rounded-lg border border-border/60 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-white/[0.06] transition-colors"
        >
          <Search className="h-3 w-3" />
          Find on YouTube
          <ExternalLink className="h-2.5 w-2.5 opacity-50" />
        </a>
        <Link
          href={`/watchers?prefill=${encodeURIComponent(JSON.stringify({ type: "youtube_channel", hint: gap.search_terms[0] ?? gap.topic }))}`}
          className="flex items-center gap-1.5 h-8 px-3 rounded-lg border border-border/60 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-white/[0.06] transition-colors"
        >
          <Rss className="h-3 w-3" />
          Watch a source
        </Link>
      </div>
    </div>
  );
}

type State =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "done"; gaps: Gap[]; fresh: boolean }
  | { phase: "error"; message: string };

export default function GapsPage() {
  const [state, setState] = useState<State>({ phase: "idle" });

  const runAnalysis = useCallback(async (force = false) => {
    setState({ phase: "loading" });
    try {
      const res = await fetch(`/api/gaps?force=${force}`);
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const gaps: Gap[] = await res.json();
      setState({ phase: "done", gaps, fresh: force });
    } catch (err) {
      setState({ phase: "error", message: err instanceof Error ? err.message : "Failed" });
    }
  }, []);

  return (
    <div className="max-w-4xl mx-auto px-6 py-14">
      {/* Header */}
      <div className="flex items-start justify-between mb-10 animate-fade-up">
        <div>
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-destructive/20 bg-destructive/5 mb-4">
            <AlertTriangle className="h-3 w-3 text-destructive" />
            <span className="text-xs font-mono text-destructive font-medium">Knowledge Gaps</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight text-foreground mb-2">
            Coverage Gaps
          </h1>
          <p className="text-sm text-muted-foreground max-w-lg leading-relaxed">
            Topics users asked about that the library couldn&apos;t answer well.
            Ranked by how often each gap was hit.
          </p>
        </div>

        <div className="mt-8 flex items-center gap-2">
          {state.phase === "done" && (
            <button
              onClick={() => runAnalysis(true)}
              className="flex items-center gap-1.5 h-9 px-4 rounded-lg border border-border bg-card text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-white/[0.06] transition-all"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Re-analyse
            </button>
          )}
          {state.phase !== "done" && state.phase !== "loading" && (
            <button
              onClick={() => runAnalysis(false)}
              className="flex items-center gap-1.5 h-9 px-4 rounded-lg bg-primary text-black text-sm font-semibold hover:bg-primary/90 transition-colors"
            >
              <Search className="h-3.5 w-3.5" />
              Analyse gaps
            </button>
          )}
        </div>
      </div>

      {/* States */}
      {state.phase === "idle" && (
        <div className="rounded-xl border border-dashed border-border/60 p-20 text-center">
          <div className="h-12 w-12 rounded-xl bg-white/[0.04] border border-border/60 flex items-center justify-center mx-auto mb-4">
            <AlertTriangle className="h-5 w-5 text-muted-foreground" />
          </div>
          <p className="text-sm text-muted-foreground mb-6">
            Analyse your query logs to find topics the library can&apos;t answer.
          </p>
          <button
            onClick={() => runAnalysis(false)}
            className="inline-flex items-center gap-1.5 h-9 px-4 rounded-lg bg-primary text-black text-sm font-semibold hover:bg-primary/90 transition-colors"
          >
            <Search className="h-3.5 w-3.5" />
            Analyse gaps
          </button>
          <p className="text-xs text-muted-foreground/40 mt-4">
            Results are cached for 1 hour.
          </p>
        </div>
      )}

      {state.phase === "loading" && (
        <div className="rounded-xl border border-border/60 p-20 text-center">
          <Loader2 className="h-6 w-6 animate-spin text-primary mx-auto mb-4" />
          <p className="text-sm text-muted-foreground">Analysing query logs…</p>
          <p className="text-xs text-muted-foreground/40 mt-2">
            Clustering queries and describing gaps with AI — takes a few seconds.
          </p>
        </div>
      )}

      {state.phase === "error" && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-8 text-center">
          <AlertTriangle className="h-6 w-6 text-destructive mx-auto mb-3" />
          <p className="text-sm text-foreground mb-1">Analysis failed</p>
          <p className="text-xs text-muted-foreground mb-4">{state.message}</p>
          <button onClick={() => runAnalysis(false)} className="text-sm text-primary hover:underline">
            Try again
          </button>
        </div>
      )}

      {state.phase === "done" && state.gaps.length === 0 && (
        <div className="rounded-xl border border-border/60 p-20 text-center">
          <div className="h-12 w-12 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center mx-auto mb-4">
            <BookOpen className="h-5 w-5 text-primary" />
          </div>
          <p className="text-sm font-medium text-foreground mb-1">No significant gaps found</p>
          <p className="text-xs text-muted-foreground">
            Either the library covers queries well, or there isn&apos;t enough query history yet.
          </p>
        </div>
      )}

      {state.phase === "done" && state.gaps.length > 0 && (
        <>
          <p className="text-xs text-muted-foreground/60 mb-6 font-mono">
            {state.gaps.length} gap{state.gaps.length !== 1 ? "s" : ""} found ·{" "}
            {state.gaps.reduce((a, g) => a + g.query_count, 0)} total unanswered queries
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {state.gaps.map((gap, i) => (
              <GapCard key={gap.topic} gap={gap} index={i} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
