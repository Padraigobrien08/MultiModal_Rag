"use client";

import { PenSquare, Trash2, MessageSquare } from "lucide-react";

export type ConvSummary = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
};

type Props = {
  history: ConvSummary[];
  currentId: string | null;
  onNew: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
};

export function HistorySidebar({ history, currentId, onNew, onSelect, onDelete }: Props) {
  const now = Date.now();
  const groups = [
    { label: "Today",     items: history.filter(c => now - c.updatedAt < 86_400_000) },
    { label: "This week", items: history.filter(c => now - c.updatedAt >= 86_400_000 && now - c.updatedAt < 7 * 86_400_000) },
    { label: "Older",     items: history.filter(c => now - c.updatedAt >= 7 * 86_400_000) },
  ];

  return (
    <div className="flex flex-col h-full bg-background border-r border-border/60">
      {/* Header */}
      <div className="h-14 px-4 flex items-center justify-between shrink-0 border-b border-border/40">
        <span className="text-sm font-semibold text-foreground">History</span>
        <button
          onClick={onNew}
          className="h-7 w-7 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-white/[0.06] hover:text-foreground transition-colors"
          title="New chat"
        >
          <PenSquare className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto px-2 py-3 space-y-4 scrollbar-hide">
        {history.length === 0 && (
          <p className="text-[11px] text-muted-foreground/40 text-center py-10">No conversations yet</p>
        )}

        {groups.map(({ label, items }) =>
          items.length > 0 ? (
            <div key={label}>
              <p className="px-2 mb-1 text-[10px] font-mono uppercase tracking-wider text-muted-foreground/40">
                {label}
              </p>
              {items.map(conv => (
                <div
                  key={conv.id}
                  onClick={() => onSelect(conv.id)}
                  className={`group w-full text-left flex items-center gap-2 px-2 py-2 rounded-lg transition-colors cursor-pointer ${
                    conv.id === currentId
                      ? "bg-white/[0.08] text-foreground"
                      : "text-muted-foreground hover:bg-white/[0.04] hover:text-foreground"
                  }`}
                >
                  <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-40" />
                  <span className="flex-1 truncate text-xs">{conv.title}</span>
                  <button
                    onClick={e => { e.stopPropagation(); onDelete(conv.id); }}
                    className="opacity-0 group-hover:opacity-60 hover:!opacity-100 h-5 w-5 flex items-center justify-center hover:text-destructive transition-all shrink-0"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          ) : null
        )}
      </div>
    </div>
  );
}
