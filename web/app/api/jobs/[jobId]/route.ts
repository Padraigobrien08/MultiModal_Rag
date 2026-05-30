const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export async function GET(_req: Request, { params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params;
  const res = await fetch(`${API_BASE}/jobs/${jobId}`);
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
