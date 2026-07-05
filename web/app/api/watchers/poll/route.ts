import { proxyJson } from "@/lib/backend";

export async function POST() {
  return proxyJson("/watchers/poll", { method: "POST" });
}
