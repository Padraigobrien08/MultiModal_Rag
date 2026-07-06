# ── Dev stage: install deps only, source is bind-mounted at runtime ───────────
FROM node:26-slim AS dev
WORKDIR /app
COPY package*.json ./
RUN npm ci
EXPOSE 3000
CMD ["npm", "run", "dev"]

# ── Production build ──────────────────────────────────────────────────────────
FROM node:26-slim AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:26-slim AS runner

WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# Standalone output is self-contained; run as the built-in unprivileged user.
USER node

EXPOSE 3000

CMD ["node", "server.js"]
