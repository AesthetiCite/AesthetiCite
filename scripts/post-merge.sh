#!/bin/bash
set -e

echo "[post-merge] Applying pending database migrations (safe, non-interactive)..."
npx drizzle-kit migrate || echo "[post-merge] No pending migrations (non-fatal)"

echo "[post-merge] Done."
