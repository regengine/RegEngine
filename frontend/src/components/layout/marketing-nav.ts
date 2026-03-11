export type MarketingNavLink = {
    label: string;
    href: string;
};

export type MarketingToolLink = {
    emoji: string;
    label: string;
    desc: string;
    href: string;
};

export const MARKETING_PRIMARY_NAV: MarketingNavLink[] = [
    { label: "Product", href: "/product" },
    { label: "FSMA 204 Guide", href: "/docs/fsma-204" },
    { label: "Developers", href: "/developers" },
    { label: "Pricing", href: "/pricing" },
];

export const MARKETING_FREE_TOOLS: MarketingToolLink[] = [
    { emoji: "🥬", label: "FTL Checker", desc: "Verify FDA Food Traceability List coverage", href: "/tools/ftl-checker" },
    { emoji: "📥", label: "Bulk Upload Templates", desc: "Download CSV and XLSX onboarding templates", href: "/onboarding/bulk-upload" },
    { emoji: "📊", label: "Cold Chain Monitor", desc: "Cold-chain anomaly detection sandbox", href: "/tools/fsma-unified" },
    { emoji: "🧠", label: "Knowledge Graph", desc: "Interactive traceability graph builder", href: "/tools/knowledge-graph" },
];

export const MARKETING_FOOTER_PRODUCT_LINKS: MarketingNavLink[] = [
    ...MARKETING_PRIMARY_NAV,
    { label: "Integrations", href: "/integrations" },
    { label: "Get Started", href: "/get-started" },
];

export const MARKETING_FOOTER_COMPANY_LINKS: MarketingNavLink[] = [
    { label: "About", href: "/about" },
    { label: "Contact", href: "/contact" },
    { label: "Security", href: "/security" },
    { label: "Privacy", href: "/privacy" },
    { label: "Terms", href: "/terms" },
    { label: "Design Partner Program", href: "/design-partner" },
];
