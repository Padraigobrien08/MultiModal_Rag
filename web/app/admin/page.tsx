"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { ArrowLeft, RefreshCw, ChevronDown, ChevronRight, ThumbsDown, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────

type StepLog = { step_id: string; distance: number; ce_score: number };
type FeedbackItem = { step_id: string; helpful: boolean };
type QueryLog = {
  id: number;
  query_text: string;
  hypothetical_text: string | null;
  tutorial_scoped: string | null;
  tutorial_ids_searched: string[] | null;
  steps_returned: StepLog[];
  answer_text: string | null;
  history_length: number;
  latency_hyde_ms: number;
  latency_retrieval_ms: number;
  latency_synthesis_ms: number;
  total_latency_ms: number;
  created_at: string;
  feedback?: FeedbackItem[];
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function pct(arr: number[], p: number): number {
  if (!arr.length) return 0;
  const sorted = [...arr].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil((p / 100) * sorted.length) - 1)];
}

function avg(arr: number[]): number {
  return arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
}

function fmtMs(ms: number): string {
  if (!ms) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function histogram(values: number[], bins = 10): { label: string; count: number }[] {
  if (!values.length) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) return [{ label: min.toFixed(2), count: values.length }];
  const w = (max - min) / bins;
  const result = Array.from({ length: bins }, (_, i) => ({
    label: (min + i * w).toFixed(2),
    count: 0,
  }));
  for (const v of values) result[Math.min(Math.floor((v - min) / w), bins - 1)].count++;
  return result;
}

function byDay(logs: QueryLog[]): { date: string; count: number }[] {
  const m = new Map<string, number>();
  for (const l of logs) {
    const d = l.created_at.slice(0, 10);
    m.set(d, (m.get(d) ?? 0) + 1);
  }
  return [...m.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([d, count]) => ({
      date: new Date(d + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      count,
    }));
}

// ── Phase config ──────────────────────────────────────────────────────────────

const PHASES = [
  { name: "HyDE",      key: "latency_hyde_ms"      },
  { name: "Retrieval", key: "latency_retrieval_ms"  },
  { name: "Synthesis", key: "latency_synthesis_ms"  },
] as const;

// ── SVG bar chart ─────────────────────────────────────────────────────────────

function BarChartSVG({ data }: { data: { label: string; count: number }[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (!data.length) return <div className="h-32 flex items-center justify-center text-xs text-muted-foreground/40">No data</div>;

  const W = 480; const H = 120;
  const PL = 28; const PR = 8; const PT = 6; const PB = 20;
  const cW = W - PL - PR; const cH = H - PT - PB;
  const maxVal = Math.max(...data.map(d => d.count), 1);
  const n = data.length;
  const barW = cW / n;
  const gap = Math.max(barW * 0.2, 1);
  const yTicks = [0, Math.ceil(maxVal / 2), maxVal];
  const labelIdxs = new Set([0, Math.floor(n / 2), n - 1]);

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: H }} preserveAspectRatio="xMidYMid meet">
        {yTicks.map((v, i) => {
          const y = PT + cH - (v / maxVal) * cH;
          return <line key={i} x1={PL} x2={W - PR} y1={y} y2={y} stroke="rgba(255,255,255,0.05)" strokeWidth={1} />;
        })}
        {yTicks.map((v, i) => {
          const y = PT + cH - (v / maxVal) * cH;
          return <text key={i} x={PL - 4} y={y + 3.5} textAnchor="end" fontSize={9} fill="#6b6b80" fontFamily="var(--font-mono)">{v}</text>;
        })}
        {data.map((d, i) => {
          const bH = Math.max((d.count / maxVal) * cH, d.count ? 2 : 0);
          const x = PL + i * barW + gap / 2;
          const y = PT + cH - bH;
          return (
            <rect key={i} x={x} y={y} width={barW - gap} height={bH}
              fill={hover === i ? "#00ff88" : "rgba(0,255,136,0.35)"} rx={2}
              onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
              style={{ cursor: "default", transition: "fill 0.1s" }} />
          );
        })}
        {data.map((d, i) => {
          if (!labelIdxs.has(i)) return null;
          return <text key={i} x={PL + i * barW + barW / 2} y={H - 4} textAnchor="middle" fontSize={9} fill="#6b6b80" fontFamily="var(--font-mono)">{d.label}</text>;
        })}
      </svg>
      {hover !== null && (
        <div
          className="pointer-events-none absolute top-1 bg-card border border-border/60 rounded-md px-2 py-1 text-[11px] font-mono whitespace-nowrap shadow-lg -translate-x-1/2"
          style={{ left: `${((hover + 0.5) / n) * 100}%` }}
        >
          <span className="text-muted-foreground">{data[hover].label} </span>
          <span className="text-foreground font-semibold">{data[hover].count}</span>
        </div>
      )}
    </div>
  );
}

// ── Shared primitives ─────────────────────────────────────────────────────────

function StatCell({ label, value, sub, warn }: {
  label: string; value: string; sub?: string; warn?: boolean;
}) {
  return (
    <div className="rounded-xl border border-border/50 bg-card px-4 py-4">
      <div className={cn("text-2xl font-semibold font-mono tabular-nums leading-none", warn ? "text-destructive" : "text-foreground")}>
        {value}
      </div>
      <div className="text-xs text-muted-foreground mt-1.5">{label}</div>
      {sub && <div className="text-[11px] font-mono text-muted-foreground/50 mt-0.5">{sub}</div>}
    </div>
  );
}

function SectionHead({ children }: { children: React.ReactNode }) {
  return <h2 className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground/40 mb-3">{children}</h2>;
}

function Panel({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-xl border border-border/50 bg-card", className)}>
      {children}
    </div>
  );
}

// ── Query Explorer ────────────────────────────────────────────────────────────

function QueryTable({ logs }: { logs: QueryLog[] }) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  function toggle(id: number) {
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  return (
    <Panel>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border/40 bg-white/[0.02]">
            <th className="w-8 px-3 py-2.5" />
            <th className="text-left px-4 py-2.5 text-xs text-muted-foreground font-medium">Query</th>
            <th className="text-right px-4 py-2.5 text-xs text-muted-foreground font-medium whitespace-nowrap">Total</th>
            <th className="text-right px-4 py-2.5 text-xs text-muted-foreground font-medium">Steps</th>
            <th className="text-right px-4 py-2.5 text-xs text-muted-foreground font-medium hidden md:table-cell">When</th>
          </tr>
        </thead>
        <tbody>
          {logs.slice(0, 200).map((log, idx) => {
            const rowId = log.id ?? idx;
            const isOpen = expanded.has(rowId);
            const hasSteps = (log.steps_returned?.length ?? 0) > 0;
            const feedback = log.feedback ?? [];
            const downCount = feedback.filter(f => !f.helpful).length;

            return (
              <React.Fragment key={rowId}>
                <tr
                  onClick={() => toggle(rowId)}
                  className={cn(
                    "border-b border-border/30 cursor-pointer transition-colors",
                    isOpen ? "bg-white/[0.04]" : idx % 2 === 1 ? "bg-white/[0.01] hover:bg-white/[0.03]" : "hover:bg-white/[0.02]",
                  )}
                >
                  <td className="px-3 py-2.5 text-muted-foreground/40">
                    {isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                  </td>
                  <td className="px-4 py-2.5 max-w-0">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="truncate">{log.query_text}</span>
                      {downCount > 0 && (
                        <span className="shrink-0 inline-flex items-center gap-0.5 text-[10px] font-mono px-1.5 py-0.5 rounded bg-destructive/10 text-destructive">
                          <ThumbsDown className="h-2.5 w-2.5" />{downCount}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums whitespace-nowrap">{fmtMs(log.total_latency_ms)}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums">
                    {hasSteps ? log.steps_returned.length : <span className="text-destructive">0</span>}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-[11px] text-muted-foreground hidden md:table-cell whitespace-nowrap">
                    {fmtDate(log.created_at)}
                  </td>
                </tr>

                {isOpen && (
                  <tr className="border-b border-border/40">
                    <td colSpan={5} className="bg-background/60 px-8 py-5">
                      <div className="space-y-5 max-w-3xl">
                        {log.hypothetical_text && (
                          <div>
                            <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground/40 mb-1.5">Hypothetical (HyDE)</p>
                            <p className="text-xs text-foreground/60 leading-relaxed">{log.hypothetical_text}</p>
                          </div>
                        )}
                        {hasSteps && (
                          <div>
                            <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground/40 mb-2">Steps retrieved</p>
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="text-muted-foreground/50 border-b border-border/30">
                                  <th className="text-left pb-1.5 pr-6 font-normal">Step ID</th>
                                  <th className="text-right pb-1.5 pr-6 font-normal">Distance</th>
                                  <th className="text-right pb-1.5 pr-6 font-normal">CE score</th>
                                  <th className="text-right pb-1.5 font-normal">Feedback</th>
                                </tr>
                              </thead>
                              <tbody>
                                {log.steps_returned.map(step => {
                                  const fb = feedback.find(f => f.step_id === step.step_id);
                                  return (
                                    <tr key={step.step_id} className="border-b border-border/20 last:border-0">
                                      <td className="py-1.5 pr-6 font-mono text-muted-foreground/60 max-w-[180px] truncate">{step.step_id}</td>
                                      <td className={cn("py-1.5 pr-6 font-mono text-right tabular-nums", step.distance < 0.35 ? "text-primary" : step.distance > 0.65 ? "text-destructive/70" : "")}>
                                        {step.distance.toFixed(3)}
                                      </td>
                                      <td className={cn("py-1.5 pr-6 font-mono text-right tabular-nums", step.ce_score > 0 ? "text-primary" : "")}>
                                        {step.ce_score.toFixed(3)}
                                      </td>
                                      <td className="py-1.5 text-right">
                                        {fb ? (fb.helpful ? <span className="text-primary text-sm">↑</span> : <span className="text-destructive text-sm">↓</span>) : <span className="text-muted-foreground/30">—</span>}
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        )}
                        {log.answer_text && (
                          <div>
                            <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground/40 mb-1.5">Answer</p>
                            <p className="text-xs text-foreground/60 leading-relaxed line-clamp-5">{log.answer_text}</p>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
      {logs.length > 200 && (
        <div className="px-4 py-3 border-t border-border/40 text-xs text-center text-muted-foreground/50">
          Showing 200 of {logs.length.toLocaleString()} queries
        </div>
      )}
    </Panel>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

const RANGES = ["24h", "7d", "30d", "all"] as const;
type Range = typeof RANGES[number];

export default function AdminPage() {
  const [logs, setLogs] = useState<QueryLog[]>([]);
  const [tutorialNames, setTutorialNames] = useState<Map<string, string>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [range, setRange] = useState<Range>("7d");

  async function fetchLogs(r: Range = range) {
    setRefreshing(true);
    try {
      const params = r !== "all" ? `?since=${r}` : "";
      const res = await fetch(`/api/admin/query-logs${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const raw: QueryLog[] = data.logs ?? data;
      setLogs(raw.map(log => ({
        ...log,
        steps_returned: typeof log.steps_returned === "string" ? JSON.parse(log.steps_returned) : (log.steps_returned ?? []),
        tutorial_ids_searched: typeof log.tutorial_ids_searched === "string" ? JSON.parse(log.tutorial_ids_searched) : (log.tutorial_ids_searched ?? []),
      })));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  function handleRangeChange(r: Range) {
    setRange(r);
    setLoading(true);
    setError(null);
    fetchLogs(r);
  }

  useEffect(() => {
    fetchLogs();
    fetch("/api/tutorials")
      .then(r => r.json())
      .then((ts: { id: string; title: string }[]) =>
        setTutorialNames(new Map(ts.map(t => [t.id, t.title])))
      )
      .catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function tName(id: string) {
    return tutorialNames.get(id) ?? id.slice(0, 8) + "…";
  }

  // Derived values
  const n = logs.length;
  const zeroResults = logs.filter(l => !l.steps_returned?.length).length;
  const zeroRate = n ? (zeroResults / n) * 100 : 0;
  const avgTotal = avg(logs.map(l => l.total_latency_ms));
  const allFb = logs.flatMap(l => l.feedback ?? []);
  const posFb = allFb.filter(f => f.helpful).length;
  const negFb = allFb.length - posFb;
  const fbPct = allFb.length ? (posFb / allFb.length) * 100 : null;

  const latencyRows = PHASES.map(({ name, key }) => {
    const vals = logs.map(l => l[key]).filter(v => v > 0);
    return { name, p50: pct(vals, 50), p95: pct(vals, 95), mean: avg(vals) };
  });
  const maxP95 = Math.max(...latencyRows.map(r => r.p95), 1);

  const allSteps = logs.flatMap(l => l.steps_returned ?? []);
  const distances = allSteps.map(s => s.distance).filter(Number.isFinite);
  const ceScores = allSteps.map(s => s.ce_score).filter(Number.isFinite);

  const tutorialCounts = new Map<string, number>();
  for (const log of logs) {
    for (const id of (log.tutorial_ids_searched ?? [])) {
      tutorialCounts.set(id, (tutorialCounts.get(id) ?? 0) + 1);
    }
  }
  const topTutorials = [...tutorialCounts.entries()].sort(([, a], [, b]) => b - a).slice(0, 10);

  const negByTutorial = new Map<string, string[]>();
  for (const log of logs) {
    if (!(log.feedback ?? []).some(f => !f.helpful)) continue;
    const key = log.tutorial_scoped ?? log.tutorial_ids_searched?.[0] ?? "unscoped";
    const arr = negByTutorial.get(key) ?? [];
    arr.push(log.query_text);
    negByTutorial.set(key, arr);
  }
  const negFeedback = [...negByTutorial.entries()].sort(([, a], [, b]) => b.length - a.length);

  const volumeData = byDay(logs);

  return (
    <div className="flex flex-col min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-10 flex items-center gap-3 px-4 h-14 border-b border-border/60 bg-background/90 backdrop-blur-sm shrink-0">
        <Link href="/" className="h-8 w-8 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-white/[0.06] transition-colors">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="flex items-center gap-2">
          <div className="relative h-6 w-6 flex items-center justify-center">
            <div className="absolute inset-0 rounded bg-primary/15" />
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="relative z-10">
              <path d="M2 3h10M2 7h7M2 11h4" stroke="#00ff88" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </div>
          <span className="font-semibold text-[15px] tracking-tight">Stepwise</span>
          <span className="text-muted-foreground/40 text-sm mx-0.5">/</span>
          <span className="text-sm text-muted-foreground">Admin</span>
        </div>
        <div className="flex-1" />
        <Link
          href="/gaps"
          className="flex items-center gap-1.5 h-8 px-3 rounded-lg border border-border/60 text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-white/[0.06] transition-colors"
        >
          <AlertTriangle className="h-3.5 w-3.5" />
          Coverage Gaps
        </Link>
        <div className="flex-1" />
        <div className="flex items-center gap-0.5 rounded-lg border border-border/50 bg-card p-0.5">
          {RANGES.map(r => (
            <button
              key={r}
              onClick={() => handleRangeChange(r)}
              className={cn(
                "px-2.5 py-1 rounded-md text-xs font-mono transition-colors",
                range === r ? "bg-white/[0.08] text-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {r}
            </button>
          ))}
        </div>

        {!loading && !error && (
          <span className="text-xs font-mono text-muted-foreground/40 hidden sm:block">{n.toLocaleString()} logs</span>
        )}
        <button onClick={() => fetchLogs()} disabled={refreshing} title="Refresh"
          className="h-8 w-8 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-white/[0.06] transition-colors disabled:opacity-40">
          <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
        </button>
      </header>

      <div className="flex-1 px-6 py-6 space-y-6 max-w-screen-xl mx-auto w-full">
        {loading && (
          <div className="space-y-3">
            {[56, 180, 160, 240].map((h, i) => <div key={i} className="rounded-xl skeleton w-full" style={{ height: h }} />)}
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-foreground/70">
            Failed to load query logs: {error}
          </div>
        )}

        {!loading && !error && (
          <>
            {/* ── Stats ── */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <StatCell label="Total queries" value={n.toLocaleString()} />
              <StatCell label="Zero-result rate" value={`${zeroRate.toFixed(1)}%`} sub={`${zeroResults} queries`} warn={zeroRate > 20} />
              <StatCell label="Avg total latency" value={fmtMs(avgTotal)} />
              <StatCell
                label="Feedback positive"
                value={fbPct !== null ? `${fbPct.toFixed(0)}%` : "—"}
                sub={allFb.length ? `${allFb.length} ratings` : "no ratings yet"}
              />
            </div>

            {/* ── Volume + Latency ── */}
            <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
              <Panel className="lg:col-span-3 px-4 pt-4 pb-3">
                <SectionHead>Query volume</SectionHead>
                {volumeData.length > 1
                  ? <BarChartSVG data={volumeData.map(d => ({ label: d.date, count: d.count }))} />
                  : <div className="h-32 flex items-center justify-center text-xs text-muted-foreground/40">Not enough data for a trend</div>
                }
              </Panel>

              <Panel className="lg:col-span-2 px-5 py-4">
                <SectionHead>Latency — P50 / P95</SectionHead>
                <div className="space-y-3">
                  {latencyRows.map(r => (
                    <div key={r.name}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-muted-foreground">{r.name}</span>
                        <span className="text-[10px] font-mono tabular-nums text-muted-foreground/50">
                          {fmtMs(r.p50)} / {fmtMs(r.p95)}
                        </span>
                      </div>
                      <div className="space-y-1">
                        <div className="relative h-2 rounded-sm overflow-hidden bg-white/[0.04]">
                          <div className="absolute inset-y-0 left-0 rounded-sm bg-primary/25 transition-all duration-500" style={{ width: `${(r.p50 / maxP95) * 100}%` }} />
                        </div>
                        <div className="relative h-2 rounded-sm overflow-hidden bg-white/[0.04]">
                          <div className="absolute inset-y-0 left-0 rounded-sm bg-primary/50 transition-all duration-500" style={{ width: `${(r.p95 / maxP95) * 100}%` }} />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-4 pt-3 border-t border-border/30">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-muted-foreground/50">
                        <th className="text-left font-normal pb-1">Phase</th>
                        <th className="text-right font-normal pb-1">P50</th>
                        <th className="text-right font-normal pb-1">P95</th>
                        <th className="text-right font-normal pb-1">Mean</th>
                      </tr>
                    </thead>
                    <tbody>
                      {latencyRows.map(r => (
                        <tr key={r.name} className="border-t border-border/20">
                          <td className="py-1 text-muted-foreground">{r.name}</td>
                          <td className="py-1 text-right font-mono tabular-nums">{fmtMs(r.p50)}</td>
                          <td className="py-1 text-right font-mono tabular-nums">{fmtMs(r.p95)}</td>
                          <td className="py-1 text-right font-mono tabular-nums text-muted-foreground/60">{fmtMs(r.mean)}</td>
                        </tr>
                      ))}
                      {(() => {
                        const totals = logs.map(l => l.total_latency_ms);
                        return (
                          <tr className="border-t border-border/40">
                            <td className="py-1 text-muted-foreground/50 text-[10px]">Total</td>
                            <td className="py-1 text-right font-mono tabular-nums text-[10px]">{fmtMs(pct(totals, 50))}</td>
                            <td className="py-1 text-right font-mono tabular-nums text-[10px]">{fmtMs(pct(totals, 95))}</td>
                            <td className="py-1 text-right font-mono tabular-nums text-[10px] text-muted-foreground/60">{fmtMs(avg(totals))}</td>
                          </tr>
                        );
                      })()}
                    </tbody>
                  </table>
                </div>
              </Panel>
            </div>

            {/* ── Histograms ── */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Panel className="px-4 pt-4 pb-3">
                <SectionHead>Distance distribution</SectionHead>
                <BarChartSVG data={histogram(distances, 10).map(b => ({ label: b.label, count: b.count }))} />
              </Panel>
              <Panel className="px-4 pt-4 pb-3">
                <SectionHead>CE score distribution</SectionHead>
                <BarChartSVG data={histogram(ceScores, 10).map(b => ({ label: b.label, count: b.count }))} />
              </Panel>
            </div>

            {/* ── Queries ── */}
            <div>
              <SectionHead>Recent queries</SectionHead>
              {n === 0
                ? <Panel className="px-6 py-12 text-center"><p className="text-sm text-muted-foreground">No query logs yet.</p></Panel>
                : <QueryTable logs={logs} />
              }
            </div>

            {/* ── Tutorial frequency + Feedback ── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 pb-6">
              <Panel>
                <div className="px-4 pt-4 pb-1">
                  <SectionHead>Most searched tutorials</SectionHead>
                </div>
                {topTutorials.length === 0
                  ? <div className="px-4 pb-4 text-xs text-muted-foreground/40">No data.</div>
                  : (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border/40 bg-white/[0.02]">
                          <th className="text-left px-4 py-2 text-xs text-muted-foreground font-medium">Tutorial</th>
                          <th className="text-right px-4 py-2 text-xs text-muted-foreground font-medium">Queries</th>
                          <th className="text-right px-4 py-2 text-xs text-muted-foreground font-medium">Share</th>
                        </tr>
                      </thead>
                      <tbody>
                        {topTutorials.map(([id, count], idx) => (
                          <tr key={id} className={cn("border-b border-border/30 last:border-0 hover:bg-white/[0.02] transition-colors", idx % 2 === 1 ? "bg-white/[0.01]" : "")}>
                            <td className="px-4 py-2 text-xs text-foreground/80 truncate max-w-[220px]" title={id}>{tName(id)}</td>
                            <td className="px-4 py-2 text-right font-mono text-sm tabular-nums">{count}</td>
                            <td className="px-4 py-2 text-right font-mono text-xs tabular-nums text-muted-foreground">
                              {n ? `${((count / n) * 100).toFixed(1)}%` : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )
                }
              </Panel>

              <Panel>
                <div className="px-4 pt-4 pb-1">
                  <SectionHead>Negative feedback by tutorial</SectionHead>
                </div>
                {negFeedback.length === 0 ? (
                  <div className="px-4 pb-4 text-xs text-muted-foreground/40">No negative feedback recorded.</div>
                ) : (
                  <>
                    {allFb.length > 0 && (
                      <div className="px-4 pb-3 flex items-center gap-3">
                        <div className="flex-1 h-1.5 rounded-sm overflow-hidden bg-white/[0.06]">
                          <div className="h-full rounded-sm bg-primary/40" style={{ width: `${fbPct}%` }} />
                        </div>
                        <span className="text-[11px] font-mono shrink-0">
                          <span className="text-primary/70">{posFb}↑</span>{" "}
                          <span className="text-destructive/70">{negFb}↓</span>
                        </span>
                      </div>
                    )}
                    <div className="divide-y divide-border/20">
                      {negFeedback.map(([tutorialId, queries]) => (
                        <div key={tutorialId} className="px-4 py-3">
                          <div className="flex items-center gap-2 mb-1.5">
                            <span className="text-xs text-foreground/70 truncate flex-1" title={tutorialId}>{tName(tutorialId)}</span>
                            <span className="shrink-0 inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded bg-destructive/10 text-destructive">
                              <ThumbsDown className="h-2.5 w-2.5" />{queries.length}
                            </span>
                          </div>
                          <ul className="space-y-0.5">
                            {queries.slice(0, 3).map((q, i) => (
                              <li key={i} className="text-[11px] text-muted-foreground/50 truncate flex items-center gap-1.5">
                                <span className="text-destructive/40 shrink-0">↓</span>{q}
                              </li>
                            ))}
                            {queries.length > 3 && (
                              <li className="text-[11px] text-muted-foreground/30 font-mono">+{queries.length - 3} more</li>
                            )}
                          </ul>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </Panel>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
