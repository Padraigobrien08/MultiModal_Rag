// Tests for the demo-mode question matcher — the logic that maps a visitor's
// question to one of the canned answers (or the fallback). Runs against the real
// demo/responses.json fixture so drift between code and fixtures is caught.
// Run with:  node --test tests/demo.test.ts   (Node 22+, TS type-stripping)
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, test } from "node:test";

import { matchQuestion, type DemoResponses } from "../lib/demo.ts";

const data = JSON.parse(
  readFileSync(path.join(import.meta.dirname, "../../demo/responses.json"), "utf8"),
) as DemoResponses;

describe("matchQuestion — the three sample questions", () => {
  test("each example button resolves to its own answer with steps", () => {
    const cases: [string, string][] = [
      ["How do I configure an API key?", "api-key"],
      ["How do I invite a team member?", "invite-member"],
      ["How do I issue a refund?", "refund"],
    ];
    for (const [query, id] of cases) {
      const expected = data.questions.find((q) => q.id === id)!;
      const got = matchQuestion(data, query);
      assert.equal(got.answer, expected.answer, id);
      assert.ok(got.steps.length > 0, `${id} should have steps`);
      assert.equal(got.steps[0].step_id, expected.steps[0].step_id, id);
    }
  });
});

describe("matchQuestion — fuzziness", () => {
  test("ignores case and punctuation", () => {
    const got = matchQuestion(data, "  How do I ISSUE a Refund?!  ");
    assert.equal(got.answer, data.questions.find((q) => q.id === "refund")!.answer);
  });

  test("loose free-text still lands on a canned answer", () => {
    assert.equal(matchQuestion(data, "refund a charge").steps[0].step_id, "demo-refund-1");
    assert.equal(matchQuestion(data, "I want to add a user").steps[0].step_id, "demo-invite-1");
  });
});

describe("matchQuestion — fallback", () => {
  test("unrelated questions return the fallback with no steps", () => {
    const got = matchQuestion(data, "what is the weather today");
    assert.equal(got.answer, data.fallback.answer);
    assert.deepEqual(got.steps, []);
  });

  test("empty input returns the fallback", () => {
    assert.equal(matchQuestion(data, "").answer, data.fallback.answer);
    assert.equal(matchQuestion(data, "   ").answer, data.fallback.answer);
  });
});
