import { proxyJson } from "@/lib/backend";

export async function GET(_req: Request, { params }: { params: Promise<{ tutorialId: string }> }) {
  const { tutorialId } = await params;
  return proxyJson(`/tutorials/${encodeURIComponent(tutorialId)}`, { cache: "no-store" });
}

export async function DELETE(_req: Request, { params }: { params: Promise<{ tutorialId: string }> }) {
  const { tutorialId } = await params;
  return proxyJson(`/tutorials/${encodeURIComponent(tutorialId)}`, { method: "DELETE" });
}
