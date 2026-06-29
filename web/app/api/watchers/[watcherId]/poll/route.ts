import { fetchBackend } from "@/lib/backend";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ watcherId: string }> }
) {
  const { watcherId } = await params;
  const res = await fetchBackend(`/watchers/${watcherId}/poll`, { method: "POST" });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
