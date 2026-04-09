'use client';

import { useState, useEffect, useRef, useCallback } from 'react';

/* ─────────────────────────────────────────────────────────────
   DESIGN TOKENS
   ───────────────────────────────────────────────────────────── */
export const T = {
    bg: 'var(--re-surface-base)',
    surface: 'var(--re-surface-card)',
    surfaceHover: 'var(--re-surface-elevated)',
    border: 'var(--re-surface-border)',
    borderHover: 'var(--re-border-default)',
    text: 'var(--re-text-secondary)',
    textMuted: 'var(--re-text-muted)',
    textDim: 'var(--re-text-disabled)',
    heading: 'var(--re-text-primary)',
    accent: 'var(--re-brand)',
    accentHover: 'var(--re-brand-dark)',
    accentGlow: 'var(--re-brand-muted)',
    warning: 'var(--re-warning)',
    warningBg: 'var(--re-warning-bg, rgba(245,158,11,0.08))',
    warningBorder: 'var(--re-warning-border, rgba(245,158,11,0.15))',
    danger: 'var(--re-danger)',
    dangerBg: 'var(--re-danger-bg, rgba(239,68,68,0.08))',
    blue: 'var(--re-accent-blue)',
    blueBg: 'var(--re-info-bg, rgba(59,130,246,0.08))',
};

/* ─────────────────────────────────────────────────────────────
   SCROLL REVEAL HOOK
   ───────────────────────────────────────────────────────────── */
export function useScrollReveal(threshold = 0.15) {
    const ref = useRef<HTMLDivElement>(null);
    const [visible, setVisible] = useState(false);

    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        const obs = new IntersectionObserver(
            ([entry]) => { if (entry.isIntersecting) { setVisible(true); obs.disconnect(); } },
            { threshold }
        );
        obs.observe(el);
        return () => obs.disconnect();
    }, [threshold]);

    return { ref, visible };
}

/* ─────────────────────────────────────────────────────────────
   PRICING DATA
   ───────────────────────────────────────────────────────────── */
export const PRICING_TIERS = [
    {
        revenue: '1 facility',
        price: '$425',
        period: '/mo',
        note: 'Save ~15% vs monthly billing',
        features: ['Up to 500 CTEs/month', '1 facility', 'FSMA 204 traceability workspace', 'FDA-ready export'],
    },
    {
        revenue: '2–3 facilities',
        price: '$549',
        period: '/mo',
        note: 'Save ~15% vs monthly billing',
        features: ['Unlimited CTEs', '2–3 facilities', 'Everything in Base', 'Retailer-specific benchmarks', 'EPCIS 2.0 export'],
        highlighted: true,
    },
    {
        revenue: '4+ facilities',
        price: '$639',
        period: '/mo',
        note: 'Save ~15% vs monthly billing',
        features: ['Unlimited CTEs', '4+ facilities', 'Everything in Standard', 'Dedicated Slack channel', 'Quarterly compliance reviews'],
    },
];

/* ─────────────────────────────────────────────────────────────
   TRACE ANIMATION NODES
   ───────────────────────────────────────────────────────────── */
export const TRACE_NODES_FORWARD = [
    { label: 'Harvest', sublabel: 'Farm • Salinas, CA', icon: '🌱', kde: 'TLC-2026-0412' },
    { label: 'Cool & Pack', sublabel: 'Cooler • Salinas, CA', icon: '❄️', kde: 'TLC-2026-0412-P' },
    { label: 'Ship', sublabel: 'Truck → DC', icon: '🚛', kde: 'BOL-88421' },
    { label: 'Receive', sublabel: 'Retailer DC #7218', icon: '📦', kde: 'RCV-7218-0412' },
    { label: 'Store', sublabel: 'Retail Store #4521', icon: '🏪', kde: 'STR-4521-0412' },
];

export const TRACE_NODES_BACKWARD = [
    { label: 'Recall Alert', sublabel: 'Store #4521 • Shelf Pull', icon: '🚨', kde: 'RCL-4521-0412' },
    { label: 'Receiving Log', sublabel: 'Retailer DC #7218', icon: '📦', kde: 'RCV-7218-0412' },
    { label: 'Shipment', sublabel: 'BOL Lookup → Carrier', icon: '🚛', kde: 'BOL-88421-REV' },
    { label: 'Packing Record', sublabel: 'Cooler • Salinas, CA', icon: '❄️', kde: 'PKG-2026-0412' },
    { label: 'Source Identified', sublabel: 'Farm • Salinas, CA • Lot #0412', icon: '🎯', kde: 'SRC-FARM-0412' },
];

/* ─────────────────────────────────────────────────────────────
   FAQ DATA
   ───────────────────────────────────────────────────────────── */
export const FAQ_ITEMS = [
    { q: 'We already use spreadsheets — why switch?', a: 'Spreadsheets can\'t generate the FDA-sortable export format required by FSMA 204. When a major retailer or the FDA requests a trace, you need results in seconds, not days. RegEngine automates what spreadsheets can\'t: hash-chained CTEs, lot-level KDEs, and one-click FDA exports.' },
    { q: 'We\'re a small supplier — do we really need this?', a: 'If you sell any FDA Food Traceability List (FTL) categories through major retailers, you\'re subject to the same requirements as large suppliers. Size doesn\'t exempt you from compliance — but RegEngine starts at $425/mo for Founding Design Partners — built specifically for single-facility suppliers getting compliant.' },
    { q: 'Can\'t we just wait for the FDA\'s July 2028 deadline?', a: 'Retailers are already enforcing. Walmart required food and beverage suppliers to meet ASN and packaging requirements by August 1, 2025. Kroger required EDI 856 compliance by June 30, 2025. Suppliers who can\'t demonstrate traceability readiness risk losing shelf placement during the next category review. By the time the FDA deadline hits, it\'s already too late.' },
    { q: 'How long does integration take?', a: 'Most suppliers are operational within 2–4 weeks. Data flows in via API, CSV/XLSX bulk upload, or SFTP import. If you have existing data in spreadsheets, we bulk-import and auto-clean it during onboarding. ERP and retailer integrations are scoped per delivery mode — native API, webhook, CSV import, or custom mapping.' },
    { q: 'What if we don\'t sell FTL products?', a: 'Use our free FTL Checker tool to verify whether your products fall under the FDA Food Traceability List categories (see 21 CFR 1.1300). Even if your primary products aren\'t on the list, many suppliers are surprised to find that secondary product lines (like pre-cut salads or certain cheeses) are covered.' },
];

/* ─────────────────────────────────────────────────────────────
   COMPETITOR DATA
   ───────────────────────────────────────────────────────────── */
export const COMPETITORS = [
    { feature: 'Starting price', regengine: '$425/mo', foodlogiq: '$2,500+/mo', tracelink: 'Enterprise only' },
    { feature: 'Setup time', regengine: '2–4 weeks', foodlogiq: '3–6 months', tracelink: '6–12 months' },
    { feature: 'API-first', regengine: '✓ Full REST API', foodlogiq: 'Limited', tracelink: 'Portal-based' },
    { feature: 'FDA export format', regengine: '✓ One-click', foodlogiq: 'Manual config', tracelink: 'Custom build' },
    { feature: 'Trace speed', regengine: '< 5 seconds', foodlogiq: 'Minutes', tracelink: 'Hours' },
    { feature: 'Contract length', regengine: 'Month-to-month', foodlogiq: 'Annual', tracelink: 'Multi-year' },
];

/* ─────────────────────────────────────────────────────────────
   INTEGRATION LOGOS
   ───────────────────────────────────────────────────────────── */
export const INTEGRATIONS = [
    { name: 'SAP', icon: '🔷' },
    { name: 'Oracle NetSuite', icon: '🔶' },
    { name: 'QuickBooks', icon: '📗' },
    { name: 'Shopify', icon: '🛒' },
    { name: 'WMS Systems', icon: '📦' },
    { name: 'REST API', icon: '⚡' },
    { name: 'CSV Import', icon: '📄' },
    { name: 'Webhook', icon: '🔔' },
];

/* ─────────────────────────────────────────────────────────────
   ANALYTICS TRACKING HELPER HOOK
   ───────────────────────────────────────────────────────────── */
export function useTrackEvent() {
    return useCallback((event: string, data?: Record<string, unknown>) => {
        if (typeof window !== 'undefined') {
            const events = JSON.parse(localStorage.getItem('retailer_analytics') || '[]');
            events.push({ event, data, ts: new Date().toISOString() });
            localStorage.setItem('retailer_analytics', JSON.stringify(events));
        }
    }, []);
}
