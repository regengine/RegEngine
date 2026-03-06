'use client';

import { useState, useEffect, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';

// ─── Data: Strategic Infrastructure Map (Revision: Mar 06, 2026) ─────────────

const STACKS = [
    {
        id: 'core',
        label: 'OPERATIONAL INFRASTRUCTURE',
        color: '#4fa',
        nodes: [
            {
                id: 'hashchain',
                label: 'Immutable Multi-Chain',
                detail: 'Proprietary evidence sealing using SHA-256 hash chains. Every record in RegEngine is cryptographically linked, creating an unalterable audit trail specifically designed for FDA investigator scrutiny.',
                status: 'live',
            },
            {
                id: 'postgres',
                label: 'Hardened Tenant Isolation',
                detail: 'Postgres architecture utilizing strict Row-Level Security (RLS). Data isolation is enforced at the database kernel level, ensuring zero cross-tenant leakage for enterprise compliance.',
                status: 'live',
            },
            {
                id: 'neo4j',
                label: 'Traceability Graph',
                detail: 'Graph database mapping regulatory obligations to supply chain evidence. Powers our real-time gap analysis and allows auditors to visualize full-chain traceability in seconds.',
                status: 'live',
            },
            {
                id: 'nlp',
                label: 'Regulatory NLP Engine',
                detail: 'Advanced NLP pipeline trained to parse FDA/USDA guidance documents and map text directly to operational KDE requirements, automating obligation mapping.',
                status: 'live',
            },
            {
                id: 'ingestion',
                label: 'Real-time Validation',
                detail: 'High-throughput event processor that validates incoming CTEs (Critical Tracking Events) against FSMA 204 schemas before record finalization.',
                status: 'live',
            },
            {
                id: 'dashboard',
                label: 'Compliance Dashboard',
                detail: 'Web-native interface for supply chain visibility, featuring WCAG 2.1 AA accessibility and real-time dashboarding for FTL coverage reporting.',
                status: 'live',
            },
            {
                id: 'agents',
                label: 'Fractal Agent Swarm',
                detail: 'Fractal agent layer designed for autonomous system-generated audits and continuous integrity monitoring across the platform.',
                status: 'live',
            },
        ],
    },
    {
        id: 'roadmap',
        label: 'STRATEGIC COMMITMENTS',
        color: '#88f',
        nodes: [
            {
                id: 'fdaexport',
                label: 'FDA Export Engine',
                detail: 'Standardized IFT export module designed for 24-hour audit response windows. Internal logic is currently undergoing stability testing for Q3 release.',
                status: 'roadmap',
                date: 'Target Q3 2026',
            },
            {
                id: 'compliance',
                label: 'Compliance Chain-Map',
                detail: 'Advanced KDE-to-CTE cross-referencing for full-chain traceability verification. Currently in active development for the CORE v1.2 release.',
                status: 'roadmap',
                date: 'Target Q3 2026',
            },
            {
                id: 'erp',
                label: 'Enterprise ERP Connectors',
                detail: 'Direct adapters for SAP and Oracle NetSuite to automate CTE ingestion directly from global procurement systems.',
                status: 'roadmap',
                date: 'Target Q4 2026',
            },
            {
                id: 'auth',
                label: 'Enterprise SSO (SAML)',
                detail: 'Centralized identity management and granular RBAC (Role-Based Access Control) for large-scale organizational deployments.',
                status: 'roadmap',
                date: 'Target Q3 2026',
            },
            {
                id: 'alerts',
                label: 'Intelligent Alerting',
                detail: 'Proactive notification system for identifying data gaps and potential 24hr SLA violations across supply chain nodes.',
                status: 'roadmap',
                date: 'Target Q3 2026',
            },
            {
                id: 'iot',
                label: 'IoT Bridge Architecture',
                detail: 'Seamless ingestion of temperature and GPS data from 3rd-party loggers to enrich KDE records on-the-fly.',
                status: 'roadmap',
                date: 'Target 2027',
            },
        ],
    },
];

// ─── Component ───────────────────────────────────────────────────────────────

function RegEngineArchitectureContent() {
    const searchParams = useSearchParams();
    const router = useRouter();

    const [selected, setSelected] = useState(() => searchParams.get('node') ?? null);

    const handleSelect = (id) => {
        const next = selected === id ? null : id;
        setSelected(next);
        const params = new URLSearchParams(searchParams.toString());
        if (next) params.set('node', next);
        else params.delete('node');
        router.replace(`/architecture?${params.toString()}`, { scroll: false });
    };

    const selectedNode = selected ? STACKS.flatMap((s) => s.nodes).find((n) => n.id === selected) : null;

    return (
        <>
            <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(6px); }
          to   { opacity: 1; transform: translateY(0);   }
        }
        .live-node:hover {
          background: rgba(79, 255, 170, 0.04) !important;
          border-color: #4fa !important;
        }
        @media print {
          .nav-hide { display: none !important; }
        }
      `}</style>

            <div
                style={{
                    background: '#04040a',
                    minHeight: '100vh',
                    fontFamily: "'Inter', -apple-system, system-ui, sans-serif",
                    color: '#e0e0e0',
                    padding: '60px 24px',
                    position: 'relative',
                    overflow: 'hidden',
                }}
            >
                <div
                    style={{
                        position: 'fixed',
                        inset: 0,
                        backgroundImage: 'radial-gradient(circle at 2px 2px, rgba(255,255,255,0.03) 1px, transparent 0)',
                        backgroundSize: '32px 32px',
                        pointerEvents: 'none',
                    }}
                />

                <div style={{ maxWidth: 840, margin: '0 auto', position: 'relative', zIndex: 1 }}>
                    <header style={{ marginBottom: 64, textAlign: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 16, marginBottom: 12 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#4fa' }} />
                                <span style={{ fontSize: 11, letterSpacing: 2, color: '#4fa', fontWeight: 800 }}>TRANSPARENCY REPORT</span>
                            </div>
                            <span style={{ color: '#444', fontSize: 10, fontWeight: 700, letterSpacing: 1 }}>REVISION: MAR 06, 2026</span>
                        </div>
                        <h1 style={{ fontSize: 48, fontWeight: 900, color: '#fff', margin: '16px 0', letterSpacing: -2 }}>
                            Infrastructure Roadmap
                        </h1>
                        <p style={{ fontSize: 18, color: '#777', lineHeight: 1.6, maxWidth: 640, margin: '0 auto' }}>
                            We believe transparency is the basis of trust. This map showcases our operational infrastructure alongside our strategic commitments to the food safety community.
                        </p>
                    </header>

                    {/* Operational Section */}
                    <section style={{ marginBottom: 60 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 20 }}>
                            <h2 style={{ fontSize: 12, letterSpacing: 3, color: '#4fa', fontWeight: 900, margin: 0 }}>OPERATIONAL & VERIFIED</h2>
                            <span style={{ fontSize: 10, color: '#444', fontWeight: 700 }}>v0.8.4 RELEASE</span>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
                            {STACKS[0].nodes.map((node) => (
                                <button
                                    key={node.id}
                                    onClick={() => handleSelect(node.id)}
                                    className="live-node"
                                    style={{
                                        background: 'rgba(255,255,255,0.02)',
                                        border: `1px solid ${selected === node.id ? '#4fa' : 'rgba(255,255,255,0.08)'}`,
                                        borderRadius: 12,
                                        padding: '24px',
                                        textAlign: 'left',
                                        cursor: 'pointer',
                                        transition: 'all 0.3s ease',
                                        position: 'relative',
                                    }}
                                >
                                    <div style={{ fontSize: 16, fontWeight: 800, color: '#fff', marginBottom: 8 }}>{node.label}</div>
                                    <div style={{ fontSize: 12, color: '#777', lineHeight: 1.5 }}>{node.detail.slice(0, 65)}...</div>
                                    <div style={{ position: 'absolute', top: 16, right: 16, width: 6, height: 6, borderRadius: '50%', background: '#4fa' }} />
                                </button>
                            ))}
                        </div>
                    </section>

                    {/* Strategic Roadmap Section */}
                    <section style={{ marginBottom: 80 }}>
                        <h2 style={{ fontSize: 12, letterSpacing: 3, color: '#88f', fontWeight: 900, marginBottom: 20 }}>STRATEGIC COMMITMENTS</h2>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
                            {STACKS[1].nodes.map((node) => (
                                <button
                                    key={node.id}
                                    onClick={() => handleSelect(node.id)}
                                    style={{
                                        background: 'rgba(255,255,255,0.01)',
                                        border: `1px solid ${selected === node.id ? '#88f' : 'rgba(255,255,255,0.05)'}`,
                                        borderRadius: 12,
                                        padding: '24px',
                                        textAlign: 'left',
                                        cursor: 'pointer',
                                        transition: 'all 0.3s ease',
                                        position: 'relative',
                                    }}
                                >
                                    <div style={{ fontSize: 15, fontWeight: 700, color: '#555', marginBottom: 6 }}>{node.label}</div>
                                    <div style={{ fontSize: 10, color: '#88f', fontWeight: 800, letterSpacing: 1.5, marginBottom: 10 }}>{node.date}</div>
                                    <div style={{ fontSize: 11, color: '#444', lineHeight: 1.4 }}>{node.detail.slice(0, 55)}...</div>
                                </button>
                            ))}
                        </div>
                    </section>

                    {/* Hovering/Floating Detail Panel */}
                    {selectedNode && (
                        <div
                            style={{
                                position: 'fixed',
                                bottom: 32,
                                left: '50%',
                                transform: 'translateX(-50%)',
                                width: 'calc(100% - 48px)',
                                maxWidth: 640,
                                background: '#0a0a0f',
                                border: `1px solid ${selectedNode.status === 'live' ? '#4fa' : '#88f'}`,
                                borderRadius: 28,
                                padding: '40px',
                                zIndex: 100,
                                boxShadow: '0 30px 100px rgba(0,0,0,0.9)',
                                animation: 'fadeIn 0.2s cubic-bezier(0, 0, 0.2, 1)',
                            }}
                        >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
                                <div>
                                    <div style={{ fontSize: 10, color: selectedNode.status === 'live' ? '#4fa' : '#88f', fontWeight: 900, letterSpacing: 3, marginBottom: 8, textTransform: 'uppercase' }}>
                                        {selectedNode.status === 'live' ? 'ACTIVE & DEFENSIBLE' : selectedNode.date}
                                    </div>
                                    <h3 style={{ fontSize: 32, fontWeight: 900, color: '#fff', margin: 0, letterSpacing: -1 }}>{selectedNode.label}</h3>
                                </div>
                                <button
                                    onClick={() => setSelected(null)}
                                    style={{ background: '#ffffff05', border: '1px solid #333', color: '#666', borderRadius: '50%', width: 40, height: 40, cursor: 'pointer', fontSize: 16, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                                >✕</button>
                            </div>

                            <p style={{ fontSize: 17, color: '#aaa', lineHeight: 1.8, margin: '0 0 32px 0' }}>{selectedNode.detail}</p>

                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                                <div style={{ padding: '20px', background: 'rgba(255,255,255,0.02)', borderRadius: 16 }}>
                                    <div style={{ fontSize: 10, color: '#555', fontWeight: 800, marginBottom: 6, letterSpacing: 1 }}>SPECIFICATION</div>
                                    <div style={{ fontSize: 13, color: '#888' }}>FSMA 204 Section 1.5</div>
                                </div>
                                <div style={{ padding: '20px', background: 'rgba(255,255,255,0.02)', borderRadius: 16 }}>
                                    <div style={{ fontSize: 10, color: '#555', fontWeight: 800, marginBottom: 6, letterSpacing: 1 }}>STATUS</div>
                                    <div style={{ fontSize: 13, color: selectedNode.status === 'live' ? '#4fa' : '#88f', fontWeight: 700 }}>
                                        {selectedNode.status === 'live' ? 'Defensible Verification' : 'Planned / Beta'}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    <footer style={{ padding: '60px 0', borderTop: '1px solid #111', textAlign: 'center' }}>
                        <p style={{ fontSize: 12, color: '#444', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 8 }}>
                            VERIFIED FOR COMPLIANCE. BUILT FOR PRECISION.
                        </p>
                        <p style={{ fontSize: 12, color: '#333', margin: 0 }}>
                            © 2026 RegEngine Infrastructure Division. All active capabilities verified for audit readiness.
                        </p>
                    </footer>
                </div>
            </div>
        </>
    );
}

export default function RegEngineArchitecture() {
    return (
        <Suspense>
            <RegEngineArchitectureContent />
        </Suspense>
    );
}
