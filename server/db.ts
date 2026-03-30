import { drizzle } from "drizzle-orm/node-postgres";
import pg from "pg";
import * as schema from "@shared/schema";

// Prefer the Neon database URL so the Node.js layer uses the same external
// database as the Python backend.  This eliminates the Replit-managed local
// PostgreSQL from the deployment path and prevents the "copy dev DB to
// production" step from timing out (the local DB contains all RAG data).
const connectionString =
  process.env.NEON_DATABASE_URL || process.env.DATABASE_URL;

if (!connectionString) {
  throw new Error("Neither NEON_DATABASE_URL nor DATABASE_URL is set");
}

const pool = new pg.Pool({ connectionString });
export const db = drizzle(pool, { schema });
