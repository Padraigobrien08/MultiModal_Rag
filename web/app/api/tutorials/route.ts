import { proxyJson } from "@/lib/backend";

export async function GET() {
  return proxyJson("/tutorials", { cache: "no-store" });
}
