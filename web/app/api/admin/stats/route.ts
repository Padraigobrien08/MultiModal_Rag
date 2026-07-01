import { fetchBackend } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET() {
  const res = await fetchBackend(`/admin/stats`);
  return Response.json(await res.json(), { status: res.status });
}
