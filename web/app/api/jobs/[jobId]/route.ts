import { fetchBackend } from "@/lib/backend";

export async function GET(_req: Request, { params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params;
  const res = await fetchBackend(`/jobs/${jobId}`);
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
