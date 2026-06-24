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
        features: ['Up to 500 CTEs/month', '1 facility', 'FSMA 204 traceability workspace', 'FDA-oriented sortable export'],
    },
    {
        revenue: '2–3 facilities',
        price: '$549',
        period: '/mo',
        note: 'Save ~15% vs monthly billing',
        features: ['No per-CTE caps (fair use)', '2–3 facilities', 'Everything in Base', 'Retailer-specific benchmarks', 'EPCIS 2.0 export'],
        highlighted: true,
    },
    {
        revenue: '4+ facilities',
        price: '$639',
        period: '/mo',
        note: 'Save ~15% vs monthly billing',
        features: ['No per-CTE caps (fair use)', '4+ facilities', 'Everything in Standard', 'Shared Slack channel (per agreement)', 'Quarterly compliance review (scheduled per agreement)'],
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
    { q: 'We already use spreadsheets — why switch?', a: 'A spreadsheet can support §1.1455\'s sortable electronic spreadsheet expectation on paper, but most teams discover during recall drills that maintaining hash-chained CTEs, lot-level KDEs, and consistent retailer-specific formats across many facilities and many seasons is operationally hard in a flat spreadsheet. RegEngine helps with the parts that get expensive at scale.' },
    { q: 'We\'re a small supplier — do we really need this?', a: 'If you sell food on any of the FDA Food Traceability List commodity groupings through major retailers, the rule may apply to you the same way it applies to large suppliers, subject to the §1.1305 exemptions. Size alone does not necessarily exempt you. RegEngine starts at $425/mo for Founding Design Partners and is built for single-facility suppliers working toward traceability readiness.' },
    { q: 'Can\'t we just wait for the FDA\'s July 2028 deadline?', a: 'Major retailers are already signaling traceability expectations to suppliers ahead of the federal enforcement date. Specific retailer requirements vary, change frequently, and should be confirmed directly with your buyer. RegEngine helps you build the underlying CTE/KDE record so you can respond to whichever format your retailer asks for.' },
    { q: 'How long does integration take?', a: 'Self-serve onboarding completes within days; complex ERP integrations are scoped separately. Data flows in via API, CSV/XLSX bulk upload, or SFTP import. If you have existing data in spreadsheets, we bulk-import and auto-clean it during onboarding. Retailer integrations are scoped per delivery mode — native API, webhook, CSV import, or custom mapping.' },
    { q: 'What if we don\'t sell FTL products?', a: 'Use our free FTL Checker tool to verify whether your products fall under the FDA Food Traceability List. Even if your primary products aren\'t on the list, many suppliers are surprised to find that secondary product lines (such as some fresh-cut produce or RTE deli salads) are covered.' },
];

/* ─────────────────────────────────────────────────────────────
   COMPETITOR DATA
   ───────────────────────────────────────────────────────────── */
export const COMPETITORS = [
    { feature: 'Starting price', regengine: '$425/mo (published)', foodlogiq: 'Contact sales', tracelink: 'Enterprise only' },
    { feature: 'Onboarding model', regengine: 'Self-serve', foodlogiq: 'Sales-led implementation', tracelink: 'Sales-led implementation' },
    { feature: 'API-first', regengine: '✓ Full REST API', foodlogiq: 'Verify with vendor', tracelink: 'Verify with vendor' },
    { feature: 'FDA-oriented export', regengine: '✓ Built-in', foodlogiq: 'Verify with vendor', tracelink: 'Verify with vendor' },
    { feature: 'Trace lookup', regengine: 'Indexed lookup', foodlogiq: 'Verify with vendor', tracelink: 'Verify with vendor' },
    { feature: 'Contract length', regengine: 'Month-to-month', foodlogiq: 'Verify with vendor', tracelink: 'Verify with vendor' },
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
            const safeData = data
                ? Object.fromEntries(
                    Object.entries(data).filter(([key]) => !/email|name|company|phone/i.test(key)),
                )
                : undefined;
            const events = JSON.parse(localStorage.getItem('retailer_analytics') || '[]');
            events.push({ event, data: safeData, ts: new Date().toISOString() });
            localStorage.setItem('retailer_analytics', JSON.stringify(events));
        }
    }, []);
}
