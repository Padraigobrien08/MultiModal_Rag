import { proxyJson } from "@/lib/backend";

export async function GET() {
  return proxyJson("/watchers/scheduler", { cache: "no-store" });
}
