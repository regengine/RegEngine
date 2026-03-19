/**
 * use-dashboard-refresh.ts
 *
 * Lightweight cross-component refresh coordination for dashboard pages.
 *
 * Problem: Upload flows (receiving dock, bulk upload, CSV ingest) write data
 * to the backend, but dashboard pages only fetch on mount. Users navigate
 * back to the dashboard and see stale data.
 *
 * Solution:
 * 1. `useDashboardRefresh(callback)` — dashboard pages register a reload
 *    callback. It fires on:
 *    - BroadcastChannel "dashboard-refresh" events (same origin, cross-tab)
 *    - `visibilitychange` when the tab becomes visible again
 *    - Custom DOM event (same-tab, for SPA navigations)
 *
 * 2. `notifyDashboardRefresh()` — upload flows call this after a successful
 *    ingest/commit. Fires both BroadcastChannel + DOM event so the dashboard
 *    refetches whether it's in the same tab or a different one.
 */

import { useEffect, useRef } from 'react';

const CHANNEL_NAME = 'regengine-dashboard-refresh';
const DOM_EVENT = 'regengine:dashboard-refresh';

/* ── Listener hook for dashboard pages ── */

export function useDashboardRefresh(callback: () => void) {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  useEffect(() => {
    const invoke = () => callbackRef.current();

    // 1. BroadcastChannel — cross-tab refresh
    let bc: BroadcastChannel | null = null;
    try {
      bc = new BroadcastChannel(CHANNEL_NAME);
      bc.onmessage = invoke;
    } catch {
      // BroadcastChannel not supported (e.g. older Safari) — degrade gracefully
    }

    // 2. visibilitychange — refetch when user tabs back
    const onVisibility = () => {
      if (document.visibilityState === 'visible') invoke();
    };
    document.addEventListener('visibilitychange', onVisibility);

    // 3. Custom DOM event — same-tab SPA navigation
    window.addEventListener(DOM_EVENT, invoke);

    return () => {
      bc?.close();
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener(DOM_EVENT, invoke);
    };
  }, []);
}

/* ── Notify function for upload flows ── */

export function notifyDashboardRefresh() {
  // BroadcastChannel (cross-tab)
  try {
    const bc = new BroadcastChannel(CHANNEL_NAME);
    bc.postMessage({ type: 'refresh', ts: Date.now() });
    bc.close();
  } catch {
    // not supported — fall through to DOM event
  }

  // Custom DOM event (same-tab)
  window.dispatchEvent(new CustomEvent(DOM_EVENT));
}
