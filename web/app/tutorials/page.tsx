import Link from "next/link";
import { BookOpen, Plus, AlertTriangle, Rss } from "lucide-react";
import { TutorialList } from "./tutorial-list";
import { ActiveJobs } from "./active-jobs";

type Tutorial = {
  id: string;
  title: string;
  source_url: string;
  source_type: string;
  step_count: number;
  potential_duplicate_of: string | null;
};

async function getTutorials(): Promise<Tutorial[]> {
  const apiBase = process.env.API_BASE ?? "http://localhost:8000";
  const res = await fetch(`${apiBase}/tutorials`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

export default async function TutorialsPage() {
  const tutorials = await getTutorials();

  return (
    <div className="max-w-7xl mx-auto px-6 py-14">
      {/* Header */}
      <div className="flex items-start justify-between mb-10">
        <div className="animate-fade-up">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-primary/20 bg-primary/5 mb-4">
            <BookOpen className="h-3 w-3 text-primary" />
            <span className="text-xs font-mono text-primary font-medium">Knowledge Library</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight text-foreground mb-2">
            Indexed Tutorials
          </h1>
          <p className="text-muted-foreground">
            {tutorials.length === 0
              ? "No tutorials indexed yet — ingest one to get started."
              : `${tutorials.length} tutorial${tutorials.length !== 1 ? "s" : ""} in your knowledge base`}
          </p>
        </div>

        <div className="animate-fade-up animation-delay-100 flex items-center gap-2 mt-2">
          <Link href="/watchers" className="flex items-center gap-1.5 h-9 px-3 rounded-lg border border-border bg-card text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-white/[0.06] transition-all">
            <Rss className="h-3.5 w-3.5" />
            Watchers
          </Link>
          <Link href="/gaps" className="flex items-center gap-1.5 h-9 px-3 rounded-lg border border-border bg-card text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-white/[0.06] transition-all">
            <AlertTriangle className="h-3.5 w-3.5" />
            Gaps
          </Link>
          <Link href="/" className="flex items-center gap-1.5 h-9 px-4 rounded-lg border border-border bg-card text-sm font-medium text-foreground hover:bg-white/[0.06] hover:border-border/80 transition-all">
            <Plus className="h-3.5 w-3.5" />
            Ingest
          </Link>
        </div>
      </div>

      <ActiveJobs />

      {tutorials.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border/60 p-20 text-center animate-fade-up">
          <div className="h-12 w-12 rounded-xl bg-white/[0.04] border border-border/60 flex items-center justify-center mx-auto mb-4">
            <BookOpen className="h-5 w-5 text-muted-foreground" />
          </div>
          <p className="text-sm text-muted-foreground mb-4">
            Your knowledge base is empty.
          </p>
          <Link href="/"
            className="inline-flex items-center gap-1.5 h-9 px-4 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 transition-colors">
            <Plus className="h-3.5 w-3.5" />
            Ingest your first tutorial
          </Link>
        </div>
      ) : (
        <TutorialList tutorials={tutorials} />
      )}
    </div>
  );
}
