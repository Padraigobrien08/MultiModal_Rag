import { fetchBackend } from "@/lib/backend";

export async function POST(request: Request) {
  const formData = await request.formData();
  const res = await fetchBackend(`/ingest/images`, {
    method: "POST",
    body: formData,
  });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
