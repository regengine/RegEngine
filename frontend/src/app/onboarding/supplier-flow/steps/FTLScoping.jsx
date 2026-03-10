/**
 * Step 4: FTL Category Scoping (LIVE)
 * Calls apiClient.getFacilityRequiredCTEs and apiClient.setFacilityFTLCategories
 */
import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { ACCENT, ACCENT_LIGHT, GRAY, GRAY_LIGHT, BORDER, ERROR, BLUE, BLUE_LIGHT } from "../shared/styles";
import { Card, SectionTitle, InfoCallout } from "../shared/components";
import { VIEWS, FTL_CATEGORIES, CTE_TYPES } from "../shared/styles";

export default function FTLScoping({ facilityId, setView, onRequiredCTEsChange, onEvent, isLoggedIn }) {
  const [categories, setCategories] = useState(FTL_CATEGORIES);
  const [selected, setSelected] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Load real catalog + existing scoping if logged in
  useEffect(() => {
    if (!isLoggedIn || !facilityId) return;
    let cancelled = false;

    (async () => {
      try {
        const cats = await apiClient.getFTLCategories();
        if (!cancelled && cats?.length) setCategories(cats);
      } catch { /* keep local fallback */ }

      try {
        const data = await apiClient.getFacilityRequiredCTEs(facilityId);
        if (!cancelled) {
          setSelected((data.categories || []).map((c) => c.id));
          onRequiredCTEsChange?.(data.required_ctes || []);
        }
      } catch {
        if (!cancelled) onRequiredCTEsChange?.([]);
      }
    })();

    return () => { cancelled = true; };
  }, [facilityId, isLoggedIn, onRequiredCTEsChange]);

  const toggle = (id) => setSelected((prev) =>
    prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
  );

  // Derived: which CTE types are required based on selected categories
  const requiredCTEs = [...new Set(
    categories.filter((c) => selected.includes(c.id)).flatMap((c) => c.ctes)
  )];

  const saveScoping = async () => {
    if (!isLoggedIn) return;
    setSaving(true);
    setError("");
    try {
      await apiClient.setFacilityFTLCategories(facilityId, { category_ids: selected });
      onRequiredCTEsChange?.(requiredCTEs);
      onEvent?.({ event_name: "step_completed", step: VIEWS.FTL_SCOPING, status: "success" });
      setView(VIEWS.CTE_CAPTURE);
    } catch {
      setError("Could not save FTL scoping. Try again.");
    } finally {
      setSaving(false);
    }
  };

  if (!facilityId) {
    return (
      <div>
        <SectionTitle sub="RegEngine auto-determines your required CTEs based on the foods you handle">
          Step 4: FTL Category Scoping
        </SectionTitle>
        <Card>
          <div style={{ fontSize: 13, color: GRAY, padding: 20, textAlign: "center" }}>
            Register a facility in Step 3 first, then come back to assign food categories.
          </div>
          <div style={{ textAlign: "center", marginTop: 8 }}>
            <button
              onClick={() => setView(VIEWS.FACILITY_SETUP)}
              style={{
                padding: "8px 18px", borderRadius: 8,
                backgroundColor: ACCENT, color: "var(--re-surface-base)",
                border: "none", fontWeight: 600, fontSize: 12, cursor: "pointer",
              }}
            >
              ← Go to Facility Registration
            </button>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <SectionTitle sub="Select the FDA Food Traceability List categories this facility handles">
        Step 4: FTL Category Scoping
      </SectionTitle>

      <Card>
        <div style={{ fontSize: 13, fontWeight: 600, color: GRAY, marginBottom: 12 }}>SELECT FOOD CATEGORIES</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {categories.map((cat) => (
            <button
              key={cat.id}
              onClick={() => isLoggedIn && toggle(cat.id)}
              style={{
                padding: "8px 14px", borderRadius: 8, fontSize: 12, fontWeight: 500,
                cursor: isLoggedIn ? "pointer" : "default",
                backgroundColor: selected.includes(cat.id) ? ACCENT_LIGHT : "transparent",
                color: selected.includes(cat.id) ? ACCENT : GRAY,
                border: `1px solid ${selected.includes(cat.id) ? ACCENT : BORDER}`,
              }}
            >
              {cat.name}
            </button>
          ))}
        </div>

        {requiredCTEs.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--re-text-secondary)", marginBottom: 6 }}>
              Required CTEs for your selection:
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {requiredCTEs.map((cte) => (
                <span key={cte} style={{
                  padding: "4px 10px", borderRadius: 4, fontSize: 11, fontWeight: 500,
                  backgroundColor: BLUE_LIGHT, color: BLUE,
                }}>
                  {CTE_TYPES[cte]?.label || cte}
                </span>
              ))}
            </div>
          </div>
        )}

        {error && <div style={{ marginTop: 10, fontSize: 12, color: ERROR }}>{error}</div>}

        <div className="onb-selection-actions" style={{ marginTop: 14 }}>
          <button
            onClick={saveScoping}
            disabled={saving || !isLoggedIn || selected.length === 0}
            style={{
              padding: "8px 18px", borderRadius: 8,
              backgroundColor: ACCENT, color: "var(--re-surface-base)",
              border: "none", fontWeight: 600, fontSize: 12, cursor: "pointer",
              opacity: (saving || !isLoggedIn || selected.length === 0) ? 0.6 : 1,
            }}
          >
            {saving ? "Saving..." : "Save & Continue to CTE Entry"}
          </button>
        </div>
      </Card>

      <InfoCallout>
        RegEngine uses FSMA 204&apos;s Food Traceability List to auto-determine which Critical Tracking Events
        you need to record. Select the foods you handle and we do the rest.
      </InfoCallout>
    </div>
  );
}
