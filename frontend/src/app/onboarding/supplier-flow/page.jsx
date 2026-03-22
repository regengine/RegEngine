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
  const [isMobile, setIsMobile] = useState(false);
  const [view, setView] = useState(VIEWS.OVERVIEW);
  const [facilityId, setFacilityId] = useState(null);
  const [requiredCTEs, setRequiredCTEs] = useState([]);
  const [tlcRefreshKey, setTlcRefreshKey] = useState(0);
  const [socialProof, setSocialProof] = useState(null);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const media = window.matchMedia("(max-width: 900px)");
    const update = () => setIsMobile(media.matches);
    update();
    if (typeof media.addEventListener === "function") {
      media.addEventListener("change", update);
      return () => media.removeEventListener("change", update);
    }
    media.addListener(update);
    return () => media.removeListener(update);
  }, []);

  /* ── Funnel event tracker (fire-and-forget) ─────────────────── */
  const trackFunnelEvent = useCallback((payload) => {
    if (!isLoggedIn) return;
    void apiClient.trackSupplierFunnelEvent(payload).catch(() => {});
  }, [isLoggedIn]);

  /* ── Load social proof on mount (only when authenticated) ──── */
  useEffect(() => {
    if (!isLoggedIn) return;
    let cancelled = false;
    (async () => {
      try {
        const payload = await apiClient.getSupplierSocialProof();
        if (!cancelled) setSocialProof(payload);
      } catch { /* keep UI usable */ }
    })();
    return () => { cancelled = true; };
  }, [isLoggedIn, tlcRefreshKey]);

  /* ── Track step views (only when authenticated) ──────────────── */
  useEffect(() => {
    if (!isLoggedIn) return;
    void apiClient.trackSupplierFunnelEvent({
      event_name: "step_viewed",
      step: view,
      status: "viewed",
      facility_id: facilityId || undefined,
      metadata: { step_number: VIEW_STEP_NUMBER[view] || null },
    }).catch(() => {});
  }, [isLoggedIn, view, facilityId]);

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
    <div className="onb-flow" style={{
      display: isMobile ? "block" : "flex", minHeight: "calc(100vh - 56px)",
      fontFamily: "Arial, sans-serif",
      backgroundColor: "var(--re-surface-base)",
      color: "var(--re-text-primary)",
    }}>
      {/* ── Sidebar ──────────────────────────────────────────── */}
      <div className="onb-sidebar" style={{
        width: isMobile ? "100%" : 220, backgroundColor: "var(--re-surface-elevated)",
        padding: isMobile ? "10px 0" : "16px 0", flexShrink: 0, overflowY: "auto",
      }}>
        <div style={{ padding: "0 14px 16px", borderBottom: `1px solid ${BORDER}` }}>
          <div style={{ fontSize: 16, fontWeight: 800, color: ACCENT }}>RegEngine</div>
          <div style={{ fontSize: 10, color: "var(--re-text-muted)", marginTop: 2 }}>Guided Supplier Setup</div>
        </div>
        <div className="onb-navlist" style={{
          padding: isMobile ? "8px 12px" : "8px 0",
          display: isMobile ? "flex" : "block",
          gap: isMobile ? 8 : 0,
          overflowX: isMobile ? "auto" : "visible",
        }}>
          {NAV_ITEMS.map((item) => (
            <div
              className="onb-navitem"
              key={item.id}
              onClick={() => setView(item.id)}
              style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "9px 14px", cursor: "pointer", whiteSpace: "nowrap",
                backgroundColor: view === item.id ? ACCENT_LIGHT : "transparent",
                borderLeft: !isMobile && view === item.id ? `3px solid ${ACCENT}` : "3px solid transparent",
                borderBottom: isMobile && view === item.id ? `2px solid ${ACCENT}` : "2px solid transparent",
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
      <div className="onb-main" style={{ flex: 1, overflowY: "auto", padding: isMobile ? 14 : 24 }}>
        {viewComponents[view]}
      </div>

      <style>{`
        @media (max-width: 900px) {
          .onb-navlist::-webkit-scrollbar { display: none; }
          .onb-navitem { border-radius: 8px; }
          .onb-main { overflow-x: hidden; }
          .onb-proof-row { flex-wrap: wrap; row-gap: 8px; }
          .onb-nav-row { flex-direction: column; align-items: stretch !important; gap: 8px; }
          .onb-nav-row button { width: 100%; }
          .onb-dashboard-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
          .onb-cte-fields { grid-template-columns: 1fr !important; }
          .onb-results-actions { flex-direction: column !important; }
          .onb-results-actions button { width: 100%; justify-content: center; }
          .onb-what-next-grid { grid-template-columns: 1fr !important; }
          .onb-fda-config-grid { grid-template-columns: 1fr !important; }
          .onb-actions-row { flex-direction: column !important; align-items: stretch !important; }
          .onb-actions-row > * { width: 100%; }
          .onb-table-scroll { overflow-x: auto; }
          .onb-fda-grid { min-width: 760px; }
          .onb-tlc-grid { min-width: 720px; }
          .onb-exemption-row { flex-direction: column !important; }
          .onb-exemption-actions { flex-direction: column !important; align-items: stretch !important; }
          .onb-exemption-actions > div { width: 100%; display: flex; flex-direction: column; gap: 8px; }
          .onb-exemption-actions button { width: 100%; }
          .onb-selection-actions { flex-direction: column !important; align-items: stretch !important; gap: 10px; }
          .onb-selection-actions button { width: 100%; justify-content: center; }
        }
      `}</style>
    </div>
  );
}
