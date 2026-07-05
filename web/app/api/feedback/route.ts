import { proxyJsonBody } from "@/lib/backend";

export async function POST(request: Request) {
  return proxyJsonBody(request, "/feedback");
}
