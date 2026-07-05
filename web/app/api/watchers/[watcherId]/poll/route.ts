import { proxyJson } from "@/lib/backend";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ watcherId: string }> }
) {
  const { watcherId } = await params;
  return proxyJson(`/watchers/${encodeURIComponent(watcherId)}/poll`, { method: "POST" });
}
