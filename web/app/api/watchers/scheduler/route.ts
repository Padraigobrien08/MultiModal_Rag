const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export async function GET() {
  const res = await fetch(`${API_BASE}/watchers/scheduler`, { cache: "no-store" });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
