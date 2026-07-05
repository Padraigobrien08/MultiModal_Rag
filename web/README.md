# Stepwise — Web Dashboard

The frontend for [Stepwise](../README.md): a Next.js dashboard for ingesting
sources, chatting with the library, managing auto-ingestion watchers, and
reviewing retrieval telemetry.

It is a thin client over the Stepwise FastAPI backend. The routes under
`app/api/` act as a backend-for-frontend (BFF) proxy — the browser talks only to
this Next.js server, which forwards to the API.

## Stack

- **Next.js 16** (App Router, Turbopack) · **React 19**
- **Tailwind CSS v4** · **shadcn** components · **lucide-react** icons
- React Compiler enabled (`reactCompiler: true` in `next.config.ts`)
- Standalone output for containerized deploys (`output: "standalone"`)

## Pages

| Route                       | Purpose                                                                       |
| --------------------------- | ----------------------------------------------------------------------------- |
| `/`                         | Main app — chat (cited, timestamped step answers), plus ingest (modal) and the library sidebar |
| `/tutorials`, `/tutorials/[id]` | Library — browse ingested tutorials and their steps                       |
| `/watchers`                 | Manage auto-ingestion sources (YouTube / Drive / Notion)                      |
| `/gaps`                     | Coverage gaps detected from query logs                                        |
| `/admin`                    | Retrieval telemetry — query logs and stats                                    |
| `/query`                    | Redirects to `/` (the `Query` nav link and old bookmarks land here)           |

## Running

The easiest path is the full stack from the repo root:

```bash
docker compose up --build     # API on :8000, web on :3000
```

To run the frontend on its own (expects the API reachable at `API_BASE`):

```bash
npm install
npm run dev                   # http://localhost:3000
```

### Scripts

| Command         | Description                          |
| --------------- | ------------------------------------ |
| `npm run dev`   | Start the dev server (Turbopack HMR) |
| `npm run build` | Production build                     |
| `npm run start` | Serve the production build           |
| `npm run lint`  | Run ESLint                           |
| `npm run test`  | Run unit tests (Node's built-in test runner) |

## Configuration

The frontend reads two environment variables:

| Variable   | Default                 | Description                                                     |
| ---------- | ----------------------- | -------------------------------------------------------------- |
| `API_BASE` | `http://localhost:8000` | Base URL of the Stepwise FastAPI backend the BFF proxies to.   |
| `DATA_DIR` | `../data`               | Directory the `/api/frame` route reads step screenshots from.  |

In Docker these are set in `docker-compose.yml`.

## Contributing

See the root [CONTRIBUTING.md](../CONTRIBUTING.md). Before opening a PR, make
sure `npm run lint`, `npm run test`, and `npm run build` pass.
