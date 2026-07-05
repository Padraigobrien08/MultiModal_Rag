import { proxyJson, withQuery } from "@/lib/backend";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const force = searchParams.get("force") === "true";
  return proxyJson(withQuery("/gaps", { force }), { cache: "no-store" });
}
