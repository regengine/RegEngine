/**
 * Step 2: How Account Creation Works
 * ------------------------------------
 * EXPLAINER showing what the signup experience looks like.
 * Links to real /signup and /accept-invite pages.
 */
import { ACCENT, GRAY, GRAY_LIGHT, BORDER } from "../shared/styles";
import { Card, SectionTitle, InfoCallout } from "../shared/components";

export default function HowSignupWorks({ setView, VIEWS }) {
  const fields = [
    { label: "Company Name", note: "Pre-filled from invite (locked)" },
    { label: "Your Name", note: "The person managing compliance" },
    { label: "Email", note: "Pre-filled from invite (locked)" },
    { label: "Password", note: "12+ characters required" },
    { label: "Role", note: "Compliance Officer, QA Manager, Operations, or Other" },
  ];

  return (
    <div>
      <SectionTitle sub="What the signup experience looks like after you accept an invite">
        Step 2: Account Creation
      </SectionTitle>

      <Card>
        <div style={{ textAlign: "center", marginBottom: 16 }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: ACCENT }}>RegEngine</div>
          <div style={{ fontSize: 12, color: GRAY }}>You&apos;ve been invited by <strong>FreshCo Distribution</strong></div>
        </div>

        <div style={{ border: `1px solid ${BORDER}`, borderRadius: 8, padding: 16, backgroundColor: GRAY_LIGHT }}>
          {fields.map((f) => (
            <div key={f.label} style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "var(--re-text-secondary)", marginBottom: 2 }}>{f.label}</div>
              <div style={{
                border: `1px solid ${BORDER}`, borderRadius: 8,
                padding: "10px 14px", fontSize: 12,
                color: GRAY, backgroundColor: "var(--re-surface-elevated)",
              }}>
                {f.note}
              </div>
            </div>
          ))}
        </div>

        <div style={{ fontSize: 11, color: GRAY, marginTop: 12 }}>
          Company name and email are locked from the invite to prevent mismatched records. Your compliance data is encrypted at rest and in transit.
        </div>
      </Card>

      <InfoCallout>
        After creating your account, you&apos;ll register your facilities, scope your food categories, and start logging CTE events. The next steps are where the real work begins.
      </InfoCallout>

      <div className="onb-nav-row" style={{ marginTop: 16, display: "flex", justifyContent: "space-between" }}>
        <button
          onClick={() => setView(VIEWS.HOW_INVITE)}
          style={{
            padding: "8px 20px", borderRadius: 8,
            backgroundColor: "transparent", color: ACCENT,
            border: `1px solid ${ACCENT}`, fontWeight: 600, fontSize: 13, cursor: "pointer",
          }}
        >
          ← Back
        </button>
        <button
          onClick={() => setView(VIEWS.FACILITY_SETUP)}
          style={{
            padding: "8px 20px", borderRadius: 8,
            backgroundColor: ACCENT, color: "var(--re-surface-base)",
            border: "none", fontWeight: 600, fontSize: 13, cursor: "pointer",
          }}
        >
          Next: Register a Facility →
        </button>
      </div>
    </div>
  );
}
