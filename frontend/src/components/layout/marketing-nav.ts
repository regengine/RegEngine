import { Calculator, LayoutGrid, Leaf, ShieldCheck } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type MarketingNavLink = {
    label: string;
    href: string;
};

export type MarketingToolLink = {
    icon: LucideIcon;
    label: string;
    desc: string;
    href: string;
};

export const MARKETING_PRIMARY_NAV: MarketingNavLink[] = [
    { label: "Product", href: "/product" },
    { label: "Integrations", href: "/integrations" },
    { label: "Readiness", href: "/retailer-readiness" },
    { label: "Pricing", href: "/pricing" },
    { label: "FSMA 204", href: "/fsma-204" },
];

export const MARKETING_FREE_TOOLS: MarketingToolLink[] = [
    { icon: Leaf, label: "FTL Checker", desc: "Verify FDA Food Traceability List coverage", href: "/tools/ftl-checker" },
    { icon: ShieldCheck, label: "Recall Readiness", desc: "Assess your recall response capability", href: "/tools/recall-readiness" },
    { icon: Calculator, label: "ROI Calculator", desc: "Calculate your compliance cost savings", href: "/tools/roi-calculator" },
];

export const MARKETING_ALL_TOOLS_LINK: MarketingToolLink = {
    icon: LayoutGrid,
    label: "View All Tools",
    desc: "Explore the compliance toolkit",
    href: "/tools",
};

export const MARKETING_FOOTER_PRODUCT_LINKS: MarketingNavLink[] = [
    { label: "Pricing", href: "/pricing" },
    { label: "Case Studies", href: "/case-studies" },
    { label: "Integrations", href: "/integrations" },
    { label: "Get Started", href: "/onboarding" },
];

export const MARKETING_FOOTER_DEVELOPER_LINKS: MarketingNavLink[] = [
    { label: "Developer Portal", href: "/developer/portal" },
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
