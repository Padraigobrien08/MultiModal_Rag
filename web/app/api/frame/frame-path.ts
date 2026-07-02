import path from "path";

export const CONTENT_TYPES: Record<string, string> = {
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".webp": "image/webp",
  ".gif": "image/gif",
};

/**
 * Resolve a client-supplied path to an absolute path inside `dataDir`, or return
 * null if it escapes the directory or isn't a supported image type.
 *
 * Containment is checked with path.relative (not startsWith) so sibling-prefix
 * bypasses like `${dataDir}-evil` are rejected. NUL bytes and unsupported
 * extensions are rejected too.
 */
export function resolveFramePath(filePath: string, dataDir: string): string | null {
  if (!filePath || filePath.includes("\0")) return null;

  const resolved = path.isAbsolute(filePath)
    ? path.resolve(filePath)
    : path.resolve(dataDir, filePath);

  const rel = path.relative(dataDir, resolved);
  if (rel === "" || rel === ".." || rel.startsWith(".." + path.sep) || path.isAbsolute(rel)) {
    return null;
  }

  const ext = path.extname(resolved).toLowerCase();
  if (!(ext in CONTENT_TYPES)) return null;

  return resolved;
}

export function contentTypeFor(filePath: string): string {
  return CONTENT_TYPES[path.extname(filePath).toLowerCase()] ?? "application/octet-stream";
}
