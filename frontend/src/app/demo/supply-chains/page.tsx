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
            style={{
                minHeight: '100vh',
                background: 'var(--re-surface-base)',
                fontFamily: "'Instrument Sans', -apple-system, BlinkMacSystemFont, sans-serif",
                color: 'var(--re-text-secondary)',
                overflowX: 'hidden',
            }}
        >
            <link
                href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
                rel="stylesheet"
            />

            {/* Noise texture */}
            <div
                style={{
                    position: 'fixed',
                    inset: 0,
                    opacity: 0.015,
                    backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
                    backgroundSize: '128px 128px',
                    pointerEvents: 'none',
                    zIndex: 1,
                }}
            />

            {/* ─── HERO HEADER ─── */}
            <section
                style={{
                    position: 'relative',
                    zIndex: 2,
                    maxWidth: '1120px',
                    margin: '0 auto',
                    padding: '80px 24px 40px',
                }}
            >
                {/* Gradient glow */}
                <div
                    style={{
                        position: 'absolute',
                        top: '-80px',
                        left: '50%',
                        transform: 'translateX(-50%)',
                        width: '700px',
                        height: '400px',
                        background: `radial-gradient(ellipse, ${chain.accentColor}0f 0%, transparent 70%)`,
                        pointerEvents: 'none',
                        transition: 'background 0.6s ease',
                    }}
                />

                <div
                    style={{
                        opacity: animateIn ? 1 : 0,
                        transform: animateIn ? 'translateY(0)' : 'translateY(20px)',
                        transition: 'all 0.8s cubic-bezier(0.16, 1, 0.3, 1)',
                    }}
                >
                    {/* Breadcrumb */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '24px', fontSize: '13px' }}>
                        <Link href="/" style={{ color: 'var(--re-text-disabled)', textDecoration: 'none', transition: 'color 0.2s' }}>Home</Link>
                        <span style={{ color: 'var(--re-text-disabled)' }}>/</span>
                        <Link href="/demo/mock-recall" style={{ color: 'var(--re-text-disabled)', textDecoration: 'none', transition: 'color 0.2s' }}>Demo</Link>
                        <span style={{ color: 'var(--re-text-disabled)' }}>/</span>
                        <span style={{ color: 'var(--re-text-tertiary)' }}>Supply Chain Explorer</span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                        <span
                            style={{
                                padding: '4px 12px',
                                background: 'rgba(16,185,129,0.08)',
                                border: '1px solid rgba(16,185,129,0.15)',
                                borderRadius: '20px',
                                fontSize: '11px',
                                fontFamily: "'JetBrains Mono', monospace",
                                fontWeight: 500,
                                color: 'var(--re-brand)',
                            }}
                        >
                            430 LIVE RECORDS
                        </span>
                        <span
                            style={{
                                padding: '4px 12px',
                                background: 'rgba(99,102,241,0.08)',
                                border: '1px solid rgba(99,102,241,0.15)',
                                borderRadius: '20px',
                                fontSize: '11px',
                                fontFamily: "'JetBrains Mono', monospace",
                                fontWeight: 500,
                                color: 'var(--re-accent-purple)',
                            }}
                        >
                            SHA-256 VERIFIED
                        </span>
                    </div>

                    <h1
                        style={{
                            fontSize: 'clamp(32px, 4.5vw, 48px)',
                            fontWeight: 700,
                            color: 'var(--re-text-primary)',
                            lineHeight: 1.1,
                            margin: '0 0 16px',
                            letterSpacing: '-0.02em',
                        }}
                    >
                        Supply Chain Explorer
                    </h1>
                    <p style={{ fontSize: '17px', color: 'var(--re-text-muted)', lineHeight: 1.6, maxWidth: '640px', margin: 0 }}>
                        Explore 3 real-world recall scenarios modeled on FDA enforcement actions. Every record is
                        cryptographically hashed and independently verifiable — this is what FSMA 204 compliance looks like in practice.
                    </p>
                </div>
            </section>

            {/* ─── CHAIN SELECTOR TABS ─── */}
            <section style={{ position: 'relative', zIndex: 2, maxWidth: '1120px', margin: '0 auto', padding: '0 24px 40px' }}>
                <div
                    style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(3, 1fr)',
                        gap: '12px',
                    }}
                >
                    {CHAINS.map((c) => {
                        const isActive = selectedChain === c.id;
                        return (
                            <button
                                key={c.id}
                                onClick={() => handleChainSwitch(c.id)}
                                style={{
                                    padding: '20px',
                                    background: isActive
                                        ? `linear-gradient(135deg, ${c.accentColor}12, ${c.accentColor}06)`
                                        : 'rgba(255,255,255,0.02)',
                                    border: `1px solid ${isActive ? c.accentColor + '40' : 'rgba(255,255,255,0.06)'}`,
                                    borderRadius: '12px',
                                    cursor: 'pointer',
                                    textAlign: 'left',
                                    color: 'inherit',
                                    fontFamily: 'inherit',
                                    transition: 'all 0.3s ease',
                                    position: 'relative',
                                    overflow: 'hidden',
                                }}
                            >
                                {isActive && (
                                    <div
                                        style={{
                                            position: 'absolute',
                                            top: 0,
                                            left: 0,
                                            right: 0,
                                            height: '2px',
                                            background: c.accentColor,
                                        }}
                                    />
                                )}
                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
                                    <span style={{ fontSize: '24px' }}>{c.icon}</span>
                                    <div style={{ flex: 1 }}>
                                        <div style={{ fontSize: '14px', fontWeight: 600, color: isActive ? 'var(--re-text-primary)' : 'var(--re-text-tertiary)' }}>
                                            {c.title}
                                        </div>
                                        <div style={{ fontSize: '11px', color: 'var(--re-text-disabled)', fontFamily: "'JetBrains Mono', monospace" }}>
                                            {c.eventCount} events • {c.batchCount} batches
                                        </div>
                                    </div>
                                </div>
                                <div style={{ fontSize: '12px', color: 'var(--re-text-muted)', lineHeight: 1.4 }}>{c.subtitle}</div>
                            </button>
                        );
                    })}
                </div>
            </section>

            {/* ─── CHAIN DETAIL ─── */}
            <section
                key={chain.id}
                style={{
                    position: 'relative',
                    zIndex: 2,
                    maxWidth: '1120px',
                    margin: '0 auto',
                    padding: '0 24px 80px',
                }}
            >
                {/* Recall Basis Banner */}
                <div
                    style={{
                        padding: '16px 20px',
                        background: `linear-gradient(90deg, ${chain.accentColor}08, transparent)`,
                        borderLeft: `3px solid ${chain.accentColor}`,
                        borderRadius: '0 8px 8px 0',
                        marginBottom: '32px',
                    }}
                >
                    <div style={{ fontSize: '11px', fontFamily: "'JetBrains Mono', monospace", color: 'var(--re-text-disabled)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                        Based on real FDA recall
                    </div>
                    <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--re-text-primary)' }}>{chain.recallBasis}</div>
                    <div style={{ fontSize: '13px', color: 'var(--re-text-tertiary)', marginTop: '6px', lineHeight: 1.5 }}>{chain.demoStory}</div>
                </div>

                {/* Stats Row */}
                <div
                    style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(4, 1fr)',
                        gap: '12px',
                        marginBottom: '32px',
                    }}
                >
                    {[
                        { value: String(chain.eventCount), label: 'CTE Records', sub: 'SHA-256 hashed' },
                        { value: String(chain.facilities.length), label: 'Facilities', sub: 'GLN-identified' },
                        { value: String(chain.products.length), label: 'Products', sub: 'GTIN-coded' },
                        { value: String(chain.cteFlow.length), label: 'CTE Steps', sub: 'CFR-mapped' },
                    ].map((stat, i) => (
                        <div
                            key={i}
                            style={{
                                padding: '20px',
                                background: 'rgba(255,255,255,0.02)',
                                border: '1px solid rgba(255,255,255,0.05)',
                                borderRadius: '10px',
                                textAlign: 'center',
                            }}
                        >
                            <div style={{ fontSize: '28px', fontWeight: 700, color: chain.accentColor, fontFamily: "'JetBrains Mono', monospace" }}>{stat.value}</div>
                            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--re-text-primary)', marginTop: '4px' }}>{stat.label}</div>
                            <div style={{ fontSize: '10px', color: 'var(--re-text-disabled)', fontFamily: "'JetBrains Mono', monospace", marginTop: '2px' }}>{stat.sub}</div>
                        </div>
                    ))}
                </div>

                {/* CTE Flow Diagram */}
                <div style={{ marginBottom: '40px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                        <div>
                            <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--re-text-primary)', margin: '0 0 4px' }}>CTE Event Flow</h2>
                            <p style={{ fontSize: '13px', color: 'var(--re-text-muted)', margin: 0 }}>Critical Tracking Events required by FSMA 204</p>
                        </div>
                        <button
                            onClick={() => setShowCteTimeline(!showCteTimeline)}
                            style={{
                                padding: '8px 16px',
                                background: showCteTimeline ? `${chain.accentColor}15` : 'rgba(255,255,255,0.04)',
                                border: `1px solid ${showCteTimeline ? chain.accentColor + '40' : 'rgba(255,255,255,0.08)'}`,
                                borderRadius: '8px',
                                color: showCteTimeline ? chain.accentColor : 'var(--re-text-tertiary)',
                                fontSize: '12px',
                                fontWeight: 600,
                                cursor: 'pointer',
                                fontFamily: 'inherit',
                                transition: 'all 0.2s',
                            }}
                        >
                            {showCteTimeline ? 'Hide Details' : 'Show Details'}
                        </button>
                    </div>

                    {/* Compact flow */}
                    <div
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0',
                            overflowX: 'auto',
                            padding: '16px 0',
                        }}
                    >
                        {chain.cteFlow.map((step, i) => (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
                                <div
                                    style={{
                                        padding: '10px 14px',
                                        background: `${chain.accentColor}08`,
                                        border: `1px solid ${chain.accentColor}25`,
                                        borderRadius: '8px',
                                        minWidth: '120px',
                                        textAlign: 'center',
                                    }}
                                >
                                    <div
                                        style={{
                                            fontSize: '10px',
                                            fontFamily: "'JetBrains Mono', monospace",
                                            fontWeight: 600,
                                            color: chain.accentColor,
                                            marginBottom: '4px',
                                        }}
                                    >
                                        {step.cte}
                                    </div>
                                    <div style={{ fontSize: '11px', color: 'var(--re-text-tertiary)' }}>{step.cfr}</div>
                                </div>
                                {i < chain.cteFlow.length - 1 && (
                                    <div style={{ padding: '0 6px', color: 'var(--re-text-disabled)' }}>
                                        <ArrowRight size={14} />
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>

                    {/* Expanded CTE timeline */}
                    {showCteTimeline && (
                        <div
                            style={{
                                marginTop: '16px',
                                padding: '0',
                            }}
                        >
                            {chain.cteFlow.map((step, i) => (
                                <div
                                    key={i}
                                    style={{
                                        display: 'flex',
                                        gap: '16px',
                                        padding: '16px 0',
                                        borderBottom: i < chain.cteFlow.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none',
                                    }}
                                >
                                    <div
                                        style={{
                                            width: '32px',
                                            height: '32px',
                                            borderRadius: '50%',
                                            background: `${chain.accentColor}15`,
                                            border: `1px solid ${chain.accentColor}30`,
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            flexShrink: 0,
                                            fontSize: '12px',
                                            fontWeight: 700,
                                            color: chain.accentColor,
                                            fontFamily: "'JetBrains Mono', monospace",
                                        }}
                                    >
                                        {i + 1}
                                    </div>
                                    <div style={{ flex: 1 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
                                            <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--re-text-primary)' }}>{step.cte}</span>
                                            <span
                                                style={{
                                                    fontSize: '10px',
                                                    fontFamily: "'JetBrains Mono', monospace",
                                                    color: chain.accentColor,
                                                    background: `${chain.accentColor}10`,
                                                    padding: '2px 8px',
                                                    borderRadius: '4px',
                                                }}
                                            >
                                                {step.cfr}
                                            </span>
                                        </div>
                                        <div style={{ fontSize: '12px', color: 'var(--re-text-muted)', marginBottom: '2px' }}>{step.description}</div>
                                        <div style={{ fontSize: '11px', color: 'var(--re-text-disabled)', fontFamily: "'JetBrains Mono', monospace" }}>
                                            📍 {step.facility}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* ─── FACILITIES GRID ─── */}
                <div style={{ marginBottom: '40px' }}>
                    <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--re-text-primary)', margin: '0 0 4px' }}>Facilities</h2>
                    <p style={{ fontSize: '13px', color: 'var(--re-text-muted)', margin: '0 0 16px' }}>
                        GLN-identified locations across the supply chain
                    </p>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '12px' }}>
                        {chain.facilities.map((facility) => {
                            const isExpanded = expandedFacility === facility.gln;
                            return (
                                <button
                                    key={facility.gln}
                                    onClick={() => setExpandedFacility(isExpanded ? null : facility.gln)}
                                    style={{
                                        padding: '16px',
                                        background: isExpanded ? `${chain.accentColor}06` : 'rgba(255,255,255,0.02)',
                                        border: `1px solid ${isExpanded ? chain.accentColor + '30' : 'rgba(255,255,255,0.05)'}`,
                                        borderRadius: '10px',
                                        textAlign: 'left',
                                        cursor: 'pointer',
                                        color: 'inherit',
                                        fontFamily: 'inherit',
                                        transition: 'all 0.2s',
                                    }}
                                >
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
                                        <span style={{ fontSize: '20px' }}>{getFacilityIcon(facility.type)}</span>
                                        <div style={{ flex: 1 }}>
                                            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--re-text-primary)' }}>{facility.name}</div>
                                            <div style={{ fontSize: '10px', fontFamily: "'JetBrains Mono', monospace", color: 'var(--re-text-disabled)' }}>
                                                {facility.type}
                                            </div>
                                        </div>
                                    </div>

                                    {/* GLN */}
                                    <div
                                        style={{
                                            fontSize: '11px',
                                            fontFamily: "'JetBrains Mono', monospace",
                                            color: 'var(--re-text-muted)',
                                            background: 'rgba(255,255,255,0.03)',
                                            padding: '4px 8px',
                                            borderRadius: '4px',
                                            marginBottom: isExpanded ? '10px' : '0',
                                        }}
                                    >
                                        GLN: {facility.gln}
                                    </div>

                                    {isExpanded && (
                                        <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--re-text-tertiary)', lineHeight: 1.5 }}>
                                            {facility.address && (
                                                <div style={{ marginBottom: '4px' }}>📍 {facility.address}</div>
                                            )}
                                            {facility.extra && Object.entries(facility.extra).map(([key, val]) => (
                                                <div key={key} style={{ marginBottom: '2px' }}>
                                                    <span style={{ color: 'var(--re-text-disabled)' }}>{key}:</span> {val}
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
                <div style={{ marginBottom: '40px' }}>
                    <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--re-text-primary)', margin: '0 0 4px' }}>Products</h2>
                    <p style={{ fontSize: '13px', color: 'var(--re-text-muted)', margin: '0 0 16px' }}>
                        {chain.id === 'rizo-dairy'
                            ? 'Products are split by FTL coverage status — this is the key demo insight'
                            : 'GTIN-coded products tracked through the supply chain'}
                    </p>

                    <div
                        style={{
                            border: '1px solid rgba(255,255,255,0.05)',
                            borderRadius: '10px',
                            overflow: 'hidden',
                        }}
                    >
                        {/* Table header */}
                        <div
                            style={{
                                display: 'grid',
                                gridTemplateColumns: chain.id === 'rizo-dairy' ? '2fr 2fr 1fr 1fr' : '2fr 2fr 1fr',
                                padding: '10px 16px',
                                background: 'rgba(255,255,255,0.03)',
                                borderBottom: '1px solid rgba(255,255,255,0.05)',
                                fontSize: '10px',
                                fontFamily: "'JetBrains Mono', monospace",
                                fontWeight: 600,
                                color: 'var(--re-text-disabled)',
                                textTransform: 'uppercase',
                                letterSpacing: '0.08em',
                            }}
                        >
                            <div>Product</div>
                            <div>GTIN</div>
                            <div>Category</div>
                            {chain.id === 'rizo-dairy' && <div style={{ textAlign: 'center' }}>On FTL?</div>}
                        </div>

                        {/* Rows */}
                        {chain.products.map((product, i) => (
                            <div
                                key={product.gtin}
                                style={{
                                    display: 'grid',
                                    gridTemplateColumns: chain.id === 'rizo-dairy' ? '2fr 2fr 1fr 1fr' : '2fr 2fr 1fr',
                                    padding: '12px 16px',
                                    borderBottom: i < chain.products.length - 1 ? '1px solid rgba(255,255,255,0.03)' : 'none',
                                    fontSize: '13px',
                                    alignItems: 'center',
                                    background: chain.id === 'rizo-dairy' && product.onFtl === false
                                        ? 'rgba(239,68,68,0.03)'
                                        : 'transparent',
                                }}
                            >
                                <div style={{ fontWeight: 500, color: 'var(--re-text-primary)' }}>{product.name}</div>
                                <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '11px', color: 'var(--re-text-muted)' }}>
                                    {product.gtin}
                                </div>
                                <div style={{ fontSize: '11px', color: 'var(--re-text-tertiary)' }}>{product.category}</div>
                                {chain.id === 'rizo-dairy' && (
                                    <div style={{ textAlign: 'center' }}>
                                        {product.onFtl ? (
                                            <span
                                                style={{
                                                    display: 'inline-flex',
                                                    alignItems: 'center',
                                                    gap: '4px',
                                                    fontSize: '10px',
                                                    fontWeight: 600,
                                                    color: 'var(--re-brand)',
                                                    background: 'rgba(16,185,129,0.1)',
                                                    padding: '3px 10px',
                                                    borderRadius: '10px',
                                                }}
                                            >
                                                <CheckIcon size={10} /> YES
                                            </span>
                                        ) : (
                                            <span
                                                style={{
                                                    display: 'inline-flex',
                                                    alignItems: 'center',
                                                    gap: '4px',
                                                    fontSize: '10px',
                                                    fontWeight: 600,
                                                    color: 'var(--re-danger)',
                                                    background: 'rgba(239,68,68,0.1)',
                                                    padding: '3px 10px',
                                                    borderRadius: '10px',
                                                }}
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
                            style={{
                                marginTop: '12px',
                                padding: '14px 16px',
                                background: 'rgba(245,158,11,0.05)',
                                borderLeft: '3px solid #f59e0b',
                                borderRadius: '0 8px 8px 0',
                                fontSize: '13px',
                                color: 'var(--re-text-tertiary)',
                                lineHeight: 1.5,
                            }}
                        >
                            <strong style={{ color: 'var(--re-warning)' }}>Why this matters:</strong> Hard cheeses and sour cream are
                            <strong style={{ color: 'var(--re-danger)' }}> NOT </strong> on the FDA Food Traceability List, even though
                            soft cheeses from the same facility <strong style={{ color: 'var(--re-brand)' }}>are</strong>. A blanket
                            compliance program wastes resources. The FTL Checker tells you exactly which products need tracking.
                        </div>
                    )}
                </div>

                {/* ─── KEY DATA ELEMENTS ─── */}
                <div style={{ marginBottom: '40px' }}>
                    <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--re-text-primary)', margin: '0 0 4px' }}>Key Data Elements (KDEs)</h2>
                    <p style={{ fontSize: '13px', color: 'var(--re-text-muted)', margin: '0 0 16px' }}>
                        FDA-required data points captured at every CTE in this chain
                    </p>

                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                        {chain.keyKDEs.map((kde) => (
                            <div
                                key={kde}
                                style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '6px',
                                    padding: '8px 14px',
                                    background: 'rgba(255,255,255,0.03)',
                                    border: '1px solid rgba(255,255,255,0.06)',
                                    borderRadius: '8px',
                                    fontSize: '12px',
                                    fontWeight: 500,
                                    color: 'var(--re-text-tertiary)',
                                }}
                            >
                                <span style={{ color: chain.accentColor, fontSize: '10px' }}>●</span>
                                {kde}
                            </div>
                        ))}
                    </div>
                </div>

                {/* ─── CRYPTOGRAPHIC PROOF SECTION ─── */}
                <div
                    style={{
                        padding: '24px',
                        background: 'rgba(255,255,255,0.02)',
                        border: '1px solid rgba(255,255,255,0.05)',
                        borderRadius: '12px',
                        marginBottom: '40px',
                    }}
                >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
                        <div style={{ color: 'var(--re-accent-purple)' }}>
                            <HashIcon size={20} />
                        </div>
                        <h2 style={{ fontSize: '18px', fontWeight: 700, color: 'var(--re-text-primary)', margin: 0 }}>Cryptographic Integrity</h2>
                    </div>
                    <p style={{ fontSize: '13px', color: 'var(--re-text-muted)', lineHeight: 1.6, margin: '0 0 16px' }}>
                        Every one of the {chain.eventCount} records in this chain has a SHA-256 hash computed from canonical JSON serialization.
                        You can verify every record independently using our open-source <code style={{ fontSize: '12px', fontFamily: "'JetBrains Mono', monospace", background: 'rgba(255,255,255,0.04)', padding: '2px 6px', borderRadius: '4px', color: 'var(--re-accent-purple)' }}>verify_chain.py</code> script.
                    </p>

                    <div
                        style={{
                            padding: '12px 16px',
                            background: 'var(--re-surface-base)',
                            borderRadius: '8px',
                            fontFamily: "'JetBrains Mono', monospace",
                            fontSize: '12px',
                            color: 'var(--re-text-tertiary)',
                            overflowX: 'auto',
                            lineHeight: 1.7,
                        }}
                    >
                        <span style={{ color: 'var(--re-success)' }}>$</span>{' '}
                        <span style={{ color: 'var(--re-text-secondary)' }}>python3 verify_chain.py --offline</span>
                        <br />
                        <span style={{ color: 'var(--re-accent-blue)' }}>Verifying {chain.eventCount} records...</span>
                        <br />
                        <span style={{ color: 'var(--re-success)' }}>✓ {chain.eventCount}/{chain.eventCount} hashes valid (100%)</span>
                        <br />
                        <span style={{ color: 'var(--re-success)' }}>✓ Canonical JSON serialization matches</span>
                        <br />
                        <span style={{ color: 'var(--re-success)' }}>✓ No tamper detected</span>
                    </div>
                </div>

                {/* ─── CTAs ─── */}
                <div
                    style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(3, 1fr)',
                        gap: '12px',
                    }}
                >
                    <Link
                        href="/demo/mock-recall"
                        style={{
                            padding: '20px',
                            background: 'rgba(239,68,68,0.05)',
                            border: '1px solid rgba(239,68,68,0.15)',
                            borderRadius: '12px',
                            textDecoration: 'none',
                            transition: 'all 0.3s ease',
                            display: 'block',
                        }}
                    >
                        <div style={{ fontSize: '20px', marginBottom: '8px' }}>🚨</div>
                        <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '4px' }}>Mock Recall Demo</div>
                        <div style={{ fontSize: '12px', color: 'var(--re-text-muted)', lineHeight: 1.4 }}>
                            Watch a contaminated lot traced through the supply chain in under 5 seconds
                        </div>
                        <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--re-danger)', marginTop: '10px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                            Run Demo <ArrowRight size={12} />
                        </div>
                    </Link>

                    <Link
                        href="/ftl-checker"
                        style={{
                            padding: '20px',
                            background: 'rgba(16,185,129,0.05)',
                            border: '1px solid rgba(16,185,129,0.15)',
                            borderRadius: '12px',
                            textDecoration: 'none',
                            transition: 'all 0.3s ease',
                            display: 'block',
                        }}
                    >
                        <div style={{ fontSize: '20px', marginBottom: '8px' }}>✅</div>
                        <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '4px' }}>FTL Coverage Checker</div>
                        <div style={{ fontSize: '12px', color: 'var(--re-text-muted)', lineHeight: 1.4 }}>
                            Check which of your products are on the FDA Food Traceability List
                        </div>
                        <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--re-brand)', marginTop: '10px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                            Check Now <ArrowRight size={12} />
                        </div>
                    </Link>

                    <Link
                        href="/verify"
                        style={{
                            padding: '20px',
                            background: 'rgba(129,140,248,0.05)',
                            border: '1px solid rgba(129,140,248,0.15)',
                            borderRadius: '12px',
                            textDecoration: 'none',
                            transition: 'all 0.3s ease',
                            display: 'block',
                        }}
                    >
                        <div style={{ fontSize: '20px', marginBottom: '8px' }}>🔐</div>
                        <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '4px' }}>Verify Records</div>
                        <div style={{ fontSize: '12px', color: 'var(--re-text-muted)', lineHeight: 1.4 }}>
                            Independently verify cryptographic integrity of any RegEngine record
                        </div>
                        <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--re-accent-purple)', marginTop: '10px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                            Verify <ArrowRight size={12} />
                        </div>
                    </Link>
                </div>
            </section>

            {/* ─── FOOTER BREADCRUMB ─── */}
            <section
                style={{
                    position: 'relative',
                    zIndex: 2,
                    borderTop: '1px solid rgba(255,255,255,0.04)',
                    padding: '24px',
                }}
            >
                <div style={{ maxWidth: '1120px', margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ fontSize: '12px', color: 'var(--re-text-disabled)' }}>
                        Data generated by <code style={{ fontFamily: "'JetBrains Mono', monospace", color: 'var(--re-text-muted)', fontSize: '11px' }}>seed_fsma_data.py v3</code> — 430 CTE records across 3 recall chains
                    </div>
                    <Link href="/docs/fsma-204" style={{ fontSize: '12px', color: 'var(--re-brand)', textDecoration: 'none', fontWeight: 500 }}>
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
