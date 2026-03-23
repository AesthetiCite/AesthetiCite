import { defineConfig } from "drizzle-kit";

if (!process.env.DATABASE_URL) {
  throw new Error("DATABASE_URL must be set");
}

// IMPORTANT: Use `npx drizzle-kit migrate` (not `npm run db:push`) to apply schema changes.
// The `db:push` command introspects ALL database tables — including Python-managed ones —
// and generates broken SQL for GIN/tsvector indexes on tables outside tablesFilter.
// Only three tables are drizzle-managed: conversations, messages, search_history.
// To add a new table: (1) add to schema.ts, (2) run `npx drizzle-kit generate`, (3) run `npx drizzle-kit migrate`.
export default defineConfig({
  out: "./migrations",
  schema: "./shared/schema.ts",
  dialect: "postgresql",
  dbCredentials: {
    url: process.env.DATABASE_URL,
  },
  tablesFilter: ["conversations", "messages", "search_history"],
  strict: true,
  verbose: true,
});
