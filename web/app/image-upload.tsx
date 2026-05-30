"use client";

import { useState, useRef, useCallback } from "react";
import { Input } from "@/components/ui/input";
import { Loader2, Upload, X, FileImage, ArrowRight } from "lucide-react";

const ACCEPTED = ["image/jpeg","image/png","image/webp","image/gif","application/zip","application/x-zip-compressed"];

type Props = {
  onJobStarted: (jobId: string, createdAt: string) => void;
  disabled: boolean;
};

export function ImageUpload({ onJobStarted, disabled }: Props) {
  const [title, setTitle]       = useState("");
  const [files, setFiles]       = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]       = useState("");
  const fileInputRef   = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const addFiles = useCallback((incoming: FileList | File[]) => {
    const arr = Array.from(incoming).filter(f => ACCEPTED.includes(f.type) || f.name.endsWith(".zip"));
    setFiles(prev => {
      const names = new Set(prev.map(f => f.name));
      return [...prev, ...arr.filter(f => !names.has(f.name))];
    });
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!files.length || !title.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("title", title.trim());
      files.forEach(f => fd.append("files", f));
      const res = await fetch("/api/ingest/images", { method: "POST", body: fd });
      if (!res.ok) { const d = await res.json(); setError(d.detail ?? "Failed"); return; }
      const { job_id } = await res.json();
      onJobStarted(job_id, new Date().toISOString());
      setFiles([]); setTitle("");
    } finally {
      setSubmitting(false);
    }
  }

  const isDisabled = disabled || submitting;

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Input
        placeholder="Tutorial title (e.g. Setting up Stripe)"
        value={title}
        onChange={e => setTitle(e.target.value)}
        disabled={isDisabled}
        className="bg-background border-border/60 focus:border-primary/50 text-sm h-10"
      />

      {/* Drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => { e.preventDefault(); setDragging(false); e.dataTransfer.files.length && addFiles(e.dataTransfer.files); }}
        onClick={() => fileInputRef.current?.click()}
        className={`relative rounded-lg border-2 border-dashed p-8 text-center transition-all cursor-pointer ${
          dragging ? "border-primary bg-primary/5" : "border-border/50 hover:border-border hover:bg-white/[0.02]"
        } ${isDisabled ? "opacity-50 pointer-events-none" : ""}`}
      >
        <div className={`h-10 w-10 rounded-lg mx-auto mb-3 flex items-center justify-center transition-colors ${
          dragging ? "bg-primary/15" : "bg-white/[0.05]"
        }`}>
          <Upload className={`h-5 w-5 ${dragging ? "text-primary" : "text-muted-foreground"}`} />
        </div>
        <p className="text-sm font-medium text-foreground mb-1">Drop images or a ZIP</p>
        <p className="text-xs text-muted-foreground">JPG · PNG · WEBP · ZIP supported</p>
        <input ref={fileInputRef} type="file" multiple accept="image/*,.zip" className="hidden"
          onChange={e => e.target.files && addFiles(e.target.files)} />
      </div>

      <button type="button" disabled={isDisabled}
        onClick={() => folderInputRef.current?.click()}
        className="text-xs text-muted-foreground hover:text-primary transition-colors disabled:opacity-40 underline-offset-2 hover:underline">
        Or select a folder →
      </button>
      <input ref={folderInputRef} type="file"
        // @ts-expect-error webkitdirectory non-standard
        webkitdirectory="" multiple className="hidden"
        onChange={e => e.target.files && addFiles(e.target.files)} />

      {files.length > 0 && (
        <div className="rounded-lg border border-border/60 bg-background p-3">
          <p className="text-xs text-muted-foreground mb-2 font-medium">
            {files.length} file{files.length !== 1 ? "s" : ""} queued
          </p>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {files.slice(0, 8).map(f => (
              <div key={f.name} className="flex items-center gap-2 text-xs group">
                <FileImage className="h-3 w-3 text-muted-foreground/50 shrink-0" />
                <span className="truncate flex-1 text-muted-foreground">{f.name}</span>
                <button type="button"
                  onClick={e => { e.stopPropagation(); setFiles(p => p.filter(x => x.name !== f.name)); }}
                  className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-all">
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
            {files.length > 8 && <p className="text-xs text-muted-foreground/50">+{files.length - 8} more</p>}
          </div>
        </div>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}

      <button type="submit" disabled={isDisabled || !files.length || !title.trim()}
        className="w-full h-10 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2">
        {submitting
          ? <><Loader2 className="h-4 w-4 animate-spin" />Processing</>
          : <>Ingest Images <ArrowRight className="h-3.5 w-3.5" /></>}
      </button>
    </form>
  );
}
