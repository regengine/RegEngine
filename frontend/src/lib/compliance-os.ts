export type ComplianceObjectState =
  | "invited"
  | "submitted"
  | "incomplete"
  | "needs-correction"
  | "ready"
  | "blocked"
  | "draft"
  | "validated"
  | "failed"
  | "corrected"
  | "committed"
  | "exported"
  | "not-eligible"
  | "building"
  | "signed"
  | "delivered"
  | "unscoped"
  | "ftl-scoped"
  | "event-mapped"
  | "kde-complete"
  | "recall-ready";

export type ComplianceTone = "control" | "traceability" | "readiness" | "trust" | "calm-urgency";

export type ComplianceStateStyle = {
  label: string;
  tone: ComplianceTone;
  colorVar: string;
  backgroundVar: string;
  borderVar: string;
};

export const complianceStateStyles: Record<ComplianceObjectState, ComplianceStateStyle> = {
  invited: {
    label: "Invited",
    tone: "traceability",
    colorVar: "var(--re-state-invited)",
    backgroundVar: "var(--re-state-invited-bg)",
    borderVar: "var(--re-state-invited-border)",
  },
  submitted: {
    label: "Submitted",
    tone: "readiness",
    colorVar: "var(--re-info)",
    backgroundVar: "var(--re-info-bg)",
    borderVar: "var(--re-info-border)",
  },
  incomplete: {
    label: "Incomplete",
    tone: "calm-urgency",
    colorVar: "var(--re-warning)",
    backgroundVar: "var(--re-warning-bg)",
    borderVar: "var(--re-warning-border)",
  },
  "needs-correction": {
    label: "Needs correction",
    tone: "calm-urgency",
    colorVar: "var(--re-warning)",
    backgroundVar: "var(--re-warning-bg)",
    borderVar: "var(--re-warning-border)",
  },
  ready: {
    label: "Ready",
    tone: "readiness",
    colorVar: "var(--re-success)",
    backgroundVar: "var(--re-success-bg)",
    borderVar: "var(--re-success-border)",
  },
  blocked: {
    label: "Blocked",
    tone: "calm-urgency",
    colorVar: "var(--re-danger)",
    backgroundVar: "var(--re-danger-bg)",
    borderVar: "var(--re-danger-border)",
  },
  draft: {
    label: "Draft",
    tone: "control",
    colorVar: "var(--re-text-muted)",
    backgroundVar: "var(--re-surface-card)",
    borderVar: "var(--re-surface-border)",
  },
  validated: {
    label: "Validated",
    tone: "readiness",
    colorVar: "var(--re-info)",
    backgroundVar: "var(--re-info-bg)",
    borderVar: "var(--re-info-border)",
  },
  failed: {
    label: "Failed",
    tone: "calm-urgency",
    colorVar: "var(--re-danger)",
    backgroundVar: "var(--re-danger-bg)",
    borderVar: "var(--re-danger-border)",
  },
  corrected: {
    label: "Corrected",
    tone: "traceability",
    colorVar: "var(--re-state-corrected)",
    backgroundVar: "var(--re-state-corrected-bg)",
    borderVar: "var(--re-state-corrected-border)",
  },
  committed: {
    label: "Committed",
    tone: "trust",
    colorVar: "var(--re-evidence)",
    backgroundVar: "var(--re-evidence-bg)",
    borderVar: "var(--re-evidence-border)",
  },
  exported: {
    label: "Exported",
    tone: "trust",
    colorVar: "var(--re-success)",
    backgroundVar: "var(--re-success-bg)",
    borderVar: "var(--re-success-border)",
  },
  "not-eligible": {
    label: "Not eligible",
    tone: "calm-urgency",
    colorVar: "var(--re-danger)",
    backgroundVar: "var(--re-danger-bg)",
    borderVar: "var(--re-danger-border)",
  },
  building: {
    label: "Building",
    tone: "control",
    colorVar: "var(--re-info)",
    backgroundVar: "var(--re-info-bg)",
    borderVar: "var(--re-info-border)",
  },
  signed: {
    label: "Signed",
    tone: "trust",
    colorVar: "var(--re-evidence)",
    backgroundVar: "var(--re-evidence-bg)",
    borderVar: "var(--re-evidence-border)",
  },
  delivered: {
    label: "Delivered",
    tone: "trust",
    colorVar: "var(--re-success)",
    backgroundVar: "var(--re-success-bg)",
    borderVar: "var(--re-success-border)",
  },
  unscoped: {
    label: "Unscoped",
    tone: "control",
    colorVar: "var(--re-text-muted)",
    backgroundVar: "var(--re-surface-card)",
    borderVar: "var(--re-surface-border)",
  },
  "ftl-scoped": {
    label: "FTL scoped",
    tone: "traceability",
    colorVar: "var(--re-info)",
    backgroundVar: "var(--re-info-bg)",
    borderVar: "var(--re-info-border)",
  },
  "event-mapped": {
    label: "Event mapped",
    tone: "traceability",
    colorVar: "var(--re-state-event)",
    backgroundVar: "var(--re-state-event-bg)",
    borderVar: "var(--re-state-event-border)",
  },
  "kde-complete": {
    label: "KDE complete",
    tone: "readiness",
    colorVar: "var(--re-success)",
    backgroundVar: "var(--re-success-bg)",
    borderVar: "var(--re-success-border)",
  },
  "recall-ready": {
    label: "Recall ready",
    tone: "readiness",
    colorVar: "var(--re-success)",
    backgroundVar: "var(--re-success-bg)",
    borderVar: "var(--re-success-border)",
  },
};

export function getComplianceStateStyle(state: ComplianceObjectState) {
  return complianceStateStyles[state];
}

export type RouteFamily =
  | "marketing"
  | "complianceEducation"
  | "tools"
  | "developerDocs"
  | "trustLegal"
  | "authOnboarding"
  | "appDashboard"
  | "admin";

export type RouteFamilyConfig = {
  label: string;
  routes: string[];
  density: "low" | "medium" | "medium-high" | "high" | "system";
  shell: string;
  rule: string;
};

export const complianceRouteFamilies: Record<RouteFamily, RouteFamilyConfig> = {
  marketing: {
    label: "Marketing",
    routes: ["/", "/product", "/pricing", "/why-regengine", "/about"],
    density: "medium",
    shell: "Command Center first viewport",
    rule: "Lead with proof, readiness, and defensible evidence rather than generic SaaS claims.",
  },
  complianceEducation: {
    label: "Compliance education",
    routes: ["/fsma-204", "/blog", "/case-studies"],
    density: "medium",
    shell: "Evidence Chain editorial",
    rule: "Use readable regulatory narratives, citations, and chain-of-custody visuals.",
  },
  tools: {
    label: "Tools",
    routes: ["/tools", "/tools/"],
    density: "medium-high",
    shell: "Food Operations Workbench",
    rule: "Keep tools action-first with Input to Validate to Artifact flow and next-best-action bars.",
  },
  developerDocs: {
    label: "Developer docs",
    routes: ["/docs", "/docs/", "/developers", "/developer/portal"],
    density: "high",
    shell: "Developer workbench",
    rule: "Use persistent navigation, code/reference splits, and endpoint evidence-state annotations.",
  },
  trustLegal: {
    label: "Trust and legal",
    routes: ["/security", "/trust", "/privacy", "/dpa", "/terms"],
    density: "medium-high",
    shell: "Evidence Ledger",
    rule: "Make controls, packets, verification, and chain-of-custody artifacts concrete.",
  },
  authOnboarding: {
    label: "Auth and onboarding",
    routes: ["/login", "/signup", "/onboarding", "/forgot-password", "/reset-password"],
    density: "low",
    shell: "Trust-first setup",
    rule: "Use low-density confidence cues, progress rails, and infrastructure setup language.",
  },
  appDashboard: {
    label: "App and dashboard",
    routes: ["/dashboard", "/compliance", "/records", "/requests", "/settings", "/exceptions", "/identity", "/rules"],
    density: "high",
    shell: "Readiness Flight Deck",
    rule: "Prioritize what needs attention, exception queues, supplier gaps, and export blockers.",
  },
  admin: {
    label: "Admin",
    routes: ["/admin", "/sysadmin"],
    density: "system",
    shell: "System console",
    rule: "Use audit logs, tenant scopes, mode badges, and constrained administrative density.",
  },
};

export function getRouteFamilyForPath(pathname: string): RouteFamilyConfig {
  const normalized = pathname === "" ? "/" : pathname;
  const exactMatch = Object.values(complianceRouteFamilies).find((family) =>
    family.routes.includes(normalized),
  );

  if (exactMatch) {
    return exactMatch;
  }

  const prefixMatch = Object.values(complianceRouteFamilies)
    .flatMap((family) => family.routes.map((route) => ({ family, route })))
    .filter(({ route }) => route !== "/" && normalized.startsWith(route.endsWith("/") ? route : `${route}/`))
    .sort((a, b) => b.route.length - a.route.length)[0];

  return prefixMatch?.family ?? complianceRouteFamilies.marketing;
}
