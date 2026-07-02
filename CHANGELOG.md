# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Open-source repository hygiene: `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`,
  `CODE_OF_CONDUCT.md`, `SUPPORT.md`, `CHANGELOG.md`, GitHub issue/PR templates,
  and Dependabot configuration.
- Stepwise-specific frontend README under `web/`.

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
  (`web/app/api/frame/route.test.ts`, run from `pytest`).

### Changed

- Hardened the backend `Dockerfile`: copy source before installing so the build
  is reproducible, install runtime dependencies only (no dev extras), and run as
  a non-root user. The frontend production image now also runs as non-root.
- Expanded `.dockerignore` and `web/.dockerignore` to shrink the build context
  and keep secrets out of images.

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
