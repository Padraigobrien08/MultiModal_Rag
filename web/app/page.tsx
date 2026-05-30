"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { PanelLeft, BookOpen, Plus, ArrowUp, Clock, ExternalLink, Loader2, ThumbsUp, ThumbsDown, BarChart2, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { HistorySidebar, type ConvSummary } from "@/components/history-sidebar";
import { LibrarySidebar } from "@/components/library-sidebar";
import { IngestModal } from "@/components/ingest-modal";

// ── Types ─────────────────────────────────────────────────────────────────────

type StepResult = {
  step_number: number;
  step_id: string;
  tutorial_id: string;
  tutorial_title?: string;
  source_url?: string;
  source_type?: string;
  video_id?: string;
  timestamp_start: number | null;
  visual_reference: string | null;
  text: string;
};

type Message = {
  id: string;
  role: "user" | "assistant";
  text?: string;
  scopedTitle?: string;
  result?: { answer: string; steps: StepResult[] };
  error?: string;
  loading?: boolean;
  answerStreaming?: boolean;
};

// ── Conversation storage ──────────────────────────────────────────────────────

const HISTORY_KEY = "stepwise:convHistory";
const convKey = (id: string) => `stepwise:conv:${id}`;

function loadHistory(): ConvSummary[] {
  if (typeof window === "undefined") return [];
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); }
  catch { return []; }
}

function persistConversation(summary: ConvSummary, messages: Message[]) {
  const clean = messages.filter(m => !m.loading);
  localStorage.setItem(convKey(summary.id), JSON.stringify(clean));
  const history = loadHistory();
  const idx = history.findIndex(c => c.id === summary.id);
  if (idx >= 0) history[idx] = summary; else history.unshift(summary);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, 50)));
}

function loadMessages(id: string): Message[] {
  try { return JSON.parse(localStorage.getItem(convKey(id)) || "[]"); }
  catch { return []; }
}

function removeConversation(id: string) {
  localStorage.removeItem(convKey(id));
  localStorage.setItem(HISTORY_KEY, JSON.stringify(loadHistory().filter(c => c.id !== id)));
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeTitle(q: string): string {
  const clean = q.replace(/[?!.,]+$/, "").trim();
  if (clean.length <= 50) return clean;
  const cut = clean.slice(0, 50);
  const lastSpace = cut.lastIndexOf(" ");
  return (lastSpace > 20 ? cut.slice(0, lastSpace) : cut) + "…";
}

function fmtTime(secs: number) {
  const m = Math.floor(secs / 60), s = Math.floor(secs % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function videoUrl(step: StepResult): string | null {
  const ts = Math.round(step.timestamp_start ?? 0);
  if (step.source_type === "youtube" && step.video_id) return `https://youtu.be/${step.video_id}?t=${ts}`;
  if (step.source_url?.startsWith("http")) return step.source_url;
  return null;
}

// ── Resize handle + notch ─────────────────────────────────────────────────────

function ResizeHandle({ isOpen, onToggle, onResize }: {
  isOpen: boolean;
  onToggle: () => void;
  onResize: (delta: number) => void;
}) {
  const hasDragged = useRef(false);

  function handleMouseDown(e: React.MouseEvent) {
    if (!isOpen) return;
    hasDragged.current = false;
    e.preventDefault();

    function onMove(mv: MouseEvent) {
      hasDragged.current = true;
      onResize(mv.movementX);
    }
    function onUp() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }

  function handleClick() {
    if (!isOpen) onToggle();
    else if (!hasDragged.current) onToggle();
  }

  return (
    <div
      onMouseDown={handleMouseDown}
      onClick={handleClick}
      className={cn(
        "relative flex-shrink-0 w-[5px] flex items-center justify-center group",
        "hover:bg-primary/10 transition-colors duration-150 z-10",
        isOpen ? "cursor-col-resize" : "cursor-pointer"
      )}
      title={isOpen ? "Drag to resize · Click to close" : "Open sidebar"}
    >
      {/* The notch pill — always visible, positioned at vertical center */}
      <div className="absolute top-1/2 -translate-y-1/2 h-10 w-[3px] rounded-full bg-border/50 group-hover:bg-primary/60 transition-colors duration-150" />
    </div>
  );
}

// ── Step card ─────────────────────────────────────────────────────────────────

function StepCard({ step, index, query }: { step: StepResult; index: number; query?: string }) {
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  const url = videoUrl(step);
  const ts = step.timestamp_start !== null ? fmtTime(step.timestamp_start) : null;

  async function sendFeedback(helpful: boolean) {
    const next = helpful ? "up" : "down";
    setFeedback(next);
    await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: query ?? "", step_id: step.step_id, helpful }),
    }).catch(() => {});
  }

  return (
    <div className="rounded-xl border border-border/50 bg-card overflow-hidden animate-fade-up"
      style={{ animationDelay: `${index * 60}ms` }}>
      <div className="flex items-center gap-2.5 px-4 py-2.5 border-b border-border/40 bg-white/[0.02]">
        <span className="text-[11px] font-mono font-semibold text-primary bg-primary/10 px-1.5 py-0.5 rounded">
          {index + 1}
        </span>
        <span className="text-xs text-muted-foreground truncate flex-1">
          {step.tutorial_title ?? "Tutorial"}
        </span>
        {url && ts && (
          <a href={url} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1 text-[11px] font-mono text-muted-foreground/50 hover:text-primary transition-colors shrink-0">
            <Clock className="h-3 w-3" />{ts}<ExternalLink className="h-2.5 w-2.5" />
          </a>
        )}
      </div>
      {step.visual_reference && (
        <div className="border-b border-border/40">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={`/api/frame?path=${encodeURIComponent(step.visual_reference)}`}
            alt={`Step ${step.step_number}`} className="w-full object-cover max-h-52" />
        </div>
      )}
      <div className="group/card px-4 py-3 flex items-start gap-3">
        <p className="text-sm text-foreground/80 leading-relaxed flex-1">{step.text}</p>
        <div className={cn("flex gap-1 shrink-0 mt-0.5 transition-opacity duration-150", feedback ? "opacity-100" : "opacity-0 group-hover/card:opacity-100")}>
          <button onClick={() => sendFeedback(true)}
            className={cn("h-6 w-6 rounded flex items-center justify-center transition-colors",
              feedback === "up" ? "text-primary bg-primary/10" : "text-muted-foreground/40 hover:text-primary hover:bg-primary/10")}
            title="Helpful">
            <ThumbsUp className="h-3 w-3" />
          </button>
          <button onClick={() => sendFeedback(false)}
            className={cn("h-6 w-6 rounded flex items-center justify-center transition-colors",
              feedback === "down" ? "text-destructive bg-destructive/10" : "text-muted-foreground/40 hover:text-destructive hover:bg-destructive/10")}
            title="Not helpful">
            <ThumbsDown className="h-3 w-3" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Assistant message ─────────────────────────────────────────────────────────

function AssistantMessage({ msg, query }: { msg: Message; query?: string }) {
  if (msg.loading) return (
    <div className="flex items-center gap-2 py-2">
      <Loader2 className="h-3.5 w-3.5 text-primary animate-spin" />
      <span className="text-xs text-muted-foreground animate-pulse">Searching knowledge base…</span>
    </div>
  );
  if (msg.error) return (
    <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-foreground/70">{msg.error}</div>
  );
  if (!msg.result) return null;
  const { answer, steps } = msg.result;
  if (!steps.length) return (
    <div className="rounded-xl border border-border/50 bg-card px-4 py-5 text-sm text-muted-foreground">
      No relevant steps found. Try rephrasing or adding more content to your library.
    </div>
  );
  return (
    <div className="space-y-3">
      {/* Synthesised answer — streams in above the cards */}
      {(answer || msg.answerStreaming) && (
        <p className="text-sm text-foreground/80 leading-relaxed px-1">
          {answer}
          {msg.answerStreaming && (
            <span className="inline-block w-0.5 h-3.5 bg-primary ml-0.5 animate-pulse align-middle" />
          )}
        </p>
      )}
      {steps.map((step, i) => <StepCard key={step.step_id} step={step} index={i} query={query} />)}
    </div>
  );
}

// ── Admin gateway ─────────────────────────────────────────────────────────────

function AdminGateway() {
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    fetch("/api/admin/stats")
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setCount(d.queries_24h); })
      .catch(() => {});
  }, []);

  return (
    <Link
      href="/admin"
      className={cn(
        "h-8 flex items-center gap-1.5 px-2.5 rounded-lg transition-colors",
        "text-muted-foreground hover:text-foreground hover:bg-white/[0.06]",
      )}
      title="Admin dashboard"
    >
      <BarChart2 className="h-3.5 w-3.5 shrink-0" />
      {count !== null && count > 0 && (
        <span className="text-[11px] font-mono tabular-nums">{count}</span>
      )}
    </Link>
  );
}

// ── Example prompts ───────────────────────────────────────────────────────────

const EXAMPLES = [
  "How do I configure an API key?",
  "How do I invite a team member?",
  "How do I issue a refund?",
];

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Page() {
  // Both sidebars open by default
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [leftWidth, setLeftWidth] = useState(256);
  const [rightWidth, setRightWidth] = useState(288);

  const [ingestOpen, setIngestOpen] = useState(false);
  const [libraryRefreshKey, setLibraryRefreshKey] = useState(0);

  const [history, setHistory] = useState<ConvSummary[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [scoped, setScoped] = useState<{ id: string; title: string } | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const currentIdRef = useRef<string | null>(null);
  const messagesRef = useRef<Message[]>([]);

  useEffect(() => { setHistory(loadHistory()); }, []);

  // Auto-scope when arriving from the tutorials page via /?tutorial_id=...
  useEffect(() => {
    const tid = new URLSearchParams(window.location.search).get("tutorial_id");
    if (!tid) return;
    fetch(`/api/tutorials/${tid}`)
      .then(r => r.ok ? r.json() : null)
      .then(t => { if (t?.id) setScoped({ id: t.id, title: t.title }); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    currentIdRef.current = currentId;
    messagesRef.current = messages;
  }, [currentId, messages]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  function startNew() { setCurrentId(null); setMessages([]); setScoped(null); }

  function selectConv(id: string) { setCurrentId(id); setMessages(loadMessages(id)); }

  function deleteConv(id: string) {
    removeConversation(id); setHistory(loadHistory());
    if (currentId === id) startNew();
  }

  function handleInputChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }

  async function submit(question: string) {
    const q = question.trim();
    if (!q) return;

    let convId = currentIdRef.current;
    let isNew = false;
    if (!convId) { convId = crypto.randomUUID(); isNew = true; setCurrentId(convId); currentIdRef.current = convId; }

    const userMsg: Message = { id: crypto.randomUUID(), role: "user", text: q, scopedTitle: scoped?.title };
    const pendingId = crypto.randomUUID();
    const next = [...messagesRef.current, userMsg, { id: pendingId, role: "assistant" as const, loading: true }];
    setMessages(next); messagesRef.current = next;
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    try {
      // Build history: last 6 messages (3 exchanges) before the pending placeholder
      const historyMsgs = messagesRef.current
        .filter(m => !m.loading && (m.text || m.result?.answer))
        .slice(-6)
        .map(m => ({ role: m.role, text: m.text ?? m.result?.answer ?? "" }));

      const res = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, tutorial_id: scoped?.id, top_k: 5, history: historyMsgs }),
      });
      if (!res.ok) throw new Error("Query failed");

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        // Process all complete SSE lines
        const parts = buf.split("\n");
        buf = parts.pop() ?? "";

        for (const line of parts) {
          if (!line.startsWith("data: ")) continue;
          const evt = JSON.parse(line.slice(6));

          if (evt.type === "steps") {
            setMessages(prev => prev.map(m =>
              m.id === pendingId
                ? { ...m, loading: false, answerStreaming: true, result: { answer: "", steps: evt.steps } }
                : m
            ));
          } else if (evt.type === "token") {
            setMessages(prev => prev.map(m =>
              m.id === pendingId && m.result
                ? { ...m, result: { ...m.result, answer: m.result.answer + evt.text } }
                : m
            ));
          } else if (evt.type === "done") {
            setMessages(prev => {
              const updated = prev.map(m =>
                m.id === pendingId ? { ...m, answerStreaming: false } : m
              );
              const createdAt = isNew ? Date.now() : (loadHistory().find(c => c.id === convId)?.createdAt ?? Date.now());
              persistConversation({ id: convId!, title: makeTitle(q), createdAt, updatedAt: Date.now() }, updated);
              setHistory(loadHistory());
              return updated;
            });
          }
        }
      }
    } catch (err) {
      setMessages(prev => prev.map(m =>
        m.id === pendingId ? { ...m, loading: false, error: err instanceof Error ? err.message : "Something went wrong" } : m
      ));
    }
  }

  return (
    <div className="flex flex-col h-screen">
      {/* ── Header ── */}
      <header className="flex items-center gap-3 px-4 h-14 border-b border-border/60 bg-background/80 backdrop-blur-sm shrink-0">
        <button
          onClick={() => setLeftOpen(v => !v)}
          className={cn("h-8 w-8 rounded-lg flex items-center justify-center transition-colors",
            leftOpen ? "bg-white/[0.08] text-foreground" : "text-muted-foreground hover:bg-white/[0.06] hover:text-foreground")}
          title="History"
        >
          <PanelLeft className="h-4 w-4" />
        </button>

        <div className="flex items-center gap-2">
          <div className="relative h-6 w-6 flex items-center justify-center">
            <div className="absolute inset-0 rounded bg-primary/15" />
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="relative z-10">
              <path d="M2 3h10M2 7h7M2 11h4" stroke="#00ff88" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </div>
          <span className="font-semibold text-[15px] tracking-tight">Stepwise</span>
        </div>

        <div className="flex-1" />

        {scoped && (
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-primary/30 bg-primary/5 text-xs text-primary max-w-[180px]">
            <span className="truncate">{scoped.title}</span>
            <button onClick={() => setScoped(null)} className="shrink-0 opacity-60 hover:opacity-100">×</button>
          </div>
        )}

        <AdminGateway />
        <Link
          href="/gaps"
          className={cn(
            "h-8 flex items-center gap-1.5 px-2.5 rounded-lg transition-colors",
            "text-muted-foreground hover:text-foreground hover:bg-white/[0.06]",
          )}
          title="Coverage gaps"
        >
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
        </Link>

        {/* "View Library" button — explicit label */}
        <button
          onClick={() => setRightOpen(v => !v)}
          className={cn(
            "h-8 flex items-center gap-1.5 px-3 rounded-lg text-sm font-medium transition-colors",
            rightOpen ? "bg-white/[0.08] text-foreground" : "text-muted-foreground hover:bg-white/[0.06] hover:text-foreground"
          )}
        >
          <BookOpen className="h-3.5 w-3.5" />
          <span>View Library</span>
        </button>

        <button
          onClick={() => setIngestOpen(true)}
          className="h-8 flex items-center gap-1.5 px-3 rounded-lg bg-primary text-black text-sm font-semibold hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" /><span>Add</span>
        </button>
      </header>

      {/* ── Body ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* History sidebar */}
        <div
          style={{ width: leftOpen ? leftWidth : 0 }}
          className="flex-shrink-0 overflow-hidden transition-[width] duration-200 ease-in-out"
        >
          <div style={{ width: leftWidth }} className="h-full">
            <HistorySidebar history={history} currentId={currentId} onNew={startNew} onSelect={selectConv} onDelete={deleteConv} />
          </div>
        </div>

        {/* Left resize handle + notch */}
        <ResizeHandle
          isOpen={leftOpen}
          onToggle={() => setLeftOpen(v => !v)}
          onResize={delta => setLeftWidth(w => Math.max(180, Math.min(440, w + delta)))}
        />

        {/* Chat */}
        <main className="flex-1 flex flex-col overflow-hidden min-w-0 relative">
          {/* Click-outside overlay */}
          {(leftOpen || rightOpen) && (
            <div className="absolute inset-0 z-10 md:hidden"
              onClick={() => { setLeftOpen(false); setRightOpen(false); }} />
          )}

          <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-hide">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full gap-8 px-6 animate-fade-up">
                <div className="text-center">
                  <div className="h-10 w-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center mx-auto mb-4">
                    <svg width="18" height="18" viewBox="0 0 14 14" fill="none">
                      <path d="M2 3h10M2 7h7M2 11h4" stroke="#00ff88" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                  </div>
                  <h2 className="text-xl font-semibold mb-1.5">Ask anything</h2>
                  <p className="text-sm text-muted-foreground max-w-xs leading-relaxed">
                    Stepwise searches your tutorial library and returns cited, step-by-step answers.
                  </p>
                </div>
                <div className="flex flex-col gap-2 w-full max-w-sm">
                  {EXAMPLES.map(ex => (
                    <button key={ex} onClick={() => submit(ex)}
                      className="text-left text-sm text-muted-foreground px-4 py-2.5 rounded-lg border border-border/50 hover:border-primary/30 hover:text-foreground hover:bg-white/[0.03] transition-all">
                      {ex}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="max-w-2xl mx-auto px-4 py-6 space-y-6">
                {messages.map((msg, idx) => (
                  <div key={msg.id}>
                    {msg.role === "user" ? (
                      <div className="flex justify-end">
                        <div className="max-w-[80%]">
                          {msg.scopedTitle && (
                            <p className="text-right text-[10px] text-primary/50 mb-1 pr-1 truncate">
                              Scoped to: {msg.scopedTitle}
                            </p>
                          )}
                          <div className="bg-white/[0.06] border border-border/40 rounded-2xl px-4 py-2.5 text-sm">{msg.text}</div>
                        </div>
                      </div>
                    ) : (
                      <div className="flex gap-3">
                        <div className="h-6 w-6 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0 mt-0.5">
                          <svg width="10" height="10" viewBox="0 0 14 14" fill="none">
                            <path d="M2 3h10M2 7h7M2 11h4" stroke="#00ff88" strokeWidth="1.5" strokeLinecap="round" />
                          </svg>
                        </div>
                        <div className="flex-1 min-w-0 pt-0.5"><AssistantMessage msg={msg} query={messages[idx - 1]?.text} /></div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Input */}
          <div className="border-t border-border/60 bg-background/80 backdrop-blur-sm px-4 py-4 shrink-0">
            <div className="max-w-2xl mx-auto">
              <div className="flex items-end gap-3 rounded-xl border border-border/60 bg-card px-4 py-3 focus-within:border-primary/40 transition-colors">
                <textarea ref={textareaRef} rows={1}
                  placeholder={scoped ? `Ask about "${scoped.title}"…` : "Ask about your tutorials…"}
                  value={input} onChange={handleInputChange}
                  onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(input); } }}
                  className="flex-1 bg-transparent text-sm placeholder:text-muted-foreground/40 resize-none outline-none leading-relaxed"
                  style={{ minHeight: "24px", maxHeight: "160px" }} />
                <button onClick={() => submit(input)} disabled={!input.trim()}
                  className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center shrink-0 hover:bg-primary/90 disabled:opacity-30 disabled:cursor-not-allowed transition-all mb-0.5">
                  <ArrowUp className="h-4 w-4 text-black" />
                </button>
              </div>
              <p className="text-center text-[11px] text-muted-foreground/40 mt-2">Enter↵ to send · Shift+Enter for new line</p>
            </div>
          </div>
        </main>

        {/* Right resize handle + notch */}
        <ResizeHandle
          isOpen={rightOpen}
          onToggle={() => setRightOpen(v => !v)}
          onResize={delta => setRightWidth(w => Math.max(220, Math.min(500, w - delta)))}
        />

        {/* Library sidebar */}
        <div
          style={{ width: rightOpen ? rightWidth : 0 }}
          className="flex-shrink-0 overflow-hidden transition-[width] duration-200 ease-in-out"
        >
          <div style={{ width: rightWidth }} className="h-full">
            <LibrarySidebar onClose={() => setRightOpen(false)} scopedId={scoped?.id ?? null} onScopeTutorial={setScoped} refreshKey={libraryRefreshKey} />
          </div>
        </div>
      </div>

      {ingestOpen && (
        <IngestModal onClose={() => { setIngestOpen(false); setLibraryRefreshKey(k => k + 1); }} />
      )}
    </div>
  );
}
