import { jsonError, proxyJson } from "@/lib/backend";

export async function POST(request: Request) {
  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return jsonError(400, "Invalid multipart form data");
  }
  return proxyJson("/ingest/images", { method: "POST", body: formData });
}
