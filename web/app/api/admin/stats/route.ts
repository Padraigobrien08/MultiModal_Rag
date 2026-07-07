import { proxyJson, withQuery } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const library_id = searchParams.get("library_id") ?? undefined;
  return proxyJson(withQuery("/admin/stats", { library_id }));
}
