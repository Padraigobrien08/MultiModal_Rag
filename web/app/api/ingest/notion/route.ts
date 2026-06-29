import { fetchBackend } from "@/lib/backend";

export async function POST(request: Request) {
  const body = await request.json();
  const res = await fetchBackend(`/ingest/notion`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
