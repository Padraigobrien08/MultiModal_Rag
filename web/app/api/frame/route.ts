import { readFile } from "fs/promises";
import path from "path";

const DATA_DIR = path.resolve(/*turbopackIgnore: true*/ process.env.DATA_DIR ?? "../data");

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const filePath = searchParams.get("path");

  if (!filePath) {
    return new Response("Missing path", { status: 400 });
  }

  // Resolve relative to DATA_DIR so both local and Docker paths work
  const resolved = path.isAbsolute(filePath)
    ? path.resolve(filePath)
    : path.resolve(DATA_DIR, filePath);

  // Prevent directory traversal — must stay within DATA_DIR
  if (!resolved.startsWith(DATA_DIR)) {
    return new Response("Forbidden", { status: 403 });
  }

  try {
    const buffer = await readFile(resolved);
    return new Response(buffer, {
      headers: { "Content-Type": "image/jpeg", "Cache-Control": "public, max-age=31536000" },
    });
  } catch {
    return new Response("Not found", { status: 404 });
  }
}
