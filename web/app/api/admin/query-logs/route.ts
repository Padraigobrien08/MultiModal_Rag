const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const since = searchParams.get("since");
  const upstream = new URL(`${API_BASE}/admin/query-logs`);
  upstream.searchParams.set("limit", "500");
  if (since) upstream.searchParams.set("since", since);
  const res = await fetch(upstream.toString());
  return Response.json(await res.json(), { status: res.status });
}
