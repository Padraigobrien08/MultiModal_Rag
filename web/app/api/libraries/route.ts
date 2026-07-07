import { proxyJson, proxyJsonBody } from "@/lib/backend";

export async function GET() {
  return proxyJson("/libraries", { cache: "no-store" });
}

export async function POST(request: Request) {
  return proxyJsonBody(request, "/libraries");
}
