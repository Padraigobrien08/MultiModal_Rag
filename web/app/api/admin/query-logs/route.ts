import { proxyJson, withQuery } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const since = searchParams.get("since");
  return proxyJson(withQuery("/admin/query-logs", { limit: 500, since }));
}
