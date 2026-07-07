import { proxyJson, proxyJsonBody, withQuery } from "@/lib/backend";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const library_id = searchParams.get("library_id") ?? undefined;
  return proxyJson(withQuery("/watchers", { library_id }), { cache: "no-store" });
}

export async function POST(request: Request) {
  return proxyJsonBody(request, "/watchers");
}
