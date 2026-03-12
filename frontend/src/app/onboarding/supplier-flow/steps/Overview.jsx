/**
 * Overview: Step grid with progress tracking and social proof
 */
import { ACCENT, GRAY, BLUE } from "../shared/styles";
import { SectionTitle, FlowStep, DemoBanner, InfoCallout } from "../shared/components";
import { VIEWS } from "../shared/styles";

const STEPS = [
  { view: VIEWS.HOW_INVITE, title: "How the Invite Works", desc: "What happens on the buyer's side before you get your invite link", isDemo: true },
  { view: VIEWS.HOW_SIGNUP, title: "Account Creation", desc: "What the signup experience looks like after accepting an invite", isDemo: true },
  { view: VIEWS.FACILITY_SETUP, title: "Facility Registration", desc: "Register your physical locations with FDA registration numbers" },
  { view: VIEWS.FTL_SCOPING, title: "FTL Category Scoping", desc: "Select the Food Traceability List categories each facility handles" },
  { view: VIEWS.CTE_CAPTURE, title: "CTE/KDE Data Entry", desc: "Record Critical Tracking Events with all required Key Data Elements" },
  { view: VIEWS.TLC_MGMT, title: "Traceability Lot Codes", desc: "Manage TLCs — every CTE record links to a traceability lot code" },
  { view: VIEWS.DASHBOARD, title: "Supplier Dashboard", desc: "Your compliance posture — coverage, freshness, and chain integrity" },
  { view: VIEWS.FDA_EXPORT, title: "FDA 24-Hour Export", desc: "Generate the sortable spreadsheet FDA requires within 24 hours" },
];

function getStepStatus(step, facilityId, isLoggedIn) {
  // Steps 1-2 are always accessible (explainers)
  if (step.isDemo) return "complete";
  // Steps 3+ require login for "active" status
  if (!isLoggedIn) return "pending";
  // If facility exists, step 3 is complete
  if (step.view === VIEWS.FACILITY_SETUP && facilityId) return "complete";
  return "pending";
}

export default function Overview({ setView, socialProof, facilityId, isLoggedIn }) {
  return (
    <div>
      <SectionTitle sub="FSMA 204 compliance onboarding — 8 steps from invite to FDA-ready export">
        Supplier Onboarding
      </SectionTitle>

      <DemoBanner isLoggedIn={isLoggedIn} />

      {socialProof && (
        <div className="onb-proof-row" style={{
          display: "flex", gap: 16, marginBottom: 16, fontSize: 12, color: GRAY,
        }}>
          {socialProof.supplier_count != null && (
            <span><strong style={{ color: ACCENT }}>{socialProof.supplier_count}</strong> suppliers onboarded</span>
          )}
          {socialProof.cte_count != null && (
            <span><strong style={{ color: ACCENT }}>{socialProof.cte_count.toLocaleString()}</strong> CTE events recorded</span>
          )}
          {socialProof.export_count != null && (
            <span><strong style={{ color: ACCENT }}>{socialProof.export_count}</strong> FDA exports generated</span>
          )}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {STEPS.map((step, i) => (
          <FlowStep
            key={step.view}
            number={i + 1}
            title={step.title}
            description={step.desc}
            isDemo={step.isDemo}
            status={getStepStatus(step, facilityId, isLoggedIn)}
            onClick={() => setView(step.view)}
          />
        ))}
      </div>

      <InfoCallout>
        Steps 1-2 preview how your buyers invite you. Steps 3-8 are the guided setup you complete after signup.
      </InfoCallout>
    </div>
  );
}
