import { defineConfig } from "drizzle-kit";

// Prefer Neon so both the Node.js layer and the Python backend share one DB.
// This removes the Replit-local PostgreSQL from the deployment path entirely —
// no "copy dev DB to production" step, no multi-GB timeout.
const dbUrl = process.env.NEON_DATABASE_URL || process.env.DATABASE_URL;

if (!dbUrl) {
  throw new Error("Neither NEON_DATABASE_URL nor DATABASE_URL is set");
}

// IMPORTANT: Use `npx drizzle-kit migrate` (not `npm run db:push`) to apply schema changes.
// The `db:push` command introspects ALL database tables — including Python-managed ones —
// and generates broken SQL for GIN/tsvector indexes on tables outside tablesFilter.
// Only three tables are drizzle-managed: conversations, messages, search_history.
// To add a new table: (1) add to schema.ts, (2) run `npx drizzle-kit generate`, (3) run `npx drizzle-kit migrate`.
//
// NOTE: Migrations are stored in `./drizzle/` (not `./migrations/`) to prevent
// Replit's deployment platform from auto-detecting and attempting to run them
// against its local PostgreSQL. This project uses Neon DB exclusively.
export default defineConfig({
  out: "./drizzle",
  schema: "./shared/schema.ts",
  dialect: "postgresql",
  dbCredentials: {
    url: dbUrl,
  },
  tablesFilter: ["conversations", "messages", "search_history"],
  strict: true,
  verbose: true,
});
