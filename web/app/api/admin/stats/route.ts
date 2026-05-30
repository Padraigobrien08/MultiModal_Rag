const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function GET() {
  const res = await fetch(`${API_BASE}/admin/stats`);
  return Response.json(await res.json(), { status: res.status });
}
