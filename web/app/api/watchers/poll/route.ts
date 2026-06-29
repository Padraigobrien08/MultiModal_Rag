import { fetchBackend } from "@/lib/backend";

export async function POST() {
  const res = await fetchBackend(`/watchers/poll`, { method: "POST" });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
