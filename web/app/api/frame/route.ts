import { readFile } from "fs/promises";

import { contentTypeFor, resolveFramePath } from "./frame-path";

import path from "path";

const DATA_DIR = path.resolve(/*turbopackIgnore: true*/ process.env.DATA_DIR ?? "../data");

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const filePath = searchParams.get("path");

  if (!filePath) {
    return new Response("Missing path", { status: 400 });
  }

  const resolved = resolveFramePath(filePath, DATA_DIR);
  if (!resolved) {
    return new Response("Forbidden", { status: 403 });
  }

  try {
    const buffer = await readFile(resolved);
    return new Response(new Uint8Array(buffer), {
      headers: {
        "Content-Type": contentTypeFor(resolved),
        "Cache-Control": "public, max-age=31536000",
      },
    });
  } catch {
    return new Response("Not found", { status: 404 });
  }
}
