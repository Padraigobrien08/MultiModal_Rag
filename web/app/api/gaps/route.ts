import { proxyJson, withQuery } from "@/lib/backend";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const force = searchParams.get("force") === "true";
  const library_id = searchParams.get("library_id") ?? undefined;
  return proxyJson(withQuery("/gaps", { force, library_id }), { cache: "no-store" });
}
