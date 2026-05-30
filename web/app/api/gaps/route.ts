const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const force = searchParams.get("force") === "true";
  const res = await fetch(`${API_BASE}/gaps?force=${force}`, { cache: "no-store" });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
