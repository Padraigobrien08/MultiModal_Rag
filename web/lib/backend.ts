/** Server-side helpers for calling the Stepwise FastAPI backend from Next.js BFF routes. */

export const API_BASE = process.env.API_BASE ?? "http://localhost:8000";

const API_KEY = process.env.API_KEY;

/** Headers for backend fetch — forwards API_KEY when configured on the web service. */
export function backendHeaders(init?: HeadersInit): Headers {
  const headers = new Headers(init);
  if (API_KEY && !headers.has("X-API-Key")) {
    headers.set("X-API-Key", API_KEY);
  }
  return headers;
}

export function fetchBackend(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  return fetch(url, {
    ...init,
    headers: backendHeaders(init?.headers),
  });
}
