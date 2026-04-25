/**
 * Step 3: Facility Registration (LIVE)
 * Calls apiClient.createSupplierFacility — this is real.
 */
import { useState } from "react";
import { apiClient } from "@/lib/api-client";
import { ACCENT, GRAY, GRAY_LIGHT, BORDER, ERROR } from "../shared/styles";
import { Card, SectionTitle, FormField } from "../shared/components";
import { VIEWS } from "../shared/styles";

const SUPPLY_CHAIN_ROLES = ["Grower", "Packer", "Processor", "Distributor", "Importer"];

export default function FacilitySetup({ setView, onFacilityCreated, onEvent, isLoggedIn }) {
  const [form, setForm] = useState({
    name: "", street: "", city: "", state: "", zip: "", fda_reg: "", roles: [],
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const update = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const toggleRole = (role) => setForm((f) => ({
    ...f,
    roles: f.roles.includes(role) ? f.roles.filter((r) => r !== role) : [...f.roles, role],
  }));

  const saveFacility = async () => {
    if (!isLoggedIn) { setError("Log in to register a facility."); return; }
    setSaving(true);
    setError("");
    try {
      const facility = await apiClient.createSupplierFacility(form);
      onFacilityCreated?.(facility.id);
      onEvent?.({ event_name: "step_completed", step: VIEWS.FACILITY_SETUP, status: "success", facility_id: facility.id });
      setView(VIEWS.FTL_SCOPING);
    } catch {
      setError("Could not save facility. Confirm you are logged in and try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <SectionTitle sub="One supplier can have multiple facilities — each with its own FTL scope">
        Step 3: Facility Registration
      </SectionTitle>

      <Card>
        <div style={{ fontSize: 13, fontWeight: 600, color: GRAY, marginBottom: 12 }}>ADD FACILITY (1 of N)</div>
        <div style={{ border: `1px solid ${BORDER}`, borderRadius: 6, padding: 16, backgroundColor: GRAY_LIGHT }}>
          {[
            ["Facility Name", "name", "e.g. Salinas Valley Packhouse"],
            ["Street Address", "street", "e.g. 1200 Abbott St"],
            ["City", "city", "e.g. Salinas"],
            ["State", "state", "e.g. CA"],
            ["ZIP / Postal Code", "zip", "e.g. 93901"],
            ["FDA Registration Number (if applicable)", "fda_reg", "e.g. 12345678901"],
          ].map(([label, key, placeholder]) => (
            <FormField
              key={key}
              label={label}
              placeholder={placeholder}
              value={form[key]}
              onChange={update(key)}
              disabled={!isLoggedIn}
            />
          ))}

          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--re-text-secondary)", marginBottom: 6 }}>Supply Chain Role(s)</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {SUPPLY_CHAIN_ROLES.map((role) => (
                <button
                  key={role}
                  onClick={() => isLoggedIn && toggleRole(role)}
                  style={{
                    padding: "6px 12px", borderRadius: 6, fontSize: 12, fontWeight: 500, cursor: isLoggedIn ? "pointer" : "default",
                    backgroundColor: form.roles.includes(role) ? "var(--re-brand-muted)" : "transparent",
                    color: form.roles.includes(role) ? ACCENT : GRAY,
                    border: `1px solid ${form.roles.includes(role) ? ACCENT : BORDER}`,
                  }}
                >
                  {role}
                </button>
              ))}
            </div>
          </div>
        </div>

        {error && <div style={{ marginTop: 10, fontSize: 12, color: ERROR }}>{error}</div>}

        <div style={{ marginTop: 14, display: "flex", gap: 10, alignItems: "center" }}>
          <button
            onClick={saveFacility}
            disabled={saving || !isLoggedIn}
            style={{
              padding: "10px 24px", borderRadius: 8,
              backgroundColor: ACCENT, color: "var(--re-surface-base)",
              border: "none", fontWeight: 600, fontSize: 13, cursor: "pointer",
              opacity: (saving || !isLoggedIn) ? 0.6 : 1,
            }}
          >
            {saving ? "Saving..." : "Save & Continue to FTL Scoping"}
          </button>
          <button
            onClick={() => {/* add another facility */}}
            style={{
              padding: "10px 24px", borderRadius: 8,
              backgroundColor: "transparent", color: "var(--re-text-secondary)",
              border: `1px solid ${BORDER}`, fontWeight: 500, fontSize: 13, cursor: "pointer",
            }}
          >
            + Add Another Facility
          </button>
        </div>

        {!isLoggedIn && (
          <div style={{ marginTop: 12, fontSize: 12, color: GRAY }}>
            <a href="/login?redirect=/onboarding/setup/welcome" style={{ color: ACCENT, fontWeight: 600 }}>Log in</a> to register your facility and start recording CTE events.
          </div>
        )}

        <div style={{ marginTop: 12 }}>
          <a href="/onboarding/bulk-upload" style={{ fontSize: 12, color: ACCENT }}>
            Or upload facilities, TLCs, and CTE events in bulk →
          </a>
        </div>
      </Card>
    </div>
  );
}
