/**
 * No-API-key demo mode.
 *
 * When DEMO_MODE=1, the BFF stops proxying to the FastAPI backend and instead
 * serves canned answers + screenshots from the repo-root `demo/` fixtures. This
 * lets a visitor try Stepwise with `docker compose -f docker-compose.demo.yml up`
 * — no Anthropic key, no model downloads, no video ingestion.
 *
 * Fixtures live at DEMO_DIR (default `../demo`, i.e. repo-root demo/). Screenshots
 * are served by the existing /api/frame route via DATA_DIR pointing at the same dir.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

export const DEMO_MODE = process.env.DEMO_MODE === "1";

const DEMO_DIR = process.env.DEMO_DIR ?? "../demo";

export type DemoStep = {
  step_number: number;
  step_id: string;
  tutorial_id: string;
  tutorial_title: string;
  source_url: string;
  source_type: string;
  video_id: string | null;
  timestamp_start: number | null;
  visual_reference: string | null;
  text: string;
};

export type DemoQuestion = {
  id: string;
  match: string[];
  answer: string;
  steps: DemoStep[];
};

export type DemoResponses = {
  questions: DemoQuestion[];
  fallback: { answer: string; steps: DemoStep[] };
};

export type DemoTutorial = {
  id: string;
  title: string;
  source_url: string;
  source_type: string;
  step_count: number;
  potential_duplicate_of: string | null;
};

let _responses: DemoResponses | null = null;
let _tutorials: DemoTutorial[] | null = null;

function readFixture<T>(file: string): T {
  return JSON.parse(readFileSync(path.join(DEMO_DIR, file), "utf8")) as T;
}

export function loadResponses(): DemoResponses {
  if (!_responses) _responses = readFixture<DemoResponses>("responses.json");
  return _responses;
}

export function loadTutorials(): DemoTutorial[] {
  if (!_tutorials) _tutorials = readFixture<DemoTutorial[]>("tutorials.json");
  return _tutorials;
}

/** Lowercase, strip punctuation, collapse whitespace — for fuzzy matching. */
function normalize(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Pick the canned question whose match phrases best fit the query, or return the
 * fallback. A phrase hits when it is contained in the normalized query (or vice
 * versa) — so both the example buttons and loose free-text land on an answer.
 * Pure (fixtures passed in) so it can be unit-tested without the filesystem.
 */
export function matchQuestion(
  data: DemoResponses,
  query: string,
): { answer: string; steps: DemoStep[] } {
  const q = normalize(query);
  if (q) {
    for (const question of data.questions) {
      for (const phrase of question.match) {
        const p = normalize(phrase);
        if (p && (q.includes(p) || p.includes(q))) {
          return { answer: question.answer, steps: question.steps };
        }
      }
    }
  }
  return data.fallback;
}

const encoder = new TextEncoder();

function sse(obj: unknown): Uint8Array {
  return encoder.encode(`data: ${JSON.stringify(obj)}\n\n`);
}

/**
 * Build the same SSE contract the real /query endpoint streams: a `steps` event,
 * then the answer word-by-word as `token` events (so the typing animation still
 * plays), then `done`.
 */
export function demoQueryResponse(query: string): Response {
  const { answer, steps } = matchQuestion(loadResponses(), query);

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      controller.enqueue(sse({ type: "steps", steps }));

      // Stream the answer in small chunks to preserve the live-typing feel.
      const words = answer.split(" ");
      for (let i = 0; i < words.length; i++) {
        const text = i === 0 ? words[i] : ` ${words[i]}`;
        controller.enqueue(sse({ type: "token", text }));
        await new Promise((r) => setTimeout(r, 18));
      }

      controller.enqueue(sse({ type: "done" }));
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
    },
  });
}
