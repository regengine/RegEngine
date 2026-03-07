/**
 * Supplier Onboarding Flow — Main Orchestrator
 * ──────────────────────────────────────────────
 * Replaces the 1,293-line monolith with a clean router that:
 *  1. Manages view state + sidebar nav
 *  2. Detects isLoggedIn and threads it to every step
 *  3. Fires lightweight funnel events (non-blocking)
 *  4. Loads FTL catalog + social proof on mount
 *
 * Drop-in replacement: same route, same apiClient, same CSS vars.
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";

import { ACCENT, ACCENT_LIGHT, GRAY, BORDER } from "./shared/styles";
import { VIEWS, VIEW_STEP_NUMBER } from "./shared/styles";

import Overview from "./steps/Overview";
import HowInviteWorks from "./steps/HowInviteWorks";
import HowSignupWorks from "./steps/HowSignupWorks";
import FacilitySetup from "./steps/FacilitySetup";
import FTLScoping from "./steps/FTLScoping";
import CTEEntry from "./steps/CTEEntry";
import TLCManagement from "./steps/TLCManagement";
import Dashboard from "./steps/Dashboard";
import FDAExport from "./steps/FDAExport";

/* ── Sidebar nav items ───────────────────────────────────────────── */
const NAV_ITEMS = [
  { id: VIEWS.OVERVIEW, label: "Overview", icon: "🏠" },
  { id: VIEWS.HOW_INVITE, label: "1. Invite", icon: "📧" },
  { id: VIEWS.HOW_SIGNUP, label: "2. Signup", icon: "👤" },
  { id: VIEWS.FACILITY_SETUP, label: "3. Facility", icon: "🏭" },
  { id: VIEWS.FTL_SCOPING, label: "4. FTL Scope", icon: "🥬" },
  { id: VIEWS.CTE_CAPTURE, label: "5. CTE Entry", icon: "📝" },
  { id: VIEWS.TLC_MGMT, label: "6. TLCs", icon: "🏷️" },
  { id: VIEWS.DASHBOARD, label: "7. Dashboard", icon: "📊" },
  { id: VIEWS.FDA_EXPORT, label: "8. FDA Export", icon: "📄" },
];

/* ── Auth detection (simple heuristic — replace with real auth context) ── */
function useIsLoggedIn() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  useEffect(() => {
    // Check for auth cookie or session token
    const hasToken =
      typeof document !== "undefined" &&
      (document.cookie.includes("session_token=") || document.cookie.includes("access_token="));
    setIsLoggedIn(hasToken);
  }, []);
  return isLoggedIn;
}

/* ── Main component ──────────────────────────────────────────────── */
export default function SupplierOnboardingFlow() {
  const isLoggedIn = useIsLoggedIn();
  const [view, setView] = useState(VIEWS.OVERVIEW);
  const [facilityId, setFacilityId] = useState(null);
  const [requiredCTEs, setRequiredCTEs] = useState([]);
  const [tlcRefreshKey, setTlcRefreshKey] = useState(0);
  const [socialProof, setSocialProof] = useState(null);

  /* ── Funnel event tracker (fire-and-forget) ─────────────────── */
  const trackFunnelEvent = useCallback((payload) => {
    void apiClient.trackSupplierFunnelEvent(payload).catch(() => {});
  }, []);

  /* ── Load social proof on mount ─────────────────────────────── */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const payload = await apiClient.getSupplierSocialProof();
        if (!cancelled) setSocialProof(payload);
      } catch { /* keep UI usable */ }
    })();
    return () => { cancelled = true; };
  }, [tlcRefreshKey]);

  /* ── Track step views ───────────────────────────────────────── */
  useEffect(() => {
    void apiClient.trackSupplierFunnelEvent({
      event_name: "step_viewed",
      step: view,
      status: "viewed",
      facility_id: facilityId || undefined,
      metadata: { step_number: VIEW_STEP_NUMBER[view] || null },
    }).catch(() => {});
  }, [view, facilityId]);

  /* ── View router ────────────────────────────────────────────── */
  const viewComponents = {
    [VIEWS.OVERVIEW]: (
      <Overview setView={setView} socialProof={socialProof} facilityId={facilityId} isLoggedIn={isLoggedIn} />
    ),
    [VIEWS.HOW_INVITE]: (
      <HowInviteWorks setView={setView} VIEWS={VIEWS} />
    ),
    [VIEWS.HOW_SIGNUP]: (
      <HowSignupWorks setView={setView} VIEWS={VIEWS} />
    ),
    [VIEWS.FACILITY_SETUP]: (
      <FacilitySetup setView={setView} onFacilityCreated={setFacilityId} onEvent={trackFunnelEvent} isLoggedIn={isLoggedIn} />
    ),
    [VIEWS.FTL_SCOPING]: (
      <FTLScoping facilityId={facilityId} setView={setView} onRequiredCTEsChange={setRequiredCTEs} onEvent={trackFunnelEvent} isLoggedIn={isLoggedIn} />
    ),
    [VIEWS.CTE_CAPTURE]: (
      <CTEEntry requiredCTEs={requiredCTEs} facilityId={facilityId} onCTESubmitted={() => setTlcRefreshKey((k) => k + 1)} onEvent={trackFunnelEvent} isLoggedIn={isLoggedIn} />
    ),
    [VIEWS.TLC_MGMT]: (
      <TLCManagement facilityId={facilityId} refreshKey={tlcRefreshKey} onEvent={trackFunnelEvent} isLoggedIn={isLoggedIn} />
    ),
    [VIEWS.DASHBOARD]: (
      <Dashboard facilityId={facilityId} refreshKey={tlcRefreshKey + requiredCTEs.length} isLoggedIn={isLoggedIn} />
    ),
    [VIEWS.FDA_EXPORT]: (
      <FDAExport facilityId={facilityId} refreshKey={tlcRefreshKey + requiredCTEs.length} onEvent={trackFunnelEvent} isLoggedIn={isLoggedIn} />
    ),
  };

  return (
    <div style={{
      display: "flex", minHeight: "calc(100vh - 56px)",
      fontFamily: "Arial, sans-serif",
      backgroundColor: "var(--re-surface-base)",
      color: "var(--re-text-primary)",
    }}>
      {/* ── Sidebar ──────────────────────────────────────────── */}
      <div style={{
        width: 220, backgroundColor: "var(--re-surface-elevated)",
        padding: "16px 0", flexShrink: 0, overflowY: "auto",
      }}>
        <div style={{ padding: "0 14px 16px", borderBottom: `1px solid ${BORDER}` }}>
          <div style={{ fontSize: 16, fontWeight: 800, color: ACCENT }}>RegEngine</div>
          <div style={{ fontSize: 10, color: "var(--re-text-muted)", marginTop: 2 }}>Guided Supplier Setup</div>
        </div>
        <div style={{ padding: "8px 0" }}>
          {NAV_ITEMS.map((item) => (
            <div
              key={item.id}
              onClick={() => setView(item.id)}
              style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "9px 14px", cursor: "pointer",
                backgroundColor: view === item.id ? ACCENT_LIGHT : "transparent",
                borderLeft: view === item.id ? `3px solid ${ACCENT}` : "3px solid transparent",
                transition: "all 0.1s",
              }}
            >
              <span style={{ fontSize: 14 }}>{item.icon}</span>
              <span style={{
                fontSize: 12,
                color: view === item.id ? "var(--re-text-primary)" : "var(--re-text-disabled)",
                fontWeight: view === item.id ? 600 : 500,
              }}>
                {item.label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Main content ─────────────────────────────────────── */}
      <div style={{ flex: 1, overflowY: "auto", padding: 24 }}>
        {viewComponents[view]}
      </div>
    </div>
  );
}
