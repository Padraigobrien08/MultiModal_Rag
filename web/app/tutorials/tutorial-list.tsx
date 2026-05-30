"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, ExternalLink, MessageSquare, Search, Play, ImageIcon as ImgIcon } from "lucide-react";
import { Input } from "@/components/ui/input";
import { TutorialActionsMenu } from "./actions-menu";

type Tutorial = {
  id: string;
  title: string;
  source_url: string;
  source_type: string;
  step_count: number;
  potential_duplicate_of: string | null;
};

export function TutorialList({ tutorials }: { tutorials: Tutorial[] }) {
  const [query, setQuery] = useState("");

  const filtered = query.trim()
    ? tutorials.filter(t =>
        t.title.toLowerCase().includes(query.toLowerCase()) ||
        t.source_url.toLowerCase().includes(query.toLowerCase())
      )
    : tutorials;

  return (
    <div>
      {/* Search */}
      <div className="relative mb-6 max-w-sm animate-fade-up">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/50" />
        <Input
          placeholder="Search tutorials..."
          value={query}
          onChange={e => setQuery(e.target.value)}
          className="pl-9 bg-card border-border/60 focus:border-primary/50 text-sm h-9"
        />
      </div>

      {filtered.length === 0 && query ? (
        <div className="rounded-xl border border-dashed border-border/60 py-16 text-center">
          <p className="text-sm text-muted-foreground">No tutorials match &ldquo;{query}&rdquo;</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((t, i) => (
            <TutorialCard key={t.id} tutorial={t} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}

function TutorialCard({ tutorial: t, index }: { tutorial: Tutorial; index: number }) {
  const isImage = t.source_type === "images";

  return (
    <div
      className="group relative rounded-xl border border-border/60 bg-card p-5 flex flex-col gap-3 card-hover animate-fade-up"
      style={{ animationDelay: `${Math.min(index * 50, 300)}ms` }}
    >
      {/* Source icon + type */}
      <div className="flex items-center justify-between">
        <div className={`h-8 w-8 rounded-lg flex items-center justify-center ${
          isImage ? "bg-cyan-500/10" : "bg-red-500/10"
        }`}>
          {isImage
            ? <ImgIcon className="h-4 w-4 text-cyan-400" />
            : <Play className="h-4 w-4 text-red-400" />}
        </div>
        <span className={`text-[11px] font-mono font-medium px-2 py-0.5 rounded-full border ${
          isImage
            ? "border-cyan-500/20 text-cyan-400 bg-cyan-500/5"
            : "border-red-500/20 text-red-400 bg-red-500/5"
        }`}>
          {t.source_type}
        </span>
      </div>

      {/* Title */}
      <div className="flex-1">
        <div className="flex items-start gap-1.5">
          <Link
            href={`/tutorials/${t.id}`}
            className="font-semibold text-sm text-foreground hover:text-primary transition-colors line-clamp-2 leading-snug"
          >
            {t.title}
          </Link>
          {t.potential_duplicate_of && (
            <span title="Possible duplicate — consider removing">
              <AlertTriangle className="h-3 w-3 text-yellow-500 shrink-0 mt-0.5" />
            </span>
          )}
        </div>
        <p className="text-[11px] text-muted-foreground/50 mt-1 truncate font-mono">
          {t.source_url.replace("images://", "")}
        </p>
      </div>

      {/* Step count */}
      <div className="flex items-center justify-between pt-3 border-t border-border/50">
        <div className="flex items-center gap-1.5">
          <div className="h-1.5 w-1.5 rounded-full bg-primary/60" />
          <span className="text-xs font-mono text-muted-foreground">
            <span className="text-foreground font-semibold">{t.step_count}</span> steps
          </span>
        </div>

        {/* Actions — visible on hover */}
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <Link
            href={`/?tutorial_id=${t.id}`}
            className="h-7 w-7 rounded-md border border-border/60 bg-background flex items-center justify-center text-muted-foreground hover:text-primary hover:border-primary/40 transition-all"
            title="Query this tutorial"
          >
            <MessageSquare className="h-3.5 w-3.5" />
          </Link>
          {!t.source_url.startsWith("images://") && (
            <a
              href={t.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="h-7 w-7 rounded-md border border-border/60 bg-background flex items-center justify-center text-muted-foreground hover:text-primary hover:border-primary/40 transition-all"
              title="Open source"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
          <TutorialActionsMenu tutorialId={t.id} />
        </div>
      </div>
    </div>
  );
}
