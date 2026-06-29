import { fetchBackend } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const since = searchParams.get("since");
  const params = new URLSearchParams({ limit: "500" });
  if (since) params.set("since", since);
  const res = await fetchBackend(`/admin/query-logs?${params.toString()}`);
  return Response.json(await res.json(), { status: res.status });
}
