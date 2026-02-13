'use client';

import { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Link from 'next/link';

/* ───────────────────────── CONSTANTS ───────────────────────── */

/*
 * All data below is sourced directly from scripts/demo/seed_fsma_data.py (v3).
 * Each chain mirrors a real FDA recall, seeded as 430 CTE records.
 */

interface Facility {
    name: string;
    gln: string;
    type: string;
    address?: string;
    extra?: Record<string, string>;
}

interface Product {
    name: string;
    gtin: string;
    category: string;
    onFtl?: boolean;
}

interface CTEStep {
    cte: string;
    cfr: string;
    facility: string;
    description: string;
}

interface RecallChain {
    id: string;
    title: string;
    subtitle: string;
    recallBasis: string;
    demoStory: string;
    gradient: string;
    accentColor: string;
    badgeColor: string;
    icon: string;
    eventCount: number;
    batchCount: number;
    facilities: Facility[];
    products: Product[];
    cteFlow: CTEStep[];
    keyKDEs: string[];
}

const CHAINS: RecallChain[] = [
    {
        id: 'rizo-dairy',
        title: 'Valle Fresco Dairy Chain',
        subtitle: 'The "Mixed Coverage" Story',
        recallBasis: 'Rizo Lopez Foods (2024) — Listeria monocytogenes',
        demoStory: 'A single creamery makes 8 cheese products — 5 are ON the FDA Food Traceability List, 3 are OFF. The FTL Checker reveals which products carry FSMA 204 obligations and which don\'t.',
        gradient: 'from-amber-500/20 via-orange-500/10 to-yellow-500/5',
        accentColor: 'var(--re-warning)',
        badgeColor: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
        icon: '🧀',
        eventCount: 90,
        batchCount: 15,
        facilities: [
            { name: 'Valle Fresco Creamery', gln: '0860000100001', type: 'MANUFACTURER', address: '1200 Dairy Lane, Modesto, CA 95351' },
            { name: 'Central Valley Foods Distribution', gln: '0860000100002', type: 'DISTRIBUTOR', address: '800 Commerce Way, Stockton, CA 95206' },
            { name: 'Mercado Fresco #12', gln: '0860000100010', type: 'RETAILER', address: '245 Mission St, San Jose, CA' },
            { name: 'La Tienda Market', gln: '0860000100011', type: 'RETAILER', address: '3100 E 14th St, Oakland, CA' },
            { name: 'FreshMart Grocery', gln: '0860000100012', type: 'RETAILER', address: '900 S Broadway, Los Angeles, CA' },
        ],
        products: [
            { name: 'Queso Fresco 12oz', gtin: '00860001000012', category: 'Fresh Soft Cheese', onFtl: true },
            { name: 'Ricotta Fresca 16oz', gtin: '00860001000029', category: 'Fresh Soft Cheese', onFtl: true },
            { name: 'Oaxaca String Cheese 1lb', gtin: '00860001000036', category: 'Soft Ripened & Semi-Soft', onFtl: true },
            { name: 'Panela Cheese 10oz', gtin: '00860001000043', category: 'Fresh Soft Cheese', onFtl: true },
            { name: 'Monterey Jack Block 8oz', gtin: '00860001000050', category: 'Soft Ripened & Semi-Soft', onFtl: true },
            { name: 'Aged Cotija 8oz', gtin: '00860001000067', category: 'Hard Cheese (NOT on FTL)', onFtl: false },
            { name: 'Sharp Cheddar Block 8oz', gtin: '00860001000074', category: 'Hard Cheese (NOT on FTL)', onFtl: false },
            { name: 'Crema Mexicana 15oz', gtin: '00860001000081', category: 'Sour Cream (NOT on FTL)', onFtl: false },
        ],
        cteFlow: [
            { cte: 'RECEIVING', cfr: '§1.1345', facility: 'Valle Fresco Creamery', description: 'Raw milk received at creamery' },
            { cte: 'TRANSFORMATION', cfr: '§1.1350', facility: 'Valle Fresco Creamery', description: 'Cheese making — raw milk → finished product' },
            { cte: 'SHIPPING', cfr: '§1.1340', facility: 'Valle Fresco Creamery', description: 'Ship finished cheese to distributor' },
            { cte: 'RECEIVING', cfr: '§1.1345', facility: 'Central Valley Foods Distribution', description: 'Distributor receives cheese products' },
            { cte: 'SHIPPING', cfr: '§1.1340', facility: 'Central Valley Foods Distribution', description: 'Ship to retail locations' },
            { cte: 'RECEIVING', cfr: '§1.1345', facility: 'Retail Store', description: 'Retail store receives products for sale' },
        ],
        keyKDEs: ['TLC (GTIN-DATE-SEQ)', 'Product Description', 'Quantity & UoM', 'Reference Document (BOL/PO)', 'FTL Coverage Status'],
    },
    {
        id: 'cs137-shrimp',
        title: 'Pacific Rim Seafood Chain',
        subtitle: 'The "Import Visibility" Story',
        recallBasis: 'Cesium-137 frozen shrimp recall (2025)',
        demoStory: 'Indonesian trawler catches shrimp → processed in Makassar → shipped via ocean freight to Port of Long Beach → Southwind Foods → retail. The First Land-Based Receiving CTE (§1.1335) is the key regulatory event that catches imported seafood failures.',
        gradient: 'from-cyan-500/20 via-blue-500/10 to-indigo-500/5',
        accentColor: 'var(--re-accent-cyan)',
        badgeColor: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30',
        icon: '🦐',
        eventCount: 200,
        batchCount: 20,
        facilities: [
            { name: 'KM Sinar Laut (Indonesian Trawler)', gln: '8991234560001', type: 'VESSEL', extra: { 'Harvest Area': 'FAO Area 71 — Western Central Pacific' } },
            { name: 'PT Makassar Seafood Processing', gln: '8991234560002', type: 'FOREIGN PROCESSOR', address: 'Jl. Pelabuhan No. 15, Makassar, South Sulawesi, Indonesia' },
            { name: 'Port of Long Beach — Cold Storage Terminal', gln: '0078742000010', type: 'FIRST RECEIVER', address: 'Pier J, Long Beach, CA 90802' },
            { name: 'Southwind Foods LLC', gln: '0078742000020', type: 'IMPORTER', address: '2100 Carson St, Carson, CA 90745' },
            { name: 'Pacific Rim Seafood Distribution', gln: '0078742000030', type: 'DISTRIBUTOR', address: '1500 Harbor Blvd, Long Beach, CA 90802' },
            { name: '99 Ranch Market — Rowland Heights', gln: '0078742000040', type: 'RETAILER' },
            { name: 'H Mart — Koreatown', gln: '0078742000041', type: 'RETAILER' },
            { name: 'Wholesale Club #681', gln: '0078742000042', type: 'RETAILER' },
        ],
        products: [
            { name: 'Frozen White Shrimp 16/20ct 2lb Bag', gtin: '00787420000012', category: 'Crustaceans' },
            { name: 'Frozen Tiger Shrimp 21/25ct 1lb Bag', gtin: '00787420000029', category: 'Crustaceans' },
            { name: 'Frozen Peeled Shrimp 26/30ct 2lb Bag', gtin: '00787420000036', category: 'Crustaceans' },
        ],
        cteFlow: [
            { cte: 'HARVESTING', cfr: '§1.1325(a)', facility: 'KM Sinar Laut', description: 'Wild catch at sea — FAO Area 71' },
            { cte: 'TRANSFORMATION', cfr: '§1.1350', facility: 'PT Makassar Seafood', description: 'Processing & IQF freezing in Indonesia' },
            { cte: 'SHIPPING', cfr: '§1.1340', facility: 'PT Makassar Seafood', description: '~2 weeks ocean freight to U.S.' },
            { cte: 'FIRST LAND-BASED RECEIVING', cfr: '§1.1335', facility: 'Port of Long Beach', description: 'Key CTE for imported seafood compliance' },
            { cte: 'SHIPPING', cfr: '§1.1340', facility: 'Port of Long Beach', description: 'Transfer to importer' },
            { cte: 'RECEIVING', cfr: '§1.1345', facility: 'Southwind Foods LLC', description: 'Importer receives & inspects' },
            { cte: 'SHIPPING', cfr: '§1.1340', facility: 'Southwind Foods LLC', description: 'Ship to distributor' },
            { cte: 'RECEIVING', cfr: '§1.1345', facility: 'Pacific Rim Seafood Dist.', description: 'Distributor receives inventory' },
            { cte: 'SHIPPING', cfr: '§1.1340', facility: 'Pacific Rim Seafood Dist.', description: 'Ship to retail stores' },
            { cte: 'RECEIVING', cfr: '§1.1345', facility: 'Retail Store', description: 'Final retail receiving' },
        ],
        keyKDEs: ['Vessel Name', 'FAO Harvest Area', 'Landing Port', 'Container ID', 'Import Entry Number', 'TLC (GTIN-DATE-SEQ)'],
    },
    {
        id: 'cucumber-produce',
        title: 'Suncoast Produce Chain',
        subtitle: 'The "Farm-to-Fork" Story',
        recallBasis: '2024 cucumber Salmonella recall',
        demoStory: 'Florida farm harvests cucumbers → field cooling → packed at packing house → shipped to distributor in Atlanta → retail across the Southeast. The Field ID traces back to the exact harvest location — critical for outbreak investigation.',
        gradient: 'from-emerald-500/20 via-green-500/10 to-lime-500/5',
        accentColor: 'var(--re-brand)',
        badgeColor: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
        icon: '🥒',
        eventCount: 140,
        batchCount: 20,
        facilities: [
            { name: 'Suncoast Farms', gln: '0071430000001', type: 'FARM', address: '4500 Agricultural Rd, Immokalee, FL 34142', extra: { 'Fields': 'SC-North-A, SC-North-B, SC-South-1, SC-Organic' } },
            { name: 'Suncoast Cold Storage', gln: '0071430000002', type: 'COOLER', address: '4520 Agricultural Rd, Immokalee, FL 34142' },
            { name: 'Fresh Fields Packing Co', gln: '0071430000003', type: 'PACKER', address: '200 Packing House Blvd, Plant City, FL 33563' },
            { name: 'Southeast Fresh Distribution', gln: '0071430000004', type: 'DISTRIBUTOR', address: '1000 Distribution Center Dr, Atlanta, GA 30318' },
            { name: 'Southeast Grocery #1247', gln: '0071430000010', type: 'RETAILER' },
            { name: 'National Grocer DC #432', gln: '0071430000011', type: 'RETAILER' },
            { name: 'Regional Supercenter #2891', gln: '0071430000012', type: 'RETAILER' },
            { name: 'Organic Market — Buckhead', gln: '0071430000013', type: 'RETAILER' },
        ],
        products: [
            { name: 'Fresh Cucumbers (bulk)', gtin: '00714300000012', category: 'Cucumbers' },
            { name: 'English Cucumbers 2ct Sleeve', gtin: '00714300000029', category: 'Cucumbers' },
            { name: 'Mini Cucumbers 1lb Bag', gtin: '00714300000036', category: 'Cucumbers' },
            { name: 'Organic Cucumbers (bulk)', gtin: '00714300000043', category: 'Cucumbers' },
        ],
        cteFlow: [
            { cte: 'HARVESTING', cfr: '§1.1325(a)', facility: 'Suncoast Farms', description: 'Field harvest with field ID tracking' },
            { cte: 'COOLING', cfr: '§1.1325(b)', facility: 'Suncoast Cold Storage', description: 'Pre-cooling immediately after harvest' },
            { cte: 'INITIAL PACKING', cfr: '§1.1330', facility: 'Fresh Fields Packing Co', description: 'Packed into retail-ready containers' },
            { cte: 'SHIPPING', cfr: '§1.1340', facility: 'Fresh Fields Packing Co', description: 'Ship to regional distributor' },
            { cte: 'RECEIVING', cfr: '§1.1345', facility: 'Southeast Fresh Distribution', description: 'Distributor DC in Atlanta' },
            { cte: 'SHIPPING', cfr: '§1.1340', facility: 'Southeast Fresh Distribution', description: 'Ship to retail outlets' },
            { cte: 'RECEIVING', cfr: '§1.1345', facility: 'Retail Store', description: 'Final retail receiving' },
        ],
        keyKDEs: ['Field Identifier', 'Cooling Facility', 'TLC (GTIN-DATE-SEQ)', 'Harvest Date & Time', 'Product Description', 'Quantity & UoM'],
    },
];

/* ───────────────────────── ICON COMPONENTS ───────────────────────── */

function FactoryIcon({ size = 18 }: { size?: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 20V8L7 4V8L12 4V8L17 4V20H2Z" />
            <path d="M17 20V4H22V20" />
            <path d="M6 12H8M6 16H8M12 12H14M12 16H14" />
        </svg>
    );
}

function ShipIcon({ size = 18 }: { size?: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 20L4.5 16H19.5L22 20" />
            <path d="M6.5 16V10H17.5V16" />
            <path d="M12 10V6" />
            <path d="M9 6H15" />
        </svg>
    );
}

function ArrowRight({ size = 16 }: { size?: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12H19M12 5L19 12L12 19" />
        </svg>
    );
}

function HashIcon({ size = 16 }: { size?: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 9H20M4 15H20M10 3L8 21M16 3L14 21" />
        </svg>
    );
}

function CheckIcon({ size = 14 }: { size?: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12L10 17L20 7" />
        </svg>
    );
}

function XIcon({ size = 14 }: { size?: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 6L6 18M6 6L18 18" />
        </svg>
    );
}

/* ───────────────────────── FACILITY TYPE → ICON MAPPING ───────────────────────── */

function getFacilityIcon(type: string) {
    switch (type) {
        case 'VESSEL': return '🚢';
        case 'FARM': return '🌾';
        case 'MANUFACTURER': return '🏭';
        case 'FOREIGN PROCESSOR': return '🏭';
        case 'FIRST RECEIVER': return '⚓';
        case 'COOLER': return '❄️';
        case 'PACKER': return '📦';
        case 'IMPORTER': return '🔄';
        case 'DISTRIBUTOR': return '🚛';
        case 'RETAILER': return '🏪';
        default: return '🏢';
    }
}

/* ───────────────────────── MAIN COMPONENT ───────────────────────── */

export default function SupplyChainExplorerPage() {
    const [selectedChain, setSelectedChain] = useState<string>(CHAINS[0].id);
    const [animateIn, setAnimateIn] = useState(false);
    const [expandedFacility, setExpandedFacility] = useState<string | null>(null);
    const [showCteTimeline, setShowCteTimeline] = useState(false);

    useEffect(() => setAnimateIn(true), []);

    const chain = useMemo(() => CHAINS.find(c => c.id === selectedChain)!, [selectedChain]);

    const handleChainSwitch = (id: string) => {
        setSelectedChain(id);
        setExpandedFacility(null);
        setShowCteTimeline(false);
    };

    return (
        <div
            className="min-h-screen bg-[var(--re-surface-base)] font-['Instrument_Sans',_-apple-system,_BlinkMacSystemFont,_sans-serif] text-[var(--re-text-secondary)] overflow-x-hidden"
        >
            <link
                href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
                rel="stylesheet"
            />

            {/* Noise texture */}
            <div
                className="fixed inset-0 opacity-[0.015] bg-[length:128px_128px] pointer-events-none z-[1]"
                style={{
                    backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
                }}
            />

            {/* ─── HERO HEADER ─── */}
            <section
                className="relative z-[2] max-w-[1120px] mx-auto px-6 pt-20 pb-10"
            >
                {/* Gradient glow */}
                <div
                    className="absolute -top-20 left-1/2 -translate-x-1/2 w-[700px] h-[400px] pointer-events-none transition-[background] duration-[600ms] ease-[ease]"
                    style={{
                        background: `radial-gradient(ellipse, ${chain.accentColor}0f 0%, transparent 70%)`,
                    }}
                />

                <div
                    className="transition-all duration-[800ms]"
                    style={{
                        opacity: animateIn ? 1 : 0,
                        transform: animateIn ? 'translateY(0)' : 'translateY(20px)',
                        transitionTimingFunction: 'cubic-bezier(0.16, 1, 0.3, 1)',
                    }}
                >
                    {/* Breadcrumb */}
                    <div className="flex items-center gap-2 mb-6 text-[13px]">
                        <Link href="/" className="text-[var(--re-text-disabled)] no-underline transition-colors duration-200">Home</Link>
                        <span className="text-[var(--re-text-disabled)]">/</span>
                        <Link href="/demo/mock-recall" className="text-[var(--re-text-disabled)] no-underline transition-colors duration-200">Demo</Link>
                        <span className="text-[var(--re-text-disabled)]">/</span>
                        <span className="text-[var(--re-text-tertiary)]">Supply Chain Explorer</span>
                    </div>

                    <div className="flex items-center gap-3 mb-3">
                        <span
                            className="px-3 py-1 bg-[rgba(16,185,129,0.08)] border border-[rgba(16,185,129,0.15)] rounded-[20px] text-[11px] font-['JetBrains_Mono',_monospace] font-medium text-[var(--re-brand)]"
                        >
                            430 LIVE RECORDS
                        </span>
                        <span
                            className="px-3 py-1 bg-[rgba(99,102,241,0.08)] border border-[rgba(99,102,241,0.15)] rounded-[20px] text-[11px] font-['JetBrains_Mono',_monospace] font-medium text-[var(--re-accent-purple)]"
                        >
                            SHA-256 VERIFIED
                        </span>
                    </div>

                    <h1
                        className="text-[clamp(32px,4.5vw,48px)] font-bold text-[var(--re-text-primary)] leading-[1.1] m-0 mb-4 tracking-[-0.02em]"
                    >
                        Supply Chain Explorer
                    </h1>
                    <p className="text-[17px] text-[var(--re-text-muted)] leading-[1.6] max-w-[640px] m-0">
                        Explore 3 real-world recall scenarios modeled on FDA enforcement actions. Every record is
                        cryptographically hashed and independently verifiable — this is what FSMA 204 compliance looks like in practice.
                    </p>
                </div>
            </section>

            {/* ─── CHAIN SELECTOR TABS ─── */}
            <section className="relative z-[2] max-w-[1120px] mx-auto px-6 pb-10">
                <div
                    className="grid grid-cols-3 gap-3"
                >
                    {CHAINS.map((c) => {
                        const isActive = selectedChain === c.id;
                        return (
                            <button
                                key={c.id}
                                onClick={() => handleChainSwitch(c.id)}
                                className="p-5 rounded-xl cursor-pointer text-left text-inherit font-inherit transition-all duration-300 ease-[ease] relative overflow-hidden"
                                style={{
                                    background: isActive
                                        ? `linear-gradient(135deg, ${c.accentColor}12, ${c.accentColor}06)`
                                        : 'rgba(255,255,255,0.02)',
                                    border: `1px solid ${isActive ? c.accentColor + '40' : 'rgba(255,255,255,0.06)'}`,
                                }}
                            >
                                {isActive && (
                                    <div
                                        className="absolute top-0 left-0 right-0 h-[2px]"
                                        style={{
                                            background: c.accentColor,
                                        }}
                                    />
                                )}
                                <div className="flex items-center gap-[10px] mb-2">
                                    <span className="text-2xl">{c.icon}</span>
                                    <div className="flex-1">
                                        <div className="text-sm font-semibold" style={{ color: isActive ? 'var(--re-text-primary)' : 'var(--re-text-tertiary)' }}>
                                            {c.title}
                                        </div>
                                        <div className="text-[11px] text-[var(--re-text-disabled)] font-['JetBrains_Mono',_monospace]">
                                            {c.eventCount} events • {c.batchCount} batches
                                        </div>
                                    </div>
                                </div>
                                <div className="text-xs text-[var(--re-text-muted)] leading-[1.4]">{c.subtitle}</div>
                            </button>
                        );
                    })}
                </div>
            </section>

            {/* ─── CHAIN DETAIL ─── */}
            <section
                key={chain.id}
                className="relative z-[2] max-w-[1120px] mx-auto px-6 pb-20"
            >
                {/* Recall Basis Banner */}
                <div
                    className="py-4 px-5 rounded-r-lg mb-8"
                    style={{
                        background: `linear-gradient(90deg, ${chain.accentColor}08, transparent)`,
                        borderLeft: `3px solid ${chain.accentColor}`,
                    }}
                >
                    <div className="text-[11px] font-['JetBrains_Mono',_monospace] text-[var(--re-text-disabled)] mb-1 uppercase tracking-[0.08em]">
                        Based on real FDA recall
                    </div>
                    <div className="text-sm font-semibold text-[var(--re-text-primary)]">{chain.recallBasis}</div>
                    <div className="text-[13px] text-[var(--re-text-tertiary)] mt-1.5 leading-[1.5]">{chain.demoStory}</div>
                </div>

                {/* Stats Row */}
                <div
                    className="grid grid-cols-4 gap-3 mb-8"
                >
                    {[
                        { value: String(chain.eventCount), label: 'CTE Records', sub: 'SHA-256 hashed' },
                        { value: String(chain.facilities.length), label: 'Facilities', sub: 'GLN-identified' },
                        { value: String(chain.products.length), label: 'Products', sub: 'GTIN-coded' },
                        { value: String(chain.cteFlow.length), label: 'CTE Steps', sub: 'CFR-mapped' },
                    ].map((stat, i) => (
                        <div
                            key={i}
                            className="p-5 bg-[rgba(255,255,255,0.02)] border border-[rgba(255,255,255,0.05)] rounded-[10px] text-center"
                        >
                            <div className="text-[28px] font-bold font-['JetBrains_Mono',_monospace]" style={{ color: chain.accentColor }}>{stat.value}</div>
                            <div className="text-[13px] font-semibold text-[var(--re-text-primary)] mt-1">{stat.label}</div>
                            <div className="text-[10px] text-[var(--re-text-disabled)] font-['JetBrains_Mono',_monospace] mt-0.5">{stat.sub}</div>
                        </div>
                    ))}
                </div>

                {/* CTE Flow Diagram */}
                <div className="mb-10">
                    <div className="flex items-center justify-between mb-4">
                        <div>
                            <h2 className="text-xl font-bold text-[var(--re-text-primary)] m-0 mb-1">CTE Event Flow</h2>
                            <p className="text-[13px] text-[var(--re-text-muted)] m-0">Critical Tracking Events required by FSMA 204</p>
                        </div>
                        <button
                            onClick={() => setShowCteTimeline(!showCteTimeline)}
                            className="py-2 px-4 rounded-lg text-xs font-semibold cursor-pointer font-inherit transition-all duration-200"
                            style={{
                                background: showCteTimeline ? `${chain.accentColor}15` : 'rgba(255,255,255,0.04)',
                                border: `1px solid ${showCteTimeline ? chain.accentColor + '40' : 'rgba(255,255,255,0.08)'}`,
                                color: showCteTimeline ? chain.accentColor : 'var(--re-text-tertiary)',
                            }}
                        >
                            {showCteTimeline ? 'Hide Details' : 'Show Details'}
                        </button>
                    </div>

                    {/* Compact flow */}
                    <div
                        className="flex items-center gap-0 overflow-x-auto py-4"
                    >
                        {chain.cteFlow.map((step, i) => (
                            <div key={i} className="flex items-center flex-shrink-0">
                                <div
                                    className="py-[10px] px-3.5 rounded-lg min-w-[120px] text-center"
                                    style={{
                                        background: `${chain.accentColor}08`,
                                        border: `1px solid ${chain.accentColor}25`,
                                    }}
                                >
                                    <div
                                        className="text-[10px] font-['JetBrains_Mono',_monospace] font-semibold mb-1"
                                        style={{
                                            color: chain.accentColor,
                                        }}
                                    >
                                        {step.cte}
                                    </div>
                                    <div className="text-[11px] text-[var(--re-text-tertiary)]">{step.cfr}</div>
                                </div>
                                {i < chain.cteFlow.length - 1 && (
                                    <div className="px-1.5 text-[var(--re-text-disabled)]">
                                        <ArrowRight size={14} />
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>

                    {/* Expanded CTE timeline */}
                    {showCteTimeline && (
                        <div
                            className="mt-4 p-0"
                        >
                            {chain.cteFlow.map((step, i) => (
                                <div
                                    key={i}
                                    className="flex gap-4 py-4"
                                    style={{
                                        borderBottom: i < chain.cteFlow.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none',
                                    }}
                                >
                                    <div
                                        className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold font-['JetBrains_Mono',_monospace]"
                                        style={{
                                            background: `${chain.accentColor}15`,
                                            border: `1px solid ${chain.accentColor}30`,
                                            color: chain.accentColor,
                                        }}
                                    >
                                        {i + 1}
                                    </div>
                                    <div className="flex-1">
                                        <div className="flex items-center gap-[10px] mb-1">
                                            <span className="text-[13px] font-semibold text-[var(--re-text-primary)]">{step.cte}</span>
                                            <span
                                                className="text-[10px] font-['JetBrains_Mono',_monospace] py-0.5 px-2 rounded"
                                                style={{
                                                    color: chain.accentColor,
                                                    background: `${chain.accentColor}10`,
                                                }}
                                            >
                                                {step.cfr}
                                            </span>
                                        </div>
                                        <div className="text-xs text-[var(--re-text-muted)] mb-0.5">{step.description}</div>
                                        <div className="text-[11px] text-[var(--re-text-disabled)] font-['JetBrains_Mono',_monospace]">
                                            📍 {step.facility}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* ─── FACILITIES GRID ─── */}
                <div className="mb-10">
                    <h2 className="text-xl font-bold text-[var(--re-text-primary)] m-0 mb-1">Facilities</h2>
                    <p className="text-[13px] text-[var(--re-text-muted)] m-0 mb-4">
                        GLN-identified locations across the supply chain
                    </p>

                    <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-3">
                        {chain.facilities.map((facility) => {
                            const isExpanded = expandedFacility === facility.gln;
                            return (
                                <button
                                    key={facility.gln}
                                    onClick={() => setExpandedFacility(isExpanded ? null : facility.gln)}
                                    className="p-4 rounded-[10px] text-left cursor-pointer text-inherit font-inherit transition-all duration-200"
                                    style={{
                                        background: isExpanded ? `${chain.accentColor}06` : 'rgba(255,255,255,0.02)',
                                        border: `1px solid ${isExpanded ? chain.accentColor + '30' : 'rgba(255,255,255,0.05)'}`,
                                    }}
                                >
                                    <div className="flex items-center gap-[10px] mb-2">
                                        <span className="text-xl">{getFacilityIcon(facility.type)}</span>
                                        <div className="flex-1">
                                            <div className="text-[13px] font-semibold text-[var(--re-text-primary)]">{facility.name}</div>
                                            <div className="text-[10px] font-['JetBrains_Mono',_monospace] text-[var(--re-text-disabled)]">
                                                {facility.type}
                                            </div>
                                        </div>
                                    </div>

                                    {/* GLN */}
                                    <div
                                        className="text-[11px] font-['JetBrains_Mono',_monospace] text-[var(--re-text-muted)] bg-[rgba(255,255,255,0.03)] py-1 px-2 rounded"
                                        style={{
                                            marginBottom: isExpanded ? '10px' : '0',
                                        }}
                                    >
                                        GLN: {facility.gln}
                                    </div>

                                    {isExpanded && (
                                        <div className="mt-2 text-xs text-[var(--re-text-tertiary)] leading-[1.5]">
                                            {facility.address && (
                                                <div className="mb-1">📍 {facility.address}</div>
                                            )}
                                            {facility.extra && Object.entries(facility.extra).map(([key, val]) => (
                                                <div key={key} className="mb-0.5">
                                                    <span className="text-[var(--re-text-disabled)]">{key}:</span> {val}
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </button>
                            );
                        })}
                    </div>
                </div>

                {/* ─── PRODUCTS TABLE ─── */}
                <div className="mb-10">
                    <h2 className="text-xl font-bold text-[var(--re-text-primary)] m-0 mb-1">Products</h2>
                    <p className="text-[13px] text-[var(--re-text-muted)] m-0 mb-4">
                        {chain.id === 'rizo-dairy'
                            ? 'Products are split by FTL coverage status — this is the key demo insight'
                            : 'GTIN-coded products tracked through the supply chain'}
                    </p>

                    <div
                        className="border border-[rgba(255,255,255,0.05)] rounded-[10px] overflow-hidden"
                    >
                        {/* Table header */}
                        <div
                            className="py-[10px] px-4 bg-[rgba(255,255,255,0.03)] border-b border-[rgba(255,255,255,0.05)] text-[10px] font-['JetBrains_Mono',_monospace] font-semibold text-[var(--re-text-disabled)] uppercase tracking-[0.08em]"
                            style={{
                                display: 'grid',
                                gridTemplateColumns: chain.id === 'rizo-dairy' ? '2fr 2fr 1fr 1fr' : '2fr 2fr 1fr',
                            }}
                        >
                            <div>Product</div>
                            <div>GTIN</div>
                            <div>Category</div>
                            {chain.id === 'rizo-dairy' && <div className="text-center">On FTL?</div>}
                        </div>

                        {/* Rows */}
                        {chain.products.map((product, i) => (
                            <div
                                key={product.gtin}
                                className="py-3 px-4 text-[13px] items-center"
                                style={{
                                    display: 'grid',
                                    gridTemplateColumns: chain.id === 'rizo-dairy' ? '2fr 2fr 1fr 1fr' : '2fr 2fr 1fr',
                                    borderBottom: i < chain.products.length - 1 ? '1px solid rgba(255,255,255,0.03)' : 'none',
                                    background: chain.id === 'rizo-dairy' && product.onFtl === false
                                        ? 'rgba(239,68,68,0.03)'
                                        : 'transparent',
                                }}
                            >
                                <div className="font-medium text-[var(--re-text-primary)]">{product.name}</div>
                                <div className="font-['JetBrains_Mono',_monospace] text-[11px] text-[var(--re-text-muted)]">
                                    {product.gtin}
                                </div>
                                <div className="text-[11px] text-[var(--re-text-tertiary)]">{product.category}</div>
                                {chain.id === 'rizo-dairy' && (
                                    <div className="text-center">
                                        {product.onFtl ? (
                                            <span
                                                className="inline-flex items-center gap-1 text-[10px] font-semibold text-[var(--re-brand)] bg-[rgba(16,185,129,0.1)] py-[3px] px-[10px] rounded-[10px]"
                                            >
                                                <CheckIcon size={10} /> YES
                                            </span>
                                        ) : (
                                            <span
                                                className="inline-flex items-center gap-1 text-[10px] font-semibold text-[var(--re-danger)] bg-[rgba(239,68,68,0.1)] py-[3px] px-[10px] rounded-[10px]"
                                            >
                                                <XIcon size={10} /> NO
                                            </span>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>

                    {/* FTL coverage callout for dairy chain */}
                    {chain.id === 'rizo-dairy' && (
                        <div
                            className="mt-3 py-3.5 px-4 bg-[rgba(245,158,11,0.05)] border-l-[3px] border-l-[#f59e0b] rounded-r-lg text-[13px] text-[var(--re-text-tertiary)] leading-[1.5]"
                        >
                            <strong className="text-[var(--re-warning)]">Why this matters:</strong> Hard cheeses and sour cream are
                            <strong className="text-[var(--re-danger)]"> NOT </strong> on the FDA Food Traceability List, even though
                            soft cheeses from the same facility <strong className="text-[var(--re-brand)]">are</strong>. A blanket
                            compliance program wastes resources. The FTL Checker tells you exactly which products need tracking.
                        </div>
                    )}
                </div>

                {/* ─── KEY DATA ELEMENTS ─── */}
                <div className="mb-10">
                    <h2 className="text-xl font-bold text-[var(--re-text-primary)] m-0 mb-1">Key Data Elements (KDEs)</h2>
                    <p className="text-[13px] text-[var(--re-text-muted)] m-0 mb-4">
                        FDA-required data points captured at every CTE in this chain
                    </p>

                    <div className="flex flex-wrap gap-2">
                        {chain.keyKDEs.map((kde) => (
                            <div
                                key={kde}
                                className="inline-flex items-center gap-1.5 py-2 px-3.5 bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.06)] rounded-lg text-xs font-medium text-[var(--re-text-tertiary)]"
                            >
                                <span className="text-[10px]" style={{ color: chain.accentColor }}>●</span>
                                {kde}
                            </div>
                        ))}
                    </div>
                </div>

                {/* ─── CRYPTOGRAPHIC PROOF SECTION ─── */}
                <div
                    className="p-6 bg-[rgba(255,255,255,0.02)] border border-[rgba(255,255,255,0.05)] rounded-xl mb-10"
                >
                    <div className="flex items-center gap-[10px] mb-3">
                        <div className="text-[var(--re-accent-purple)]">
                            <HashIcon size={20} />
                        </div>
                        <h2 className="text-[18px] font-bold text-[var(--re-text-primary)] m-0">Cryptographic Integrity</h2>
                    </div>
                    <p className="text-[13px] text-[var(--re-text-muted)] leading-[1.6] m-0 mb-4">
                        Every one of the {chain.eventCount} records in this chain has a SHA-256 hash computed from canonical JSON serialization.
                        You can verify every record independently using our open-source <code className="text-xs font-['JetBrains_Mono',_monospace] bg-[rgba(255,255,255,0.04)] py-0.5 px-1.5 rounded text-[var(--re-accent-purple)]">verify_chain.py</code> script.
                    </p>

                    <div
                        className="py-3 px-4 bg-[var(--re-surface-base)] rounded-lg font-['JetBrains_Mono',_monospace] text-xs text-[var(--re-text-tertiary)] overflow-x-auto leading-[1.7]"
                    >
                        <span className="text-[var(--re-success)]">$</span>{' '}
                        <span className="text-[var(--re-text-secondary)]">python3 verify_chain.py --offline</span>
                        <br />
                        <span className="text-[var(--re-accent-blue)]">Verifying {chain.eventCount} records...</span>
                        <br />
                        <span className="text-[var(--re-success)]">✓ {chain.eventCount}/{chain.eventCount} hashes valid (100%)</span>
                        <br />
                        <span className="text-[var(--re-success)]">✓ Canonical JSON serialization matches</span>
                        <br />
                        <span className="text-[var(--re-success)]">✓ No tamper detected</span>
                    </div>
                </div>

                {/* ─── CTAs ─── */}
                <div
                    className="grid grid-cols-3 gap-3"
                >
                    <Link
                        href="/demo/mock-recall"
                        className="p-5 bg-[rgba(239,68,68,0.05)] border border-[rgba(239,68,68,0.15)] rounded-xl no-underline transition-all duration-300 ease-[ease] block"
                    >
                        <div className="text-xl mb-2">🚨</div>
                        <div className="text-sm font-semibold text-[var(--re-text-primary)] mb-1">Mock Recall Demo</div>
                        <div className="text-xs text-[var(--re-text-muted)] leading-[1.4]">
                            Watch a contaminated lot traced through the supply chain in under 5 seconds
                        </div>
                        <div className="text-xs font-semibold text-[var(--re-danger)] mt-[10px] flex items-center gap-1">
                            Run Demo <ArrowRight size={12} />
                        </div>
                    </Link>

                    <Link
                        href="/ftl-checker"
                        className="p-5 bg-[rgba(16,185,129,0.05)] border border-[rgba(16,185,129,0.15)] rounded-xl no-underline transition-all duration-300 ease-[ease] block"
                    >
                        <div className="text-xl mb-2">✅</div>
                        <div className="text-sm font-semibold text-[var(--re-text-primary)] mb-1">FTL Coverage Checker</div>
                        <div className="text-xs text-[var(--re-text-muted)] leading-[1.4]">
                            Check which of your products are on the FDA Food Traceability List
                        </div>
                        <div className="text-xs font-semibold text-[var(--re-brand)] mt-[10px] flex items-center gap-1">
                            Check Now <ArrowRight size={12} />
                        </div>
                    </Link>

                    <Link
                        href="/verify"
                        className="p-5 bg-[rgba(129,140,248,0.05)] border border-[rgba(129,140,248,0.15)] rounded-xl no-underline transition-all duration-300 ease-[ease] block"
                    >
                        <div className="text-xl mb-2">🔐</div>
                        <div className="text-sm font-semibold text-[var(--re-text-primary)] mb-1">Verify Records</div>
                        <div className="text-xs text-[var(--re-text-muted)] leading-[1.4]">
                            Independently verify cryptographic integrity of any RegEngine record
                        </div>
                        <div className="text-xs font-semibold text-[var(--re-accent-purple)] mt-[10px] flex items-center gap-1">
                            Verify <ArrowRight size={12} />
                        </div>
                    </Link>
                </div>
            </section>

            {/* ─── FOOTER BREADCRUMB ─── */}
            <section
                className="relative z-[2] border-t border-[rgba(255,255,255,0.04)] p-6"
            >
                <div className="max-w-[1120px] mx-auto flex justify-between items-center">
                    <div className="text-xs text-[var(--re-text-disabled)]">
                        Data generated by <code className="font-['JetBrains_Mono',_monospace] text-[var(--re-text-muted)] text-[11px]">seed_fsma_data.py v3</code> — 430 CTE records across 3 recall chains
                    </div>
                    <Link href="/docs/fsma-204" className="text-xs text-[var(--re-brand)] no-underline font-medium">
                        Read FSMA 204 Documentation →
                    </Link>
                </div>
            </section>

            {/* ─── ANIMATIONS ─── */}
            <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
        </div>
    );
}
