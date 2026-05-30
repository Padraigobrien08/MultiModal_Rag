const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const status = searchParams.get("status") ?? "pending,running";
  const res = await fetch(`${API_BASE}/jobs?status=${status}&limit=20`, { cache: "no-store" });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
