const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = await request.json();
  const upstream = await fetch(`${API_BASE}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  // Pass the SSE stream straight through — don't buffer
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
    },
  });
}
