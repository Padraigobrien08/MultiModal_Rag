import { proxyJson } from "@/lib/backend";
import { DEMO_MODE, loadTutorials } from "@/lib/demo";

export async function GET() {
  if (DEMO_MODE) return Response.json(loadTutorials());
  return proxyJson("/tutorials", { cache: "no-store" });
}
