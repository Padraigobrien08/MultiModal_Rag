# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Production operations polish: a `/ready` readiness probe that checks DB
  writability and Chroma reachability without loading ML models (`/health`
  stays a bare liveness check); `updated_at`/`completed_at` timestamps on
  ingestion jobs, surfaced via `/jobs` and `/jobs/{id}`; request IDs in API
  request logs and background job-failure logs; and a production checklist in
  the README (`API_KEY`, explicit `CORS_ORIGINS`, data-volume backups, model
  download/cache expectations).
- Open-source repository hygiene: `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`,
  `CODE_OF_CONDUCT.md`, `SUPPORT.md`, `CHANGELOG.md`, GitHub issue/PR templates,
  and Dependabot configuration.
- Stepwise-specific frontend README under `web/`.
- Complete packaging metadata in `pyproject.toml` (description, readme, license,
  authors, keywords, classifiers, and project URLs) and a "Releasing" checklist
  in `CONTRIBUTING.md` documenting the git-tag/GitHub-release flow. The project
  is intentionally not published to PyPI, enforced via the
  `Private :: Do Not Upload` classifier.
- Generated `constraints.txt` pinning the full runtime dependency tree for
  reproducible production Docker builds. The `Dockerfile` installs with
  `pip install -c constraints.txt .`; regenerate with `make lock` (resolves
  inside `python:3.11-slim`). `pyproject.toml` stays range-based for local dev
  and Dependabot. See "Dependency pinning" in `CONTRIBUTING.md`.

### Security

- Hardened public API input validation: bounds on query length, `top_k`,
  history size, list `limit`s, IDs, and uploads; watcher source types validated
  via an enum; watcher poll interval bounded.
- Mutable Pydantic/SQLAlchemy defaults replaced with `default_factory`/callables.
- Constant-time API key comparison (`hmac.compare_digest`); production CORS
  guidance plus a startup warning for wildcard-with-API-key.
- Image ingestion now rejects oversized files, verifies image content before
  writing, and guards against ZIP bombs (entry count, uncompressed size,
  compression ratio).
- Hardened the frame-serving route (`web/app/api/frame`) with `path.relative`
  containment (blocking sibling-prefix bypasses), NUL-byte rejection, an
  extension allow-list, and correct per-type content types — with real tests
  (`web/app/api/frame/route.test.ts`, run with `npm run test`).

### Changed

- Hardened the backend `Dockerfile`: copy source before installing so the build
  is reproducible, install runtime dependencies only (no dev extras), and run as
  a non-root user. The frontend production image now also runs as non-root.
- Expanded `.dockerignore` and `web/.dockerignore` to shrink the build context
  and keep secrets out of images.
- Centralized all Claude model IDs in `stepwise.config.Settings` with a
  per-stage setting each (`STRUCTURING_MODEL`, `HYDE_MODEL`, `SYNTHESIS_MODEL`,
  `CONSOLIDATION_MODEL`); removed the hard-coded `FAST_MODEL` from the retriever
  and renamed `CLAUDE_MODEL` → `CONSOLIDATION_MODEL`. Defaults are unchanged
  (behavior-equivalent). Documented how to choose/update models against
  Anthropic's model docs. **Migration:** if you set `CLAUDE_MODEL`, rename it to
  `CONSOLIDATION_MODEL`.

### Fixed

- Cleaned the lint/build verification baseline (ruff, ESLint, Next build) with
  no changes to application behavior.

## [0.1.0]

### Added

- Multimodal ingestion of YouTube videos, Google Drive recordings, Notion
  pages/databases, and screenshots.
- Claude-based step structuring (Haiku extraction, Sonnet consolidation) with
  trivial-step filtering and deduplication.
- Fused text + CLIP image embeddings indexed in ChromaDB, with SQLite/SQLAlchemy
  for relational data.
- HyDE retrieval with a cross-encoder re-ranking stage and streamed answer
  synthesis over SSE.
- Auto-ingestion watchers for YouTube channels, Drive folders, and Notion
  databases, plus a pollable endpoint.
- Query-log gap detection that clusters unanswered questions and suggests
  tutorials to record.
- FastAPI backend, Next.js dashboard, and a Zendesk sidebar integration.
- Retrieval evaluation harness (`scripts/run_eval.py`).

[Unreleased]: https://github.com/Padraigobrien08/MultiModal_Rag/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Padraigobrien08/MultiModal_Rag/releases/tag/v0.1.0
