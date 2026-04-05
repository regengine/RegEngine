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
    { label: "Why RegEngine", href: "/why-regengine" },
    { label: "Retailer Readiness", href: "/retailer-readiness" },
    { label: "Pricing", href: "/pricing" },
    { label: "FSMA 204 Guide", href: "/fsma-204" },
];

export const MARKETING_FREE_TOOLS: MarketingToolLink[] = [
    { emoji: "🥬", label: "FTL Checker", desc: "Verify FDA Food Traceability List coverage", href: "/tools/ftl-checker" },
    { emoji: "🛡️", label: "Recall Readiness", desc: "Assess your recall response capability", href: "/tools/recall-readiness" },
    { emoji: "📊", label: "ROI Calculator", desc: "Calculate your compliance cost savings", href: "/tools/roi-calculator" },
    { emoji: "🔧", label: "All Free Tools", desc: "Browse the full compliance toolkit", href: "/tools" },
];

export const MARKETING_FOOTER_PRODUCT_LINKS: MarketingNavLink[] = [
    ...MARKETING_PRIMARY_NAV,
    { label: "Case Studies", href: "/case-studies" },
    { label: "Integrations", href: "/integrations" },
    { label: "Get Started", href: "/onboarding" },
];

export const MARKETING_FOOTER_DEVELOPER_LINKS: MarketingNavLink[] = [
    { label: "Developer Portal", href: "/developers" },
    { label: "API Docs", href: "/docs/api" },
    { label: "Quickstart", href: "/docs/quickstart" },
    { label: "SDKs", href: "/docs/sdks" },
    { label: "Changelog", href: "/docs/changelog" },
];

export const MARKETING_FOOTER_COMPANY_LINKS: MarketingNavLink[] = [
    { label: "About", href: "/about" },
    { label: "Blog", href: "/blog" },
    { label: "Contact", href: "/contact" },
    { label: "Security", href: "/security" },
    { label: "Trust Center", href: "/trust" },
    { label: "Privacy", href: "/privacy" },
    { label: "DPA", href: "/dpa" },
    { label: "Terms", href: "/terms" },
    { label: "Log In", href: "/login" },
    { label: "Sign Up", href: "/signup" },
];
