const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export async function POST(request: Request) {
  const body = await request.json();
  const res = await fetch(`${API_BASE}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return Response.json(await res.json(), { status: res.status });
}
