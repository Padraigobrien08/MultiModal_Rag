/** Server-side helpers for calling the Stepwise FastAPI backend from Next.js BFF routes. */

export const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

const API_KEY = process.env.API_KEY;

/** Abort a backend request after this many ms unless the caller overrides it. */
const DEFAULT_TIMEOUT_MS = 30_000;

/** Headers for backend fetch — forwards API_KEY when configured on the web service. */
export function backendHeaders(init?: HeadersInit): Headers {
  const headers = new Headers(init);
  if (API_KEY && !headers.has("X-API-Key")) {
    headers.set("X-API-Key", API_KEY);
  }
  return headers;
}

export interface BackendFetchOptions extends RequestInit {
  /** Abort the request after this many ms. Pass 0 to disable (e.g. for streaming). */
  timeoutMs?: number;
}

export function fetchBackend(path: string, init?: BackendFetchOptions): Promise<Response> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal, ...rest } = init ?? {};
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;

  let finalSignal = signal ?? undefined;
  if (timeoutMs > 0) {
    const timeoutSignal = AbortSignal.timeout(timeoutMs);
    finalSignal = finalSignal ? AbortSignal.any([finalSignal, timeoutSignal]) : timeoutSignal;
  }

  return fetch(url, {
    ...rest,
    headers: backendHeaders(rest.headers),
    signal: finalSignal,
  });
}

/** Consistent JSON error body returned to the browser. */
export function jsonError(status: number, error: string): Response {
  return Response.json({ error }, { status });
}

type QueryValue = string | number | boolean | undefined | null;

/**
 * Append encoded query parameters to a path. `undefined`/`null` values are
 * skipped; everything else is passed through URLSearchParams, which handles
 * encoding.
 */
export function withQuery(path: string, params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `${path}?${qs}` : path;
}

/**
 * Proxy a backend endpoint that returns JSON, translating transport and
 * parsing failures into a consistent JSON error shape:
 *   - backend unreachable        -> 502 { error }
 *   - timeout / abort            -> 504 { error }
 *   - 204 / empty body           -> passed through with no body
 *   - non-JSON body              -> 502 { error }
 *   - otherwise                  -> upstream JSON + upstream status
 */
export async function proxyJson(path: string, init?: BackendFetchOptions): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await fetchBackend(path, init);
  } catch (err) {
    const name = (err as { name?: string } | null)?.name;
    if (name === "TimeoutError") return jsonError(504, "Backend request timed out");
    if (name === "AbortError") return jsonError(504, "Backend request cancelled");
    return jsonError(502, "Backend unreachable");
  }

  // 204 No Content — nothing to parse or forward.
  if (upstream.status === 204) {
    return new Response(null, { status: 204 });
  }

  const text = await upstream.text();
  if (text === "") {
    return new Response(null, { status: upstream.status });
  }

  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return jsonError(502, "Backend returned a non-JSON response");
  }

  return Response.json(data, { status: upstream.status });
}

/**
 * Read a JSON body from the incoming request and proxy it to a backend path as
 * a JSON POST, reusing {@link proxyJson} for the response. A malformed request
 * body yields a 400 rather than an unhandled error.
 */
export async function proxyJsonBody(request: Request, path: string): Promise<Response> {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return jsonError(400, "Invalid JSON request body");
  }
  return proxyJson(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
