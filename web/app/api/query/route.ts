import { fetchBackend, jsonError } from "@/lib/backend";
import { DEMO_MODE, demoQueryResponse } from "@/lib/demo";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return jsonError(400, "Invalid JSON request body");
  }

  if (DEMO_MODE) {
    const q = (body as { query?: unknown }).query;
    return demoQueryResponse(typeof q === "string" ? q : "");
  }

  let upstream: Response;
  try {
    upstream = await fetchBackend(`/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      // Streaming SSE response — don't impose a timeout, but cancel upstream
      // if the client disconnects.
      timeoutMs: 0,
      signal: request.signal,
    });
  } catch {
    return jsonError(502, "Backend unreachable");
  }

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
