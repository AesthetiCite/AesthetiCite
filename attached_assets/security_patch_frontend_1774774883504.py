"""
security_patch_frontend.py
===========================
Frontend security fixes — 3 files:

  FILE A — client/src/lib/auth.ts
            Add refresh token support + 401 interceptor

  FILE B — client/src/main.tsx
            Add Sentry frontend integration

  FILE C — index.html
            Add CSP meta tag + security meta tags

═══════════════════════════════════════════════════════════════════
FILE A — client/src/lib/auth.ts

Add these functions after the existing getToken / setToken / clearToken:

    // ── Refresh token storage ──────────────────────────────────
    export function getRefreshToken(): string | null {
      if (typeof window === "undefined") return null;
      return localStorage.getItem("aestheticite_refresh");
    }

    export function setRefreshToken(token: string): void {
      if (typeof window === "undefined") return;
      localStorage.setItem("aestheticite_refresh", token);
    }

    export function clearRefreshToken(): void {
      if (typeof window === "undefined") return;
      localStorage.removeItem("aestheticite_refresh");
    }

    // ── Refresh access token ───────────────────────────────────
    export async function refreshAccessToken(): Promise<string | null> {
      const refreshToken = getRefreshToken();
      if (!refreshToken) return null;
      try {
        const res = await fetch("/api/auth/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!res.ok) {
          clearToken();
          clearRefreshToken();
          return null;
        }
        const data = await res.json();
        setToken(data.access_token);
        if (data.refresh_token) setRefreshToken(data.refresh_token);
        return data.access_token;
      } catch {
        return null;
      }
    }

    // ── Authenticated fetch with auto-refresh ──────────────────
    // Use this instead of raw fetch() for all API calls that need auth.
    // It automatically retries with a fresh token if the first call
    // returns 401 (token expired).
    export async function authedFetch(
      url: string,
      options: RequestInit = {}
    ): Promise<Response> {
      const token = getToken();
      const headers: Record<string, string> = {
        ...(options.headers as Record<string, string> || {}),
      };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(url, { ...options, headers });

      if (res.status === 401) {
        // Token expired — try to refresh
        const newToken = await refreshAccessToken();
        if (!newToken) {
          // Refresh failed — redirect to login
          clearToken();
          clearRefreshToken();
          window.location.href = "/login";
          return res;
        }
        // Retry original request with new token
        headers["Authorization"] = `Bearer ${newToken}`;
        return fetch(url, { ...options, headers });
      }

      return res;
    }


Also update the login function to store the refresh token:

    Find in the existing login() function:
        setToken(data.access_token);

    Add after it:
        if (data.refresh_token) setRefreshToken(data.refresh_token);


═══════════════════════════════════════════════════════════════════
FILE B — client/src/main.tsx

Add Sentry frontend (run: npm install @sentry/react first):

    Add at the very top of main.tsx, before any other imports:

        import * as Sentry from "@sentry/react";

        Sentry.init({
          dsn: import.meta.env.VITE_SENTRY_DSN || "",
          environment: import.meta.env.MODE || "development",
          tracesSampleRate: import.meta.env.MODE === "production" ? 0.1 : 0,
          enabled: !!import.meta.env.VITE_SENTRY_DSN,
          beforeSend(event) {
            // Scrub any clinical data from error reports
            if (event.request?.data) {
              delete event.request.data;
            }
            return event;
          },
        });

Add VITE_SENTRY_DSN to your Railway env vars (get DSN from Sentry dashboard).
Set it to empty string in .env.local for local dev.


═══════════════════════════════════════════════════════════════════
FILE C — index.html (in the client/public/ or root directory)

Add these meta tags inside the <head> section:

    <!-- Security meta tags -->
    <meta http-equiv="X-Content-Type-Options" content="nosniff" />
    <meta http-equiv="X-Frame-Options" content="DENY" />
    <meta http-equiv="Referrer-Policy" content="strict-origin-when-cross-origin" />
    <meta name="robots" content="noindex, nofollow" />

    <!-- Prevent caching of clinical data in browser history -->
    <meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate" />
    <meta http-equiv="Pragma" content="no-cache" />

Note: The full Content-Security-Policy is set by the FastAPI middleware
in security_patch_main.py — no need to duplicate it in the HTML.


═══════════════════════════════════════════════════════════════════
ALSO: Add proxy route in server/routes.ts

    app.post("/api/auth/refresh", (req, res) =>
        proxyToFastAPI(req, res, "/auth/refresh"));

Add this near the other /api/auth/* routes.
"""
