import { proxyJson } from "@/lib/backend";

export async function POST(_req: Request, { params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params;
  return proxyJson(`/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
}
