import { fetchBackend } from "@/lib/backend";

export async function GET(_req: Request, { params }: { params: Promise<{ tutorialId: string }> }) {
  const { tutorialId } = await params;
  const res = await fetchBackend(`/tutorials/${tutorialId}`, { cache: "no-store" });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}

export async function DELETE(_req: Request, { params }: { params: Promise<{ tutorialId: string }> }) {
  const { tutorialId } = await params;
  const res = await fetchBackend(`/tutorials/${tutorialId}`, { method: "DELETE" });
  if (res.status === 204) return new Response(null, { status: 204 });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
