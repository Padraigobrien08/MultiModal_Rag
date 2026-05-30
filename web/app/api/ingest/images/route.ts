const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export async function POST(request: Request) {
  const formData = await request.formData();
  const res = await fetch(`${API_BASE}/ingest/images`, {
    method: "POST",
    body: formData,
  });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
