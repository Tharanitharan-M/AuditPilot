import { defineConfig } from "drizzle-kit";

// Uses DIRECT_URL (bypasses Neon's connection pooler) for migrations.
// Falls back to DATABASE_URL for local Docker dev where there is no pooler.
const url = process.env.DIRECT_URL ?? process.env.DATABASE_URL;
if (!url) {
  throw new Error("DIRECT_URL or DATABASE_URL must be set for Drizzle migrations");
}

export default defineConfig({
  dialect: "postgresql",
  schema: "./apps/api/db/schema.ts",
  out: "./apps/api/db/migrations",
  dbCredentials: { url },
  migrations: {
    table: "__drizzle_migrations",
    schema: "public",
  },
  verbose: true,
  strict: true,
});
