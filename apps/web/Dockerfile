# syntax=docker/dockerfile:1.7
# =============================================================================
# AuditPilot Web — multi-stage Dockerfile (Next.js 15)
# =============================================================================
# Build context is the repo root (see docker-compose.yml `context: .`), so
# paths are relative to /path/to/auditpilot/.
#
# Stages:
#   base  — Node 22-slim with pnpm
#   deps  — installed node_modules (workspace-aware)
#   dev   — hot-reload next dev for `docker compose up web`
#   build — next build (standalone output)
#   prod  — minimal non-root runtime for Vercel / Cloud Run (Sprint 11)
#
# Refs: PLAN.md chunk 2.2.
# =============================================================================

# ── base ─────────────────────────────────────────────────────────────────────
FROM node:22-slim AS base
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate
WORKDIR /app

# ── deps ─────────────────────────────────────────────────────────────────────
FROM base AS deps
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY apps/web/package.json ./apps/web/package.json
# Copy any workspace packages that web depends on (package.json only for
# pnpm install layer caching — source is copied later).
COPY packages/ ./packages/
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile

# ── dev ──────────────────────────────────────────────────────────────────────
FROM deps AS dev
COPY apps/web ./apps/web
EXPOSE 3000
CMD ["pnpm", "--filter", "web", "dev"]

# ── build ────────────────────────────────────────────────────────────────────
FROM deps AS build
COPY apps/web ./apps/web
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter web build

# ── prod ─────────────────────────────────────────────────────────────────────
FROM node:22-slim AS prod
RUN groupadd -r appuser -g 1001 \
    && useradd -r -u 1001 -g appuser -m -d /home/appuser appuser
WORKDIR /app

COPY --from=build --chown=appuser:appuser /app/apps/web/.next/standalone ./
COPY --from=build --chown=appuser:appuser /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=appuser:appuser /app/apps/web/public ./apps/web/public

USER appuser
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
