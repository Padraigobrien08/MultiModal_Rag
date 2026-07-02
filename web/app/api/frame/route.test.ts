// Real tests for the frame route's path-containment and content-type logic —
// the security-critical code the GET handler delegates to.
// Run with:  node --test app/api/frame/route.test.ts   (Node 22+, TS type-stripping)
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, test } from "node:test";

import { contentTypeFor, resolveFramePath } from "./frame-path.ts";

const DATA_DIR = mkdtempSync(path.join(tmpdir(), "frame-test-"));

describe("resolveFramePath — containment", () => {
  test("accepts a valid image inside the data dir", () => {
    assert.equal(
      resolveFramePath("tut/frame_0001.png", DATA_DIR),
      path.join(DATA_DIR, "tut/frame_0001.png"),
    );
  });

  test("rejects parent-directory traversal", () => {
    assert.equal(resolveFramePath("../secret.png", DATA_DIR), null);
    assert.equal(resolveFramePath("../../etc/passwd", DATA_DIR), null);
    assert.equal(resolveFramePath("tut/../../escape.png", DATA_DIR), null);
  });

  test("rejects absolute paths outside the data dir", () => {
    assert.equal(resolveFramePath("/etc/passwd", DATA_DIR), null);
  });

  test("accepts an absolute path that stays inside the data dir", () => {
    const inside = path.join(DATA_DIR, "tut", "frame.png");
    assert.equal(resolveFramePath(inside, DATA_DIR), inside);
  });

  test("rejects sibling-prefix bypass (dataDir + '-evil')", () => {
    // A naive startsWith(dataDir) check would wrongly allow this.
    assert.equal(resolveFramePath(DATA_DIR + "-evil/frame.png", DATA_DIR), null);
  });

  test("rejects the data dir itself and empty input", () => {
    assert.equal(resolveFramePath(".", DATA_DIR), null);
    assert.equal(resolveFramePath("", DATA_DIR), null);
  });

  test("rejects NUL-byte injection", () => {
    assert.equal(resolveFramePath("frame.png\0.txt", DATA_DIR), null);
  });
});

describe("resolveFramePath — extension allow-list", () => {
  test("rejects unsupported or missing extensions", () => {
    assert.equal(resolveFramePath("notes.txt", DATA_DIR), null);
    assert.equal(resolveFramePath("archive.zip", DATA_DIR), null);
    assert.equal(resolveFramePath("frame", DATA_DIR), null);
  });

  test("accepts each supported image extension (case-insensitive)", () => {
    for (const ext of [".jpg", ".jpeg", ".png", ".webp", ".gif", ".PNG"]) {
      assert.notEqual(resolveFramePath("f" + ext, DATA_DIR), null, ext);
    }
  });
});

describe("contentTypeFor", () => {
  test("maps each extension to the correct MIME type", () => {
    assert.equal(contentTypeFor("a.jpg"), "image/jpeg");
    assert.equal(contentTypeFor("a.jpeg"), "image/jpeg");
    assert.equal(contentTypeFor("a.png"), "image/png");
    assert.equal(contentTypeFor("a.webp"), "image/webp");
    assert.equal(contentTypeFor("a.gif"), "image/gif");
  });

  test("falls back to octet-stream for unknown extensions", () => {
    assert.equal(contentTypeFor("a.txt"), "application/octet-stream");
  });
});
