import { fetchBackend } from "@/lib/backend";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const force = searchParams.get("force") === "true";
  const res = await fetchBackend(`/gaps?force=${force}`, { cache: "no-store" });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
