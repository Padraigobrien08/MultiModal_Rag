import { proxyJson } from "@/lib/backend";

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ watcherId: string }> }
) {
  const { watcherId } = await params;
  return proxyJson(`/watchers/${encodeURIComponent(watcherId)}`, { method: "DELETE" });
}
