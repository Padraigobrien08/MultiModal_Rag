// Tests for the shared BFF helpers — the transport/parsing hardening that all
// JSON API routes delegate to. `fetchBackend` calls the global `fetch`, so we
// stub `globalThis.fetch` to drive each branch.
// Run with:  node --test tests/backend.test.ts   (Node 22+, TS type-stripping)
import assert from "node:assert/strict";
import { afterEach, describe, test } from "node:test";

import { proxyJson, proxyJsonBody, withQuery } from "../lib/backend.ts";

const realFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = realFetch;
});

/** Replace global fetch with a stub for the duration of one test. */
function stubFetch(impl: (input: unknown, init?: RequestInit) => Promise<Response>) {
  globalThis.fetch = impl as typeof globalThis.fetch;
}

describe("withQuery", () => {
  test("encodes values and skips undefined/null", () => {
    assert.equal(
      withQuery("/jobs", { status: "pending,running", limit: 20, since: undefined, cursor: null }),
      "/jobs?status=pending%2Crunning&limit=20",
    );
  });

  test("stringifies booleans and numbers", () => {
    assert.equal(withQuery("/gaps", { force: false }), "/gaps?force=false");
  });

  test("returns a bare path when no params survive", () => {
    assert.equal(withQuery("/tutorials", { since: undefined }), "/tutorials");
  });
});

describe("proxyJson", () => {
  test("forwards JSON body and upstream status", async () => {
    stubFetch(async () => Response.json({ ok: true }, { status: 201 }));
    const res = await proxyJson("/thing");
    assert.equal(res.status, 201);
    assert.deepEqual(await res.json(), { ok: true });
  });

  test("preserves a non-2xx status with its JSON error body", async () => {
    stubFetch(async () => Response.json({ detail: "nope" }, { status: 404 }));
    const res = await proxyJson("/thing");
    assert.equal(res.status, 404);
    assert.deepEqual(await res.json(), { detail: "nope" });
  });

  test("maps an unreachable backend to 502", async () => {
    stubFetch(async () => {
      throw new TypeError("fetch failed");
    });
    const res = await proxyJson("/thing");
    assert.equal(res.status, 502);
    assert.deepEqual(await res.json(), { error: "Backend unreachable" });
  });

  test("maps a timeout to 504", async () => {
    stubFetch(async () => {
      throw new DOMException("timed out", "TimeoutError");
    });
    const res = await proxyJson("/thing");
    assert.equal(res.status, 504);
    assert.deepEqual(await res.json(), { error: "Backend request timed out" });
  });

  test("maps a non-JSON body to 502", async () => {
    stubFetch(async () => new Response("<html>gateway error</html>", { status: 502 }));
    const res = await proxyJson("/thing");
    assert.equal(res.status, 502);
    assert.deepEqual(await res.json(), { error: "Backend returned a non-JSON response" });
  });

  test("passes a 204 through with no body", async () => {
    stubFetch(async () => new Response(null, { status: 204 }));
    const res = await proxyJson("/thing", { method: "DELETE" });
    assert.equal(res.status, 204);
    assert.equal(await res.text(), "");
  });

  test("passes an empty body through with its status", async () => {
    stubFetch(async () => new Response("", { status: 200 }));
    const res = await proxyJson("/thing");
    assert.equal(res.status, 200);
    assert.equal(await res.text(), "");
  });
});

describe("proxyJsonBody", () => {
  test("rejects a malformed request body with 400", async () => {
    let called = false;
    stubFetch(async () => {
      called = true;
      return Response.json({});
    });
    const req = new Request("http://web/api/x", { method: "POST", body: "not json{" });
    const res = await proxyJsonBody(req, "/x");
    assert.equal(res.status, 400);
    assert.deepEqual(await res.json(), { error: "Invalid JSON request body" });
    assert.equal(called, false, "backend should not be called for a bad body");
  });

  test("forwards a valid body to the backend", async () => {
    let sentBody: string | undefined;
    stubFetch(async (_input, init) => {
      sentBody = init?.body as string;
      return Response.json({ created: true }, { status: 201 });
    });
    const req = new Request("http://web/api/x", {
      method: "POST",
      body: JSON.stringify({ name: "a" }),
    });
    const res = await proxyJsonBody(req, "/x");
    assert.equal(res.status, 201);
    assert.deepEqual(await res.json(), { created: true });
    assert.deepEqual(JSON.parse(sentBody ?? ""), { name: "a" });
  });
});
