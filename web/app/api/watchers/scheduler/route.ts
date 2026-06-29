import { fetchBackend } from "@/lib/backend";

export async function GET() {
  const res = await fetchBackend(`/watchers/scheduler`, { cache: "no-store" });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
