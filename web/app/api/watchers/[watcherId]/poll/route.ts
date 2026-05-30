const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ watcherId: string }> }
) {
  const { watcherId } = await params;
  const res = await fetch(`${API_BASE}/watchers/${watcherId}/poll`, { method: "POST" });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
