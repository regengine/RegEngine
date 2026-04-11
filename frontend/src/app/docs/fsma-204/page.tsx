import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'FSMA 204 Developer Integration Guide | RegEngine',
  description: 'Build FDA-compliant traceability systems with RegEngine APIs. CTEs, KDEs, FDA Request Mode, supply chain tracing, and cryptographic verification.',
};
import { ArrowLeft, Utensils, CheckCircle, Clock, FileText, Zap, Shield, AlertTriangle, ExternalLink } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export default function FSMA204GuidePage() {
    return (
        <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
            {/* Header */}
            <div style={{
                borderBottom: `1px solid ${T.border}`,
                padding: '24px',
                background: 'linear-gradient(135deg, rgba(16,185,129,0.1) 0%, transparent 50%)',
            }}>
                <div className="max-w-[900px] mx-auto">
                    <Link
                        href="/docs"
                        style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '8px',
                            color: T.accent,
                            fontSize: '14px',
                            textDecoration: 'none',
                            marginBottom: '16px',
                        }}
                    >
                        <ArrowLeft className="w-4 h-4" />
                        Back to Docs
                    </Link>

                    <div className="flex items-center gap-3 mb-3">
                        <Utensils className="w-7 h-7 text-re-brand" />
                        <span style={{
                            background: T.accent,
                            color: 'white',
                            fontSize: '11px',
                            fontWeight: 600,
                            padding: '4px 10px',
                            borderRadius: '4px',
                            textTransform: 'uppercase',
                        }}>
                            Most Complete
                        </span>
                    </div>

                    <h1 className="text-[1.75rem] sm:text-[2.5rem] font-bold text-[var(--re-text-primary)] mb-2">
                        FSMA 204 Integration Guide
                    </h1>
                    <p style={{ color: T.textMuted, fontSize: '16px', maxWidth: '600px' }}>
                        Build FDA-compliant traceability systems with RegEngine&apos;s Food Safety APIs
                    </p>
                </div>
            </div>

            {/* Quick Stats Bar */}
            <div style={{
                background: T.surface,
                borderBottom: `1px solid ${T.border}`,
                padding: '16px 24px',
            }}>
                <div style={{ maxWidth: '900px', margin: '0 auto', display: 'flex', gap: '32px', flexWrap: 'wrap' }}>
                    <div className="flex items-center gap-2">
                        <Clock className="w-4 h-4 text-re-brand" />
                        <span className="text-sm text-re-text-secondary">24-hour FDA response</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <Shield className="w-4 h-4 text-re-brand" />
                        <span className="text-sm text-re-text-secondary">21 CFR 1.1455 compliant</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <CheckCircle className="w-4 h-4 text-re-brand" />
                        <span className="text-sm text-re-text-secondary">Enforcement: July 20, 2028</span>
                    </div>
                </div>
            </div>

            {/* Non-technical redirect */}
            <div style={{
                background: 'rgba(16,185,129,0.06)',
                borderBottom: `1px solid ${T.border}`,
                padding: '12px 24px',
            }}>
                <div style={{ maxWidth: '900px', margin: '0 auto', display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                    <span className="text-sm text-re-text-secondary">Not a developer?</span>
                    <Link
                        href="/fsma-204"
                        style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '6px',
                            color: T.accent,
                            fontSize: '14px',
                            fontWeight: 600,
                            textDecoration: 'none',
                        }}
                    >
                        Read the plain-English FSMA 204 guide →
                    </Link>
                </div>
            </div>

            {/* Content */}
            <div className="max-w-[900px] mx-auto py-12 px-6">

                {/* What is FSMA 204? */}
                <section className="mb-14">
                    <h2 className="text-[1.25rem] sm:text-2xl font-semibold text-[var(--re-text-primary)] mb-4">
                        What is FSMA 204?
                    </h2>
                    <p className="text-[var(--re-text-secondary)] leading-[1.7] mb-4">
                        The FDA Food Safety Modernization Act Section 204 (FSMA 204) requires companies handling foods on
                        the <strong className="text-re-text-primary">Food Traceability List (FTL)</strong> <a href="https://www.fda.gov/food/food-safety-modernization-act-fsma/food-traceability-list" target="_blank" rel="noopener noreferrer" className="text-xs text-re-text-muted hover:text-re-brand transition-colors align-super" title="FDA Food Traceability List">[FDA]</a> to maintain standardized
                        traceability records <a href="https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1320" target="_blank" rel="noopener noreferrer" className="text-xs text-re-text-muted hover:text-re-brand transition-colors align-super" title="21 CFR § 1.1320-1.1350 Requirement">[FDA]</a>. In a recall, you must provide the FDA with a sortable spreadsheet within
                        <strong className="text-re-text-primary"> 24 hours</strong> <a href="https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1455#p-1.1455(c)" target="_blank" rel="noopener noreferrer" className="text-xs text-re-text-muted hover:text-re-brand transition-colors align-super" title="21 CFR § 1.1455(c) Requirement">[FDA]</a>.
                    </p>

                    <div style={{
                        background: 'rgba(234,179,8,0.1)',
                        border: `1px solid rgba(234,179,8,0.3)`,
                        borderRadius: '8px',
                        padding: '16px 20px',
                    }}>
                        <div className="flex items-start gap-3">
                            <AlertTriangle style={{ width: 20, height: 20, color: 'var(--re-warning)', flexShrink: 0, marginTop: '2px' }} />
                            <div>
                                <p style={{ color: 'var(--re-text-primary)', fontWeight: 600, marginBottom: '4px' }}>Enforcement Delayed</p>
                                <p className="text-re-text-secondary text-sm m-0">
                                    The FDA announced an enforcement discretion period ending <strong>July 20, 2028</strong>.
                                    RegEngine auto-detected this regulatory change and updated all compliance facts.
                                </p>
                            </div>
                        </div>
                    </div>
                </section>

                {/* Quick Start */}
                <section className="mb-14">
                    <h2 className="text-[1.25rem] sm:text-2xl font-semibold text-[var(--re-text-primary)] mb-4">
                        Quick Start: Record a CTE
                    </h2>
                    <p className="text-[var(--re-text-secondary)] leading-[1.7] mb-4">
                        Critical Tracking Events (CTEs) are the building blocks of FSMA 204 compliance.
                        Here&apos;s how to record a receiving event:
                    </p>

                    {/* Code Block */}
                    <div style={{
                        background: 'rgba(0,0,0,0.6)',
                        borderRadius: '8px',
                        overflow: 'hidden',
                        border: `1px solid ${T.border}`,
                        marginBottom: '24px',
                    }}>
                        <div style={{
                            background: 'rgba(16,185,129,0.1)',
                            padding: '8px 16px',
                            borderBottom: `1px solid ${T.border}`,
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                        }}>
                            <span className="text-xs text-re-text-muted">POST /api/v1/webhooks/ingest</span>
                            <span className="text-xs text-re-brand">bash</span>
                        </div>
                        <pre style={{
                            padding: '20px',
                            margin: 0,
                            fontSize: '13px',
                            lineHeight: 1.6,
                            overflowX: 'auto',
                            color: 'var(--re-text-primary)',
                        }}>
                            <code>{`curl -X POST https://regengine.co/api/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: YOUR_API_KEY" \\
  -H "X-Tenant-ID: YOUR_TENANT_UUID" \\
  -H "Content-Type: application/json" \\
  -d '{
    "source": "erp",
    "events": [
      {
        "cte_type": "receiving",
        "traceability_lot_code": "00012345678901-LOT-2026-001",
        "product_description": "Romaine Lettuce",
        "quantity": 500,
        "unit_of_measure": "cases",
        "location_name": "Distribution Center #4",
        "timestamp": "2026-02-05T08:30:00Z",
        "kdes": {
          "receive_date": "2026-02-05",
          "receiving_location": "Distribution Center #4",
          "ship_from_location": "Valley Fresh Farms"
        }
      }
    ]
  }'`}</code>
                        </pre>
                    </div>

                    {/* Response */}
                    <div style={{
                        background: 'rgba(0,0,0,0.4)',
                        borderRadius: '8px',
                        overflow: 'hidden',
                        border: `1px solid ${T.border}`,
                    }}>
                        <div style={{
                            background: 'rgba(16,185,129,0.15)',
                            padding: '8px 16px',
                            borderBottom: `1px solid ${T.border}`,
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                        }}>
                            <div className="w-2 h-2 rounded-full bg-re-brand" />
                            <span className="text-xs text-re-brand">201 Created</span>
                        </div>
                        <pre className="p-3 sm:p-[16px_20px] m-0 text-[12px] sm:text-[13px] leading-[1.5] text-[var(--re-text-tertiary)]">
                            <code>{`{
  "accepted": 1,
  "rejected": 0,
  "total": 1,
  "events": [
    {
      "traceability_lot_code": "00012345678901-LOT-2026-001",
      "cte_type": "receiving",
      "status": "accepted",
      "event_id": "a1b2c3d4-...",
      "sha256_hash": "a3f2b891c4d5e6f7...",
      "chain_hash": "7f6e5d4c3b2a1908..."
    }
  ],
  "ingestion_timestamp": "2026-02-05T08:30:01Z"
}`}</code>
                        </pre>
                    </div>
                </section>

                {/* CTEs and KDEs */}
                <section className="mb-14">
                    <h2 className="text-[1.25rem] sm:text-2xl font-semibold text-[var(--re-text-primary)] mb-4">
                        Critical Tracking Events (CTEs)
                    </h2>
                    <p style={{ color: T.text, lineHeight: 1.7, marginBottom: '24px' }}>
                        FSMA 204 defines specific events that must be recorded at each point in the supply chain:
                    </p>

                    <div style={{
                        background: T.surface,
                        border: `1px solid ${T.border}`,
                        borderRadius: '8px',
                        overflowX: 'auto',
                    }}>
                        <table className="w-full border-collapse">
                            <thead>
                                <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                                    <th className="text-left px-4 py-3 text-re-text-muted text-xs font-semibold">CTE</th>
                                    <th className="text-left px-4 py-3 text-re-text-muted text-xs font-semibold">event_type</th>
                                    <th className="text-left px-4 py-3 text-re-text-muted text-xs font-semibold">Required KDEs</th>
                                </tr>
                            </thead>
                            <tbody>
                                {[
                                    { cte: 'Harvesting', event: 'harvesting', kdes: 'Location, Harvest Date, Lot Code, Product' },
                                    { cte: 'Cooling', event: 'cooling', kdes: 'Location, Cooling Date, Lot Code, Product' },
                                    { cte: 'Initial Packing', event: 'initial_packing', kdes: 'Location, Pack Date, TLC, Quantity' },
                                    { cte: 'Shipping', event: 'shipping', kdes: 'Ship From/To, TLC, Carrier, Date' },
                                    { cte: 'Receiving', event: 'receiving', kdes: 'Location, TLC, Source, Quantity, Date' },
                                    { cte: 'Transformation', event: 'transformation', kdes: 'Input TLCs, Output TLC, Date, Location' },
                                ].map((row, i, arr) => (
                                    <tr key={row.event} style={{ borderBottom: i < arr.length - 1 ? `1px solid ${T.border}` : 'none' }}>
                                        <td className="px-4 py-3 text-re-text-primary font-medium">{row.cte}</td>
                                        <td className="px-4 py-3">
                                            <code style={{
                                                background: 'rgba(16,185,129,0.2)',
                                                color: T.accent,
                                                padding: '4px 8px',
                                                borderRadius: '4px',
                                                fontSize: '12px',
                                            }}>{row.event}</code>
                                        </td>
                                        <td className="px-4 py-3 text-re-text-secondary text-sm">{row.kdes}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </section>

                {/* FDA Request Mode */}
                <section className="mb-14">
                    <h2 className="text-[1.25rem] sm:text-2xl font-semibold text-[var(--re-text-primary)] mb-4">
                        FDA Request Mode
                    </h2>
                    <p className="text-[var(--re-text-secondary)] leading-[1.7] mb-4">
                        When the FDA requests traceability data during a recall, you have <strong className="text-re-text-primary">24 hours</strong> <a href="https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1455#p-1.1455(c)" target="_blank" rel="noopener noreferrer" className="text-xs text-re-text-muted hover:text-re-brand transition-colors align-super" title="21 CFR § 1.1455(c) Requirement">[FDA]</a> to
                        provide an electronic sortable spreadsheet per 21 CFR 1.1455(c). RegEngine generates this with one API call:
                    </p>

                    <div style={{
                        background: 'rgba(0,0,0,0.6)',
                        borderRadius: '8px',
                        overflow: 'hidden',
                        border: `1px solid ${T.border}`,
                        marginBottom: '24px',
                    }}>
                        <div style={{
                            background: 'rgba(255,255,255,0.05)',
                            padding: '8px 16px',
                            borderBottom: `1px solid ${T.border}`,
                        }}>
                            <span className="text-xs text-re-text-muted">GET /v1/fsma/export/fda-request</span>
                        </div>
                        <pre style={{
                            padding: '20px',
                            margin: 0,
                            fontSize: '13px',
                            lineHeight: 1.6,
                            overflowX: 'auto',
                            color: 'var(--re-text-primary)',
                        }}>
                            <code>{`curl https://regengine.co/v1/fsma/export/fda-request \\
  -H "X-RegEngine-API-Key: YOUR_API_KEY" \\
  -H "X-Tenant-ID: YOUR_TENANT_UUID" \\
  -G \\
  -d "start_date=2026-01-01" \\
  -d "end_date=2026-02-05" \\
  -o fda_response.csv`}</code>
                        </pre>
                    </div>

                    <p className="text-[var(--re-text-secondary)] leading-[1.7] mb-4">
                        The export contains the FDA-mandated 11-column format:
                    </p>

                    <div style={{
                        background: 'rgba(0,0,0,0.4)',
                        padding: '16px 20px',
                        borderRadius: '8px',
                        border: `1px solid ${T.border}`,
                        fontSize: '13px',
                        fontFamily: T.fontMono,
                        color: 'var(--re-text-tertiary)',
                        overflowX: 'auto',
                    }}>
                        <code>Traceability Lot Code, Traceability Lot Code Description, Product Description, Quantity, Unit of Measure, Location Description, Location Identifier (GLN), Date, Time, Reference Document Type, Reference Document Number</code>
                    </div>
                </section>

                {/* Supply Chain Tracing */}
                <section className="mb-14">
                    <h2 className="text-[1.25rem] sm:text-2xl font-semibold text-[var(--re-text-primary)] mb-4">
                        Supply Chain Tracing
                    </h2>
                    <p className="text-[var(--re-text-secondary)] leading-[1.7] mb-4">
                        RegEngine uses a graph database to trace products forward and backward through your supply chain:
                    </p>

                    {/* Forward Trace */}
                    <div style={{
                        background: 'rgba(0,0,0,0.6)',
                        borderRadius: '8px',
                        overflow: 'hidden',
                        border: `1px solid ${T.border}`,
                        marginBottom: '16px',
                    }}>
                        <div style={{
                            background: 'rgba(255,255,255,0.05)',
                            padding: '8px 16px',
                            borderBottom: `1px solid ${T.border}`,
                        }}>
                            <span className="text-xs text-re-text-muted">Forward Trace (where did this lot go?)</span>
                        </div>
                        <pre className="p-3 sm:p-[16px_20px] m-0 text-[12px] sm:text-[13px] leading-[1.5] text-[var(--re-text-tertiary)]">
                            <code>{`GET /v1/fsma/trace/forward/LOT-2026-001`}</code>
                        </pre>
                    </div>

                    {/* Backward Trace */}
                    <div style={{
                        background: 'rgba(0,0,0,0.6)',
                        borderRadius: '8px',
                        overflow: 'hidden',
                        border: `1px solid ${T.border}`,
                    }}>
                        <div style={{
                            background: 'rgba(255,255,255,0.05)',
                            padding: '8px 16px',
                            borderBottom: `1px solid ${T.border}`,
                        }}>
                            <span className="text-xs text-re-text-muted">Backward Trace (where did this lot come from?)</span>
                        </div>
                        <pre className="p-3 sm:p-[16px_20px] m-0 text-[12px] sm:text-[13px] leading-[1.5] text-[var(--re-text-tertiary)]">
                            <code>{`GET /v1/fsma/trace/backward/LOT-2026-001`}</code>
                        </pre>
                    </div>
                </section>

                {/* Verify Don't Trust */}
                <section className="mb-14">
                    <h2 className="text-[1.25rem] sm:text-2xl font-semibold text-[var(--re-text-primary)] mb-4">
                        Verify, Don&apos;t Trust
                    </h2>
                    <p className="text-[var(--re-text-secondary)] leading-[1.7] mb-4">
                        Every compliance record is cryptographically hashed. You can independently verify the integrity
                        of your data without database access:
                    </p>

                    <div style={{
                        background: 'rgba(0,0,0,0.6)',
                        borderRadius: '8px',
                        overflow: 'hidden',
                        border: `1px solid ${T.border}`,
                    }}>
                        <div style={{
                            background: 'rgba(255,255,255,0.05)',
                            padding: '8px 16px',
                            borderBottom: `1px solid ${T.border}`,
                        }}>
                            <span className="text-xs text-re-text-muted">Independent Verification</span>
                        </div>
                        <pre className="p-3 sm:p-[16px_20px] m-0 text-[12px] sm:text-[13px] leading-[1.5] text-[var(--re-text-tertiary)]">
                            <code>{`python verify_chain.py --audit
# ✓ Chain integrity verified
# ✓ 1847 records validated
# ✓ No hash mismatches detected`}</code>
                        </pre>
                    </div>
                </section>

                {/* API Reference Links */}
                <section className="mb-12">
                    <h2 className="text-[1.25rem] sm:text-2xl font-semibold text-[var(--re-text-primary)] mb-4">
                        Related Endpoints
                    </h2>

                    <div className="grid gap-3">
                        {[
                            { path: 'POST /api/v1/webhooks/ingest', desc: 'Create compliance events' },
                            { path: 'GET /v1/fsma/export/fda-request', desc: 'Generate FDA-compliant export' },
                            { path: 'GET /v1/fsma/trace/forward/{tlc}', desc: 'Forward supply chain trace' },
                            { path: 'GET /v1/fsma/trace/backward/{tlc}', desc: 'Backward supply chain trace' },
                            { path: 'GET /v1/fsma/coverage', desc: 'Coverage status and freshness' },
                        ].map((ep) => (
                            <div key={ep.path} style={{
                                padding: '12px 16px',
                                background: T.surface,
                                borderRadius: '6px',
                                border: `1px solid ${T.border}`,
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                            }}>
                                <code style={{ fontSize: '13px', color: T.accent }}>{ep.path}</code>
                                <span className="text-[13px] text-re-text-muted">{ep.desc}</span>
                            </div>
                        ))}
                    </div>
                </section>

                {/* Next Steps */}
                <div style={{
                    background: T.surface,
                    border: `1px solid ${T.border}`,
                    borderRadius: '8px',
                    padding: '24px',
                }}>
                    <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '16px' }}>
                        Next Steps
                    </h3>
                    <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                        <Link
                            href="/developer/register"
                            style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '8px',
                                background: T.accent,
                                color: 'white',
                                padding: '10px 20px',
                                borderRadius: '6px',
                                fontWeight: 600,
                                fontSize: '14px',
                                textDecoration: 'none',
                            }}
                        >
                            <Zap className="w-4 h-4" />
                            Get Developer Access
                        </Link>
                        <Link
                            href="/developer/register"
                            style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '8px',
                                background: 'rgba(255,255,255,0.1)',
                                color: 'var(--re-text-primary)',
                                padding: '10px 20px',
                                borderRadius: '6px',
                                fontWeight: 600,
                                fontSize: '14px',
                                textDecoration: 'none',
                                border: `1px solid ${T.border}`,
                            }}
                        >
                            Full API Reference →
                        </Link>
                        <Link
                            href="/tools/ftl-checker"
                            style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '8px',
                                background: 'rgba(255,255,255,0.1)',
                                color: 'var(--re-text-primary)',
                                padding: '10px 20px',
                                borderRadius: '6px',
                                fontWeight: 600,
                                fontSize: '14px',
                                textDecoration: 'none',
                                border: `1px solid ${T.border}`,
                            }}
                        >
                            <ExternalLink className="w-4 h-4" />
                            FTL Checker Tool
                        </Link>
                    </div>
                </div>

            </div>
        </div>
    );
}
