import Link from "next/link";
import { ArrowLeft, Clock, ExternalLink, ImageIcon, MessageSquare } from "lucide-react";
import { notFound } from "next/navigation";
import { EmbeddedVideos } from "./embedded-videos";
import { fetchBackend } from "@/lib/backend";

type Step = {
  id: string;
  step_number: number;
  title: string;
  description: string;
  action_type: string | null;
  visual_reference: string | null;
  timestamp_start: number | null;
  confidence_score: number | null;
};

type Tutorial = {
  id: string;
  title: string;
  source_url: string;
  source_type: string;
  meta: { embedded_video_urls?: string[] } | null;
  steps: Step[];
};

const ACTION_STYLE: Record<string, { border: string; text: string; bg: string }> = {
  click:     { border: "border-sky-500/30",    text: "text-sky-400",    bg: "bg-sky-500/5"    },
  configure: { border: "border-primary/30",    text: "text-primary",    bg: "bg-primary/5"    },
  navigate:  { border: "border-amber-500/30",  text: "text-amber-400",  bg: "bg-amber-500/5"  },
  explain:   { border: "border-slate-500/30",  text: "text-slate-400",  bg: "bg-slate-500/5"  },
  verify:    { border: "border-orange-500/30", text: "text-orange-400", bg: "bg-orange-500/5" },
};

async function getTutorial(id: string): Promise<Tutorial | null> {
  const res = await fetchBackend(`/tutorials/${id}`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("Failed to fetch tutorial");
  return res.json();
}

function fmt(s: number) {
  const m = Math.floor(s / 60);
  return `${m}:${Math.floor(s % 60).toString().padStart(2, "0")}`;
}

export default async function TutorialDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const tutorial = await getTutorial(id);
  if (!tutorial) notFound();

  return (
    <div className="max-w-4xl mx-auto px-6 py-12">
      {/* Back */}
      <Link
        href="/tutorials"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mb-8 animate-fade-up"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Library
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between gap-6 mb-10 animate-fade-up animation-delay-100">
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground mb-2 leading-tight">
            {tutorial.title}
          </h1>
          {!tutorial.source_url.startsWith("images://") && (
            <a
              href={tutorial.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-primary transition-colors font-mono"
            >
              {tutorial.source_url}
              <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <div className="px-3 py-1.5 rounded-lg border border-border/60 bg-card text-xs font-mono text-muted-foreground">
            {tutorial.steps.length} steps
          </div>
          <Link
            href={`/query?tutorial_id=${tutorial.id}`}
            className="flex items-center gap-1.5 h-8 px-3 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-colors"
          >
            <MessageSquare className="h-3.5 w-3.5" />
            Query
          </Link>
        </div>
      </div>

      {/* Embedded videos from Notion */}
      {tutorial.meta?.embedded_video_urls?.length ? (
        <EmbeddedVideos urls={tutorial.meta.embedded_video_urls} />
      ) : null}

      {/* Steps */}
      <div className="relative">
        {/* Vertical timeline line */}
        <div className="absolute left-5 top-6 bottom-6 w-px bg-border/60" />

        <div className="space-y-4">
          {tutorial.steps.map((step, i) => {
            const action = step.action_type ? (ACTION_STYLE[step.action_type] ?? ACTION_STYLE.explain) : null;
            return (
              <div
                key={step.id}
                className="relative flex gap-5 animate-fade-up"
                style={{ animationDelay: `${Math.min(i * 30, 400)}ms` }}
              >
                {/* Node */}
                <div className="shrink-0 h-10 w-10 rounded-full border border-border/80 bg-card flex items-center justify-center z-10 text-xs font-mono font-semibold text-muted-foreground group-hover:border-primary/40 transition-colors">
                  {step.step_number}
                </div>

                {/* Card */}
                <div className="flex-1 rounded-xl border border-border/60 bg-card p-4 hover:border-border transition-colors mb-1">
                  <div className="flex gap-4">
                    {/* Screenshot */}
                    <div className="shrink-0" style={{ width: 112, height: 72 }}>
                      {step.visual_reference ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={`/api/frame?path=${encodeURIComponent(step.visual_reference)}`}
                          alt={`Step ${step.step_number}`}
                          className="w-full h-full object-cover rounded-lg border border-border/60"
                        />
                      ) : (
                        <div className="w-full h-full rounded-lg border border-border/40 bg-muted/20 flex items-center justify-center">
                          <ImageIcon className="h-4 w-4 text-muted-foreground/30" />
                        </div>
                      )}
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                        <span className="font-semibold text-sm text-foreground">{step.title}</span>
                        {action && step.action_type && (
                          <span className={`text-[10px] font-mono font-medium px-2 py-0.5 rounded-full border ${action.border} ${action.text} ${action.bg}`}>
                            {step.action_type}
                          </span>
                        )}
                        {step.timestamp_start !== null && (
                          <span className="flex items-center gap-1 text-[11px] font-mono text-muted-foreground/50 ml-auto">
                            <Clock className="h-3 w-3" />
                            {fmt(step.timestamp_start)}
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground leading-relaxed">
                        {step.description}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
