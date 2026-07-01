# Contributing to Stepwise

Thanks for your interest in contributing! This guide covers local setup, the
checks your change must pass, and what we expect in a pull request.

By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Project layout

Stepwise is a Python backend (`stepwise/`) plus a Next.js frontend (`web/`).
See the [README](README.md#repository-layout) for the full module map.

## Local setup

### Prerequisites

- Python **3.11+**
- Node.js **20+** (for the `web/` frontend)
- `ffmpeg` and `yt-dlp` on your `PATH` (required for video ingestion)
- An `ANTHROPIC_API_KEY`

### Backend

```bash
python -m venv venv && source venv/bin/activate
pip install -e .
cp .env.example .env          # then add your ANTHROPIC_API_KEY
uvicorn stepwise.api.app:app --reload
```

The API serves interactive OpenAPI docs at http://localhost:8000/docs.

### Frontend

```bash
cd web
npm install
npm run dev                   # http://localhost:3000
```

### Docker (full stack)

```bash
cp .env.example .env          # add your ANTHROPIC_API_KEY
docker compose up --build
```

- API → http://localhost:8000
- Web → http://localhost:3000

## Checks before opening a PR

Your change must pass the same checks CI runs. Dev tooling (`ruff`, `pytest`)
is not bundled with the runtime dependencies — install it into your virtualenv:

```bash
pip install ruff pytest
```

### Lint & test the backend

```bash
python -m ruff check stepwise tests scripts
python -m pytest tests/ -q
```

### Lint & build the frontend

```bash
cd web
npm run lint
npm run build
```

Run all of these locally before pushing. Keep the tree lint-clean — do not
disable rules to make a check pass unless you can justify it in the PR.

## Pull request expectations

- **Branch** from `main` and open your PR against `main`.
- **Keep changes scoped.** One logical change per PR. Don't mix refactors,
  formatting sweeps, and features together.
- **Match the surrounding style.** Don't reformat code you aren't otherwise
  touching.
- **Describe the change** using the PR template: what changed, why, and how you
  verified it. Paste the relevant command output.
- **Update docs** (README, CHANGELOG, etc.) when behavior or setup changes.
- **Add a CHANGELOG entry** under the `[Unreleased]` section following the
  [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.
- **Don't commit secrets.** Never commit `.env` or API keys. See
  [SECURITY.md](SECURITY.md#handling-secrets).

## Reporting bugs & requesting features

Use the [issue templates](https://github.com/Padraigobrien08/MultiModal_Rag/issues/new/choose).
For anything security-related, follow [SECURITY.md](SECURITY.md) instead of
opening a public issue.
