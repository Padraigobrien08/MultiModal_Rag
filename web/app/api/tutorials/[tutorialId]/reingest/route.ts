import { fetchBackend } from "@/lib/backend";

export async function POST(_req: Request, { params }: { params: Promise<{ tutorialId: string }> }) {
  const { tutorialId } = await params;
  const res = await fetchBackend(`/tutorials/${tutorialId}/reingest`, { method: "POST" });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
