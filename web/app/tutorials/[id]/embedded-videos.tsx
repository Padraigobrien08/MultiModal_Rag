"use client";

import { useState } from "react";
import { Play, Video, Loader2, Check, AlertCircle, Plus } from "lucide-react";

type Status = "idle" | "loading" | "done" | "exists" | "error";

function VideoRow({ url }: { url: string }) {
  const [status, setStatus] = useState<Status>("idle");

  const isYouTube = url.includes("youtube.com") || url.includes("youtu.be");

  async function ingest() {
    setStatus("loading");
    try {
      const res = await fetch("/api/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Failed");
      setStatus(data.existing ? "exists" : "done");
    } catch {
      setStatus("error");
    }
  }

  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-primary/10 last:border-0">
      <span className="text-primary/40 shrink-0">
        {isYouTube
          ? <Play className="h-3.5 w-3.5" />
          : <Video className="h-3.5 w-3.5" />}
      </span>

      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-xs font-mono text-muted-foreground hover:text-primary transition-colors flex-1 truncate"
        title={url}
      >
        {url}
      </a>

      <button
        onClick={ingest}
        disabled={status !== "idle"}
        className={`shrink-0 flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-xs font-medium transition-colors ${
          status === "idle"
            ? "border border-border/60 text-muted-foreground hover:text-foreground hover:bg-white/[0.06]"
            : status === "loading"
            ? "border border-border/40 text-muted-foreground/40 cursor-wait"
            : status === "done"
            ? "bg-primary/10 text-primary border border-primary/20"
            : status === "exists"
            ? "bg-white/[0.04] text-muted-foreground/50 border border-border/40 cursor-default"
            : "bg-destructive/10 text-destructive border border-destructive/20"
        }`}
        title={status === "exists" ? "Already in library" : undefined}
      >
        {status === "idle"    && <><Plus className="h-3 w-3" />Add</>}
        {status === "loading" && <><Loader2 className="h-3 w-3 animate-spin" />Adding…</>}
        {status === "done"    && <><Check className="h-3 w-3" />Queued</>}
        {status === "exists"  && <><Check className="h-3 w-3" />In library</>}
        {status === "error"   && <><AlertCircle className="h-3 w-3" />Failed</>}
      </button>
    </div>
  );
}

export function EmbeddedVideos({ urls }: { urls: string[] }) {
  return (
    <div className="rounded-xl border border-primary/15 bg-primary/[0.03] px-5 pt-4 pb-1 mb-8 animate-fade-up animation-delay-150">
      <p className="text-[11px] font-mono font-medium text-primary/60 uppercase tracking-wider mb-2">
        Videos found in this Notion page
      </p>
      {urls.map(url => <VideoRow key={url} url={url} />)}
    </div>
  );
}
