import { fetchBackend } from "@/lib/backend";

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ watcherId: string }> }
) {
  const { watcherId } = await params;
  const res = await fetchBackend(`/watchers/${watcherId}`, { method: "DELETE" });
  if (res.status === 204) return new Response(null, { status: 204 });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
