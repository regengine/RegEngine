import { ACCENT, ACCENT_LIGHT, GRAY, GRAY_LIGHT, BORDER, BLUE, BLUE_LIGHT } from "./styles";

/* ── Card ────────────────────────────────────────────────────────── */
export function Card({ children, style }) {
  return (
    <div style={{
      border: `1px solid ${BORDER}`,
      borderRadius: 10,
      padding: 20,
      backgroundColor: GRAY_LIGHT,
      ...style,
    }}>
      {children}
    </div>
  );
}

/* ── Section title + subtitle ────────────────────────────────────── */
export function SectionTitle({ children, sub }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <h2 style={{ fontSize: 20, fontWeight: 700, color: "var(--re-text-primary)", margin: 0 }}>{children}</h2>
      {sub && <p style={{ fontSize: 13, color: GRAY, margin: "4px 0 0" }}>{sub}</p>}
    </div>
  );
}

/* ── Overview step card ──────────────────────────────────────────── */
export function FlowStep({ number, title, description, status, onClick, isDemo }) {
  const borderColor = status === "complete" ? ACCENT : status === "active" ? BLUE : BORDER;
  return (
    <div
      onClick={onClick}
      style={{
        border: `1px solid ${borderColor}`,
        borderRadius: 10,
        padding: "14px 18px",
        cursor: "pointer",
        backgroundColor: GRAY_LIGHT,
        display: "flex",
        alignItems: "center",
        gap: 14,
        transition: "border-color 0.15s",
      }}
    >
      <div style={{
        width: 32, height: 32, borderRadius: "50%",
        backgroundColor: status === "complete" ? ACCENT : BLUE,
        color: "var(--re-surface-base)",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 14, fontWeight: 700, flexShrink: 0,
      }}>
        {number}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--re-text-primary)" }}>
          {title}
          {isDemo && (
            <span style={{
              fontSize: 10, fontWeight: 500, color: GRAY,
              marginLeft: 8, padding: "2px 6px",
              border: `1px solid ${BORDER}`, borderRadius: 4,
            }}>
              How it works
            </span>
          )}
        </div>
        <div style={{ fontSize: 12, color: GRAY }}>{description}</div>
      </div>
    </div>
  );
}

/* ── Colored badge ───────────────────────────────────────────────── */
export function Badge({ children, color = ACCENT }) {
  const bgMap = {
    [ACCENT]: ACCENT_LIGHT,
  };
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 8px",
      borderRadius: 9999,
      fontSize: 11,
      fontWeight: 600,
      backgroundColor: bgMap[color] || `${color}22`,
      color,
      marginLeft: 6,
    }}>
      {children}
    </span>
  );
}

/* ── Demo mode banner ────────────────────────────────────────────── */
export function DemoBanner({ isLoggedIn }) {
  if (isLoggedIn) return null;
  return (
    <div style={{
      backgroundColor: BLUE_LIGHT,
      border: `1px solid ${BLUE}`,
      borderRadius: 8,
      padding: "10px 16px",
      marginBottom: 16,
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: 12,
    }}>
      <div style={{ fontSize: 13, color: BLUE }}>
        <strong>Interactive walkthrough</strong> — Steps 1-2 show how the invite flow works. Steps 3-8 are live when you log in.
      </div>
      <a
        href="/login?redirect=/onboarding/supplier-flow"
        style={{
          padding: "6px 16px",
          borderRadius: 6,
          backgroundColor: ACCENT,
          color: "var(--re-surface-base)",
          fontSize: 12,
          fontWeight: 600,
          textDecoration: "none",
          whiteSpace: "nowrap",
          flexShrink: 0,
        }}
      >
        Log in to start
      </a>
    </div>
  );
}

/* ── Inline info callout (replaces the old "Graph effect" boxes) ── */
export function InfoCallout({ children }) {
  return (
    <div style={{
      marginTop: 12,
      padding: "10px 14px",
      borderRadius: 6,
      backgroundColor: BLUE_LIGHT,
      fontSize: 12,
      color: BLUE,
    }}>
      {children}
    </div>
  );
}

/* ── Form field (real input, not a styled div) ───────────────────── */
export function FormField({ label, type = "text", required, placeholder, value, onChange, disabled, options }) {
  const baseStyle = {
    width: "100%",
    border: `1px solid ${BORDER}`,
    borderRadius: 8,
    padding: "10px 14px",
    fontSize: 13,
    color: disabled ? "var(--re-text-disabled)" : "var(--re-text-secondary)",
    backgroundColor: disabled ? "var(--re-surface-card)" : "var(--re-surface-elevated)",
    boxSizing: "border-box",
  };

  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--re-text-secondary)", marginBottom: 3 }}>
        {label}{required && <span style={{ color: "var(--re-danger)", marginLeft: 2 }}>*</span>}
      </div>
      {type === "select" ? (
        <select style={baseStyle} value={value || ""} onChange={onChange} disabled={disabled}>
          <option value="">Select...</option>
          {(options || []).map((o) => (
            <option key={o} value={o}>{o}</option>
          ))}
        </select>
      ) : (
        <input
          type={type}
          style={baseStyle}
          placeholder={placeholder}
          value={value || ""}
          onChange={onChange}
          disabled={disabled}
        />
      )}
    </div>
  );
}
