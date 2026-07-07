"use client";

import { useEffect, useRef, useState } from "react";
import { Boxes, Check, Plus, ChevronDown, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export type Library = { id: string; name: string };

type Props = {
  libraryId: string;
  onSelect: (id: string) => void;
};

/** Header control to switch the active workspace (library) and create new ones. */
export function WorkspaceSelector({ libraryId, onSelect }: Props) {
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  async function fetchLibraries() {
    try {
      const res = await fetch("/api/libraries", { cache: "no-store" });
      if (res.ok) setLibraries(await res.json());
    } catch {}
  }

  useEffect(() => { void Promise.resolve().then(() => fetchLibraries()); }, []);

  // Close on outside click.
  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  async function createWorkspace() {
    const name = newName.trim();
    if (!name) return;
    setCreating(true);
    try {
      const res = await fetch("/api/libraries", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (res.ok) {
        const lib = await res.json();
        setNewName("");
        await fetchLibraries();
        onSelect(lib.id);
        setOpen(false);
      }
    } catch {} finally {
      setCreating(false);
    }
  }

  const active = libraries.find(l => l.id === libraryId);

  return (
    <div ref={rootRef} className="relative">
      <button
        onClick={() => setOpen(v => !v)}
        className={cn(
          "h-8 flex items-center gap-1.5 px-2.5 rounded-lg text-sm transition-colors max-w-[180px]",
          open ? "bg-white/[0.08] text-foreground" : "text-muted-foreground hover:bg-white/[0.06] hover:text-foreground",
        )}
        title="Switch workspace"
      >
        <Boxes className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate">{active?.name ?? "Local"}</span>
        <ChevronDown className="h-3 w-3 shrink-0 opacity-60" />
      </button>

      {open && (
        <div className="absolute right-0 mt-1.5 w-60 z-50 rounded-xl border border-border/60 bg-card shadow-2xl p-1.5">
          <p className="px-2 py-1 text-[10px] font-mono uppercase tracking-wider text-muted-foreground/40">
            Workspaces
          </p>
          <div className="max-h-64 overflow-y-auto scrollbar-hide">
            {libraries.map(lib => (
              <button
                key={lib.id}
                onClick={() => { onSelect(lib.id); setOpen(false); }}
                className={cn(
                  "w-full flex items-center gap-2 px-2 py-2 rounded-lg text-left text-sm transition-colors",
                  lib.id === libraryId ? "text-foreground" : "text-muted-foreground hover:bg-white/[0.04] hover:text-foreground",
                )}
              >
                <span className="flex-1 truncate">{lib.name}</span>
                {lib.id === libraryId && <Check className="h-3.5 w-3.5 text-primary shrink-0" />}
              </button>
            ))}
          </div>

          <div className="mt-1 pt-1.5 border-t border-border/40 flex items-center gap-1.5 px-1">
            <input
              type="text"
              placeholder="New workspace…"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === "Enter" && createWorkspace()}
              className="flex-1 bg-background border border-border/60 rounded-md px-2 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/40 focus:border-primary/50 focus:outline-none"
            />
            <button
              onClick={createWorkspace}
              disabled={!newName.trim() || creating}
              className="h-7 w-7 shrink-0 rounded-md bg-primary text-black flex items-center justify-center hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              title="Create workspace"
            >
              {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
