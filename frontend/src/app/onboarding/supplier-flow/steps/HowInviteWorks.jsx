/**
 * Step 1: How the Buyer Invite Works
 * ------------------------------------
 * EXPLAINER only. No fake forms. Shows the buyer's perspective so the
 * supplier understands what happened before they landed here.
 */
import { ACCENT, ACCENT_LIGHT, GRAY, GRAY_LIGHT, BORDER, BLUE, BLUE_LIGHT } from "../shared/styles";
import { Card, SectionTitle, InfoCallout } from "../shared/components";

export default function HowInviteWorks({ setView, VIEWS }) {
  const steps = [
    { icon: "1", text: "Your buyer opens their RegEngine dashboard and clicks Invite Supplier." },
    { icon: "2", text: "They enter your company name, contact email, and the food categories they source from you." },
    { icon: "3", text: "RegEngine generates a unique, time-limited invite link and sends it to your email." },
    { icon: "4", text: "You click the link, create your account (next step), and begin onboarding." },
  ];

  return (
    <div>
      <SectionTitle sub="This is what happens on the buyer's side before you receive your invite">
        Step 1: How the Invite Works
      </SectionTitle>

      <Card>
        <div style={{ fontSize: 13, fontWeight: 600, color: GRAY, marginBottom: 16, textTransform: "uppercase", letterSpacing: 0.5 }}>
          Buyer&apos;s perspective
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {steps.map((s) => (
            <div key={s.icon} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
              <div style={{
                width: 28, height: 28, borderRadius: "50%",
                backgroundColor: ACCENT, color: "var(--re-surface-base)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 13, fontWeight: 700, flexShrink: 0,
              }}>
                {s.icon}
              </div>
              <div style={{ fontSize: 13, color: "var(--re-text-secondary)", lineHeight: 1.5, paddingTop: 3 }}>
                {s.text}
              </div>
            </div>
          ))}
        </div>

        {/* Visual mockup of what the email looks like */}
        <div style={{
          marginTop: 20,
          border: `1px solid ${BORDER}`,
          borderRadius: 8,
          padding: 16,
          backgroundColor: "var(--re-surface-elevated)",
        }}>
          <div style={{ fontSize: 11, color: GRAY, marginBottom: 8 }}>Sample invite email:</div>
          <div style={{ fontSize: 14, fontWeight: 600, color: "var(--re-text-primary)", marginBottom: 4 }}>
            FreshCo Distribution invited you to RegEngine
          </div>
          <div style={{ fontSize: 12, color: "var(--re-text-secondary)", marginBottom: 12 }}>
            They need your FSMA 204 traceability records for: <strong>Vegetables (leafy greens)</strong>, <strong>Fresh herbs</strong>
          </div>
          <div style={{
            display: "inline-block",
            padding: "8px 20px",
            borderRadius: 6,
            backgroundColor: ACCENT,
            color: "var(--re-surface-base)",
            fontSize: 13,
            fontWeight: 600,
          }}>
            Accept Invite & Create Account
          </div>
          <div style={{ fontSize: 11, color: GRAY, marginTop: 8 }}>
            Link expires in 30 days. Your buyer can resend if needed.
          </div>
        </div>
      </Card>

      <InfoCallout>
        Already received an invite? <a href="/accept-invite" style={{ color: ACCENT, fontWeight: 600 }}>Enter your invite code here</a> to jump straight to account setup.
      </InfoCallout>

      <div style={{ marginTop: 16, display: "flex", justifyContent: "flex-end" }}>
        <button
          onClick={() => setView(VIEWS.HOW_SIGNUP)}
          style={{
            padding: "8px 20px", borderRadius: 8,
            backgroundColor: ACCENT, color: "var(--re-surface-base)",
            border: "none", fontWeight: 600, fontSize: 13, cursor: "pointer",
          }}
        >
          Next: Account Setup →
        </button>
      </div>
    </div>
  );
}
