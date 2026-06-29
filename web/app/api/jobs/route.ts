import { fetchBackend } from "@/lib/backend";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const status = searchParams.get("status") ?? "pending,running";
  const res = await fetchBackend(`/jobs?status=${status}&limit=20`, { cache: "no-store" });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
