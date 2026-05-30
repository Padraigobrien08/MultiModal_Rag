"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MoreHorizontal, RefreshCw, Trash2 } from "lucide-react";

export function TutorialActionsMenu({ tutorialId }: { tutorialId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function handleDelete() {
    if (!confirm("Delete this tutorial and all its steps? This cannot be undone.")) return;
    setBusy(true);
    await fetch(`/api/tutorials/${tutorialId}`, { method: "DELETE" });
    router.refresh();
    setBusy(false);
  }

  async function handleReingest() {
    if (!confirm("Re-ingest this tutorial? The existing steps will be deleted and re-extracted.")) return;
    setBusy(true);
    const res = await fetch(`/api/tutorials/${tutorialId}/reingest`, { method: "POST" });
    const { job_id } = await res.json();
    // Send user to ingest page — localStorage will pick up the job
    localStorage.setItem("stepwise_active_job", JSON.stringify({
      job_id,
      status: "pending",
      created_at: new Date().toISOString(),
    }));
    router.push("/");
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        disabled={busy}
        className="inline-flex items-center justify-center h-7 w-7 rounded-lg hover:bg-muted transition-colors disabled:opacity-50"
      >
        <MoreHorizontal className="h-4 w-4" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={handleReingest} className="gap-2 cursor-pointer">
          <RefreshCw className="h-3.5 w-3.5" />
          Re-ingest
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={handleDelete}
          className="gap-2 cursor-pointer text-destructive focus:text-destructive"
        >
          <Trash2 className="h-3.5 w-3.5" />
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
