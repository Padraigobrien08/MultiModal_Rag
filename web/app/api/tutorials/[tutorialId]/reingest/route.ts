const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export async function POST(_req: Request, { params }: { params: Promise<{ tutorialId: string }> }) {
  const { tutorialId } = await params;
  const res = await fetch(`${API_BASE}/tutorials/${tutorialId}/reingest`, { method: "POST" });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
