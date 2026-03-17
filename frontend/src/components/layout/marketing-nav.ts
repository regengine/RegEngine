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
    { label: "Retailer Readiness", href: "/retailer-readiness" },
    { label: "Pricing", href: "/pricing" },
    { label: "FSMA 204 Guide", href: "/fsma-204" },
];

export const MARKETING_FREE_TOOLS: MarketingToolLink[] = [
    { emoji: "🥬", label: "FTL Checker", desc: "Verify FDA Food Traceability List coverage", href: "/tools/ftl-checker" },
    { emoji: "🛡️", label: "Recall Readiness", desc: "Assess your recall response capability", href: "/tools/recall-readiness" },
    { emoji: "📊", label: "ROI Calculator", desc: "Calculate your compliance cost savings", href: "/tools/roi-calculator" },
    { emoji: "📥", label: "Bulk Upload Templates", desc: "Download CSV and XLSX onboarding templates", href: "/onboarding/bulk-upload" },
];

export const MARKETING_FOOTER_PRODUCT_LINKS: MarketingNavLink[] = [
    ...MARKETING_PRIMARY_NAV,
    { label: "Integrations", href: "/integrations" },
    { label: "Get Started", href: "/onboarding" },
];

export const MARKETING_FOOTER_COMPANY_LINKS: MarketingNavLink[] = [
    { label: "About", href: "/about" },
    { label: "Contact", href: "/contact" },
    { label: "Security", href: "/security" },
    { label: "Trust Center", href: "/trust" },
    { label: "Privacy", href: "/privacy" },
    { label: "Terms", href: "/terms" },
    { label: "Founding Design Partners", href: "/alpha" },
    { label: "Log In", href: "/login" },
    { label: "Sign Up", href: "/signup" },
];
