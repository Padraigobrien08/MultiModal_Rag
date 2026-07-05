import { proxyJson } from "@/lib/backend";

export async function POST(_req: Request, { params }: { params: Promise<{ tutorialId: string }> }) {
  const { tutorialId } = await params;
  return proxyJson(`/tutorials/${encodeURIComponent(tutorialId)}/reingest`, { method: "POST" });
}
