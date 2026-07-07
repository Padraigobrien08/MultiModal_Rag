import { proxyJson, withQuery } from "@/lib/backend";
import { DEMO_MODE, loadTutorials } from "@/lib/demo";

export async function GET(request: Request) {
  if (DEMO_MODE) return Response.json(loadTutorials());
  const { searchParams } = new URL(request.url);
  const library_id = searchParams.get("library_id") ?? undefined;
  return proxyJson(withQuery("/tutorials", { library_id }), { cache: "no-store" });
}
