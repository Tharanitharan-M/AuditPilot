-- init.sql — runs once on first container start via docker-entrypoint-initdb.d
-- Purpose: enable pgvector and create the Langfuse database for local dev.
-- This file is READ-ONLY mounted; do not use it for application migrations.
-- Application schema migrations live in apps/api/db/migrations/.

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create Langfuse database for local self-hosted dev (opt-in profile)
-- Safe to run even when the langfuse profile is not active.
SELECT 'CREATE DATABASE langfuse'
WHERE NOT EXISTS (
  SELECT FROM pg_database WHERE datname = 'langfuse'
)\gexec
