import { proxyJson, withQuery } from "@/lib/backend";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const status = searchParams.get("status") ?? "pending,running";
  return proxyJson(withQuery("/jobs", { status, limit: 20 }), { cache: "no-store" });
}
