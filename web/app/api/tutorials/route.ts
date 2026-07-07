import { proxyJson, withQuery } from "@/lib/backend";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const library_id = searchParams.get("library_id") ?? undefined;
  return proxyJson(withQuery("/tutorials", { library_id }), { cache: "no-store" });
}
