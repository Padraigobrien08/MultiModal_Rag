import { proxyJson, withQuery } from "@/lib/backend";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const status = searchParams.get("status") ?? "pending,running";
  const library_id = searchParams.get("library_id") ?? undefined;
  return proxyJson(withQuery("/jobs", { status, limit: 20, library_id }), { cache: "no-store" });
}
