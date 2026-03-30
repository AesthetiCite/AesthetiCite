/**
 * useSessionTracker.ts
 * ====================
 * React hook that tracks the current user's session.
 * - Calls POST /api/admin/sessions/start on mount
 * - Fires POST /api/admin/sessions/heartbeat every 60 seconds
 * - Calls POST /api/admin/sessions/end on unmount / logout
 * - Increments query count via trackQuery()
 *
 * INTEGRATION — in ask.tsx:
 *
 *   import { useSessionTracker } from "@/hooks/use-session-tracker";
 *
 *   // Inside the AskPage component, near the top:
 *   const { trackQuery } = useSessionTracker(token);
 *
 *   // Then wherever handleAsk() fires:
 *   trackQuery();
 */

import { useEffect, useRef, useCallback } from "react";

const HEARTBEAT_INTERVAL_MS = 60_000; // 60 seconds

export function useSessionTracker(token: string | null) {
  const queryCountRef   = useRef(0);
  const intervalRef     = useRef<ReturnType<typeof setInterval> | null>(null);
  const sessionStarted  = useRef(false);

  const headers = useCallback(() => ({
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }), [token]);

  // ── Start session ──────────────────────────────────────────────
  const startSession = useCallback(async () => {
    if (!token || sessionStarted.current) return;
    try {
      await fetch("/api/admin/sessions/start", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({}),
      });
      sessionStarted.current = true;
    } catch {
      // Silent — tracking failures must never affect the main UX
    }
  }, [token, headers]);

  // ── Heartbeat ──────────────────────────────────────────────────
  const sendHeartbeat = useCallback(async () => {
    if (!token) return;
    const inc = queryCountRef.current;
    queryCountRef.current = 0;
    try {
      await fetch("/api/admin/sessions/heartbeat", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({
          page_path: window.location.pathname,
          query_count_inc: inc,
        }),
      });
    } catch {
      // Restore count if heartbeat failed
      queryCountRef.current += inc;
    }
  }, [token, headers]);

  // ── End session ────────────────────────────────────────────────
  const endSession = useCallback(
    (reason: "logout" | "unload" = "unload") => {
      if (!token) return;
      // Use sendBeacon for page unload — fetch is unreliable there
      const body = JSON.stringify({ end_reason: reason });
      if (navigator.sendBeacon) {
        const blob = new Blob([body], { type: "application/json" });
        navigator.sendBeacon("/api/admin/sessions/end", blob);
      } else {
        fetch("/api/admin/sessions/end", {
          method: "POST",
          headers: headers(),
          body,
          keepalive: true,
        }).catch(() => {});
      }
      sessionStarted.current = false;
    },
    [token, headers]
  );

  // ── Track a query (call from handleAsk) ───────────────────────
  const trackQuery = useCallback(() => {
    queryCountRef.current += 1;
  }, []);

  // ── Lifecycle ──────────────────────────────────────────────────
  useEffect(() => {
    if (!token) return;

    startSession();

    intervalRef.current = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL_MS);

    // Send remaining queries on page hide / unload
    const handleVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        sendHeartbeat();
      }
    };
    const handleBeforeUnload = () => {
      endSession("unload");
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("beforeunload", handleBeforeUnload);
      endSession("unload");
    };
  }, [token, startSession, sendHeartbeat, endSession]);

  return { trackQuery, endSession };
}
