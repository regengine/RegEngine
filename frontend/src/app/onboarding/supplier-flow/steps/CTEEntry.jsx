/**
 * Step 5: CTE/KDE Data Entry (LIVE)
 * Calls apiClient.submitSupplierCTEEvent
 */
import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { ACCENT, ACCENT_LIGHT, GRAY, BORDER, ERROR, BLUE } from "../shared/styles";
import { Card, SectionTitle, InfoCallout } from "../shared/components";
import { VIEWS, CTE_TYPES } from "../shared/styles";

export default function CTEEntry({ requiredCTEs = [], facilityId, onCTESubmitted, onEvent, isLoggedIn }) {
  const availableCTEs = (requiredCTEs.length > 0 ? requiredCTEs : Object.keys(CTE_TYPES)).filter((key) => Boolean(CTE_TYPES[key]));
  const [activeCTE, setActiveCTE] = useState(availableCTEs[0] || "shipping");
  const [formValues, setFormValues] = useState({});
  const [submitResult, setSubmitResult] = useState(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!availableCTEs.includes(activeCTE)) {
      setActiveCTE(availableCTEs[0] || "shipping");
    }
  }, [availableCTEs, activeCTE]);

  useEffect(() => {
    setFormValues({});
    setSubmitResult(null);
    setError("");
  }, [activeCTE]);

  const cte = CTE_TYPES[activeCTE];
  if (!cte) return null;

  const setField = (name, value) => {
    setFormValues((prev) => ({ ...prev, [name]: value }));
  };

  const inferTLC = () =>
    formValues.traceability_lot_code || formValues.output_tlc || formValues.input_tlc || "";

  const submitCTE = async () => {
    if (!isLoggedIn) return;
    if (!facilityId) {
      setError("Create a facility first, then submit CTE/KDE events.");
      return;
    }
    const tlcCode = inferTLC();
    if (!tlcCode) {
      setError("Enter a Traceability Lot Code before submitting.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const response = await apiClient.submitSupplierCTEEvent(facilityId, {
        cte_type: activeCTE,
        tlc_code: tlcCode,
        kde_data: formValues,
        obligation_ids: [],
      });
      setSubmitResult(response);
      onEvent?.({
        event_name: "cte_submitted",
        step: VIEWS.CTE_CAPTURE,
        status: "success",
        facility_id: facilityId,
        metadata: { cte_type: activeCTE, tlc_code: tlcCode, merkle_sequence: response.merkle_sequence },
      });
      onCTESubmitted?.();
    } catch {
      setError("Could not submit event. Check required fields and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (!facilityId) {
    return (
      <div>
        <SectionTitle sub="Dynamic forms pre-populated with required KDE fields based on CTE type">
          Step 5: CTE/KDE Data Entry
        </SectionTitle>
        <Card>
          <div style={{ fontSize: 13, color: GRAY, padding: 20, textAlign: "center" }}>
            Register a facility and scope your FTL categories first, then come back to enter CTE events.
          </div>
          <div style={{ textAlign: "center", marginTop: 8 }}>
            <button
              onClick={() => {/* parent handles nav */}}
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
      <SectionTitle sub="Dynamic forms pre-populated with required KDE fields based on CTE type">
        Step 5: CTE/KDE Data Entry
      </SectionTitle>

      {/* CTE type tabs */}
      <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
        {availableCTEs.map((key) => {
          const val = CTE_TYPES[key];
          if (!val) return null;
          return (
            <button
              key={key}
              onClick={() => isLoggedIn && setActiveCTE(key)}
              style={{
                padding: "6px 12px", borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: isLoggedIn ? "pointer" : "default",
                border: `1px solid ${activeCTE === key ? ACCENT : BORDER}`,
                backgroundColor: activeCTE === key ? ACCENT : "var(--re-surface-base)",
                color: activeCTE === key ? "var(--re-surface-base)" : GRAY,
              }}
            >
              {val.icon} {val.label}
            </button>
          );
        })}
      </div>

      <Card>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <span style={{ fontSize: 20 }}>{cte.icon}</span>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700 }}>New {cte.label} Event</div>
            <div style={{ fontSize: 11, color: GRAY }}>{cte.fields.length} required KDE fields per FSMA 204</div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          {cte.fields.map((f) => (
            <div key={f.name}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--re-text-secondary)", marginBottom: 2 }}>
                {f.label} {f.required && <span style={{ color: ERROR }}>*</span>}
              </div>
              {f.type === "select" ? (
                <select
                  value={formValues[f.name] || ""}
                  onChange={(e) => setField(f.name, e.target.value)}
                  disabled={!isLoggedIn}
                  style={{
                    width: "100%", border: `1px solid ${BORDER}`, borderRadius: 8,
                    padding: "10px 14px", fontSize: 12, boxSizing: "border-box",
                    color: "var(--re-text-primary)", backgroundColor: "var(--re-surface-elevated)",
                  }}
                >
                  <option value="">Select...</option>
                  {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              ) : (
                <input
                  type={f.type === "number" ? "number" : f.type === "date" ? "date" : "text"}
                  value={formValues[f.name] || ""}
                  onChange={(e) => setField(f.name, e.target.value)}
                  disabled={!isLoggedIn}
                  style={{
                    width: "100%", border: `1px solid ${BORDER}`, borderRadius: 8,
                    padding: "10px 14px", fontSize: 12, boxSizing: "border-box",
                    color: "var(--re-text-primary)", backgroundColor: "var(--re-surface-elevated)",
                  }}
                />
              )}
            </div>
          ))}
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          <button
            onClick={submitCTE}
            disabled={submitting || !isLoggedIn}
            style={{
              padding: "8px 20px", borderRadius: 8,
              backgroundColor: ACCENT, color: "var(--re-surface-base)",
              border: "none", fontWeight: 600, fontSize: 12, cursor: "pointer",
              opacity: (submitting || !isLoggedIn) ? 0.6 : 1,
            }}
          >
            {submitting ? "Submitting..." : "Submit & Hash (SHA-256)"}
          </button>
        </div>

        {submitResult && (
          <div style={{
            marginTop: 10, fontSize: 11, backgroundColor: ACCENT_LIGHT,
            borderRadius: 6, padding: "8px 10px", color: ACCENT,
          }}>
            Event recorded. SHA-256: <code>{submitResult.payload_sha256?.slice(0, 16)}...</code> | Merkle seq: <strong>{submitResult.merkle_sequence}</strong>
          </div>
        )}

        {error && <div style={{ marginTop: 10, fontSize: 12, color: ERROR }}>{error}</div>}
      </Card>

      <InfoCallout>
        Each CTE submission is hashed (SHA-256) and appended to a tamper-evident Merkle chain.
        Your KDE data is stored in Postgres and linked in the Neo4j graph for forward/backward trace queries.
      </InfoCallout>
    </div>
  );
}
