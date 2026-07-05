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
- Node.js **24** (matches CI). `npm run test` runs the TypeScript tests through
  Node's native type-stripping, which requires Node **≥ 22.18** (or 23.6+) — Node
  20 cannot run them.
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

### Dependency pinning

Runtime dependencies are declared as **version ranges** in `pyproject.toml` —
that keeps local dev (`pip install -e .`) and Dependabot simple. For the
**production Docker image** we also keep `constraints.txt`, a fully-pinned
snapshot of the resolved transitive tree, so image builds are reproducible
instead of picking up whatever satisfies the ranges on build day. The
`Dockerfile` installs with `pip install -c constraints.txt .`.

`constraints.txt` is generated (do not hand-edit). Regenerate it after changing
runtime dependencies in `pyproject.toml`, or to pull in transitive security
fixes:

```bash
make lock          # requires Docker; resolves inside python:3.11-slim
```

Commit the regenerated `constraints.txt` alongside the `pyproject.toml` change.
Dependabot still bumps the ranges in `pyproject.toml`; run `make lock` when you
want those bumps reflected in the pinned image build.

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

## Releasing

Stepwise is a **deployed application, not a published package.** It is *not*
uploaded to PyPI — `pyproject.toml` exists so the backend installs cleanly
(`pip install -e .`) and exposes the `stepwise` CLI, nothing more. The
`Private :: Do Not Upload` classifier makes any accidental `twine upload` fail,
so there is no publish step to run.

Because there is no package registry, a "release" is just a **git tag plus a
GitHub release** that pins a known-good commit. The `CHANGELOG.md` compare/
release links resolve once the matching tag exists.

### Cutting a release

1. **Land all changes** for the release on `main` and make sure CI is green.
2. **Move the `[Unreleased]` entries** in `CHANGELOG.md` under a new
   `## [X.Y.Z]` heading dated today, and add a fresh empty `[Unreleased]`
   section above it.
3. **Bump `version`** in `pyproject.toml` to `X.Y.Z` (skip for the first
   `0.1.0`, which is already set).
4. **Update the link references** at the bottom of `CHANGELOG.md` so
   `[Unreleased]` compares `vX.Y.Z...HEAD` and `[X.Y.Z]` points at the new tag.
5. **Verify metadata still builds:** `python -m build` (produces
   `dist/stepwise-X.Y.Z*`; the `Private :: Do Not Upload` classifier is
   expected — do not upload).
6. **Commit, tag, and push:**

   ```bash
   git commit -am "Release vX.Y.Z"
   git tag -a vX.Y.Z -m "Stepwise vX.Y.Z"
   git push origin main --follow-tags
   ```

7. **Create the GitHub release** from the tag (`gh release create vX.Y.Z
   --notes-from-tag` or the web UI) and paste the `CHANGELOG.md` section as the
   notes.

> **First release (`v0.1.0`):** the `0.1.0` section already exists in
> `CHANGELOG.md`, so the initial release is just steps 6–7 with `vX.Y.Z =
> v0.1.0`. Until that tag is pushed, the `v0.1.0` links in `CHANGELOG.md` will
> 404 — creating the tag is what makes them resolve.

### Citation metadata

We deliberately **do not ship a `CITATION.cff`.** Stepwise is a product/
application rather than a research artifact or library meant to be cited in
academic work, so a citation file would add maintenance overhead without a real
audience. If that changes (e.g. the project is referenced in a paper), add a
`CITATION.cff` at the repo root and GitHub will surface a "Cite this
repository" button automatically.

## Reporting bugs & requesting features

Use the [issue templates](https://github.com/Padraigobrien08/MultiModal_Rag/issues/new/choose).
For anything security-related, follow [SECURITY.md](SECURITY.md) instead of
opening a public issue.
