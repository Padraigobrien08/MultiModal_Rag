import { fetchBackend } from "@/lib/backend";

export async function POST(request: Request) {
  const body = await request.json();
  const res = await fetchBackend(`/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return Response.json(await res.json(), { status: res.status });
}
