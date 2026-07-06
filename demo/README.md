# Stepwise demo fixtures

Everything here powers the **zero-API-key demo** (`docker-compose.demo.yml`). It
is entirely fake, hand-authored data — no real customer videos, no model output.

```
docker compose -f docker-compose.demo.yml up --build
# → http://localhost:3000
```

In demo mode the Next.js BFF (`web/lib/demo.ts`) answers from these files instead
of proxying to the FastAPI backend, so nothing here touches Anthropic, Whisper,
YouTube, or the embedding/CLIP models.

## Files

| File | Purpose |
|---|---|
| `responses.json` | The three canned questions → `{ answer, steps }`, plus a `fallback` for anything else. Step objects match the frontend `StepResult` shape. |
| `tutorials.json`  | The fake library shown in the right-hand sidebar. |
| `frames/*.png`    | Mock "Acme" product screenshots referenced by each step's `visual_reference` (served by `/api/frame`). |
| `generate_frames.py` | Regenerates `frames/` with Pillow. Only needed if you change what the screenshots show. |

## The three canned questions

- *How do I configure an API key?*
- *How do I invite a team member?*
- *How do I issue a refund?*

Free-text that loosely matches one of these (e.g. "refund a charge") resolves to
the same answer; anything else returns the `fallback` message.

## Editing

- **Change wording / steps:** edit `responses.json`. `match` is a list of phrases
  compared (normalized, substring either direction) against the user's question.
- **Change screenshots:** edit `FRAMES` in `generate_frames.py`, then
  `python demo/generate_frames.py`, and commit the new PNGs.
- `visual_reference` paths are resolved relative to `DATA_DIR` (the demo compose
  sets `DATA_DIR=/app/demo`), so keep them as `frames/<name>.png`.
