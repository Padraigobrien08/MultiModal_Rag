import { proxyJson } from "@/lib/backend";

export async function GET(_req: Request, { params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params;
  return proxyJson(`/jobs/${encodeURIComponent(jobId)}`);
}
