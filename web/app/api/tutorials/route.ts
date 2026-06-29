import { fetchBackend } from "@/lib/backend";

export async function GET() {
  const res = await fetchBackend(`/tutorials`, { cache: "no-store" });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
