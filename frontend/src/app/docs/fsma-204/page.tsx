import Link from 'next/link';
import { ArrowLeft, Utensils, CheckCircle, Clock, FileText, Zap, Shield, AlertTriangle, ExternalLink } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export default function FSMA204GuidePage() {
    return (
        <div style={{ minHeight: '100vh', background: T.bg, color: T.text, fontFamily: T.fontSans }}>
            {/* Header */}
            <div style={{
                borderBottom: `1px solid ${T.border}`,
                padding: '24px',
                background: 'linear-gradient(135deg, rgba(16,185,129,0.1) 0%, transparent 50%)',
            }}>
                <div style={{ maxWidth: '900px', margin: '0 auto' }}>
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
                        <ArrowLeft style={{ width: 16, height: 16 }} />
                        Back to Docs
                    </Link>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                        <Utensils style={{ width: 28, height: 28, color: T.accent }} />
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

                    <h1 style={{ fontSize: '2.5rem', fontWeight: 700, color: '#ffffff', marginBottom: '8px' }}>
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
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Clock style={{ width: 16, height: 16, color: T.accent }} />
                        <span style={{ fontSize: '14px', color: T.text }}>24-hour FDA response</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Shield style={{ width: 16, height: 16, color: T.accent }} />
                        <span style={{ fontSize: '14px', color: T.text }}>21 CFR 1.1455 compliant</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <CheckCircle style={{ width: 16, height: 16, color: T.accent }} />
                        <span style={{ fontSize: '14px', color: T.text }}>Enforcement: July 20, 2028</span>
                    </div>
                </div>
            </div>

            {/* Content */}
            <div style={{ maxWidth: '900px', margin: '0 auto', padding: '48px 24px' }}>

                {/* What is FSMA 204? */}
                <section style={{ marginBottom: '56px' }}>
                    <h2 style={{ fontSize: '1.5rem', fontWeight: 600, color: '#ffffff', marginBottom: '16px' }}>
                        What is FSMA 204?
                    </h2>
                    <p style={{ color: T.text, lineHeight: 1.7, marginBottom: '16px' }}>
                        The FDA Food Safety Modernization Act Section 204 (FSMA 204) requires companies handling foods on
                        the <strong style={{ color: '#ffffff' }}>Food Traceability List (FTL)</strong> to maintain standardized
                        traceability records. In a recall, you must provide the FDA with a sortable spreadsheet within
                        <strong style={{ color: '#ffffff' }}> 24 hours</strong>.
                    </p>

                    <div style={{
                        background: 'rgba(234,179,8,0.1)',
                        border: `1px solid rgba(234,179,8,0.3)`,
                        borderRadius: '8px',
                        padding: '16px 20px',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                            <AlertTriangle style={{ width: 20, height: 20, color: '#eab308', flexShrink: 0, marginTop: '2px' }} />
                            <div>
                                <p style={{ color: '#ffffff', fontWeight: 600, marginBottom: '4px' }}>Enforcement Delayed</p>
                                <p style={{ color: T.text, fontSize: '14px', margin: 0 }}>
                                    The FDA announced an enforcement discretion period ending <strong>July 20, 2028</strong>.
                                    RegEngine auto-detected this regulatory change and updated all compliance facts.
                                </p>
                            </div>
                        </div>
                    </div>
                </section>

                {/* Quick Start */}
                <section style={{ marginBottom: '56px' }}>
                    <h2 style={{ fontSize: '1.5rem', fontWeight: 600, color: '#ffffff', marginBottom: '16px' }}>
                        Quick Start: Record a CTE
                    </h2>
                    <p style={{ color: T.text, lineHeight: 1.7, marginBottom: '16px' }}>
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
                            <span style={{ fontSize: '12px', color: T.textMuted }}>POST /v1/records</span>
                            <span style={{ fontSize: '12px', color: T.accent }}>bash</span>
                        </div>
                        <pre style={{
                            padding: '20px',
                            margin: 0,
                            fontSize: '13px',
                            lineHeight: 1.6,
                            overflowX: 'auto',
                            color: '#e2e8f0',
                        }}>
                            <code>{`curl -X POST https://api.regengine.co/v1/records \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "type": "compliance_event",
    "framework": "FSMA_204",
    "data": {
      "event_type": "receiving",
      "lot_code": "LOT-2026-001",
      "product": "Romaine Lettuce",
      "quantity": 500,
      "unit": "cases",
      "location": {
        "name": "Distribution Center #4",
        "fda_traceability_lot_code": "TLC-DC4-2026"
      },
      "source": {
        "name": "Valley Fresh Farms",
        "lot_code": "VFF-2026-0142"
      },
      "timestamp": "2026-02-05T08:30:00Z"
    }
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
                            <div style={{ width: 8, height: 8, borderRadius: '50%', background: T.accent }} />
                            <span style={{ fontSize: '12px', color: T.accent }}>201 Created</span>
                        </div>
                        <pre style={{ padding: '16px 20px', margin: 0, fontSize: '13px', lineHeight: 1.5, color: '#94a3b8' }}>
                            <code>{`{
  "id": "rec_3x7Kp9mN2vL",
  "record_hash": "a3f2b891c4d5e6f78901a2b3c4d5e6f7...",
  "prev_hash": "7f6e5d4c3b2a19087f6e5d4c3b2a1908...",
  "chain_position": 1847,
  "created_at": "2026-02-05T08:30:01Z",
  "signature": "MEUCIQC7...base64...==",
  "public_key_id": "regengine-prod-2026-02"
}`}</code>
                        </pre>
                    </div>
                </section>

                {/* CTEs and KDEs */}
                <section style={{ marginBottom: '56px' }}>
                    <h2 style={{ fontSize: '1.5rem', fontWeight: 600, color: '#ffffff', marginBottom: '16px' }}>
                        Critical Tracking Events (CTEs)
                    </h2>
                    <p style={{ color: T.text, lineHeight: 1.7, marginBottom: '24px' }}>
                        FSMA 204 defines specific events that must be recorded at each point in the supply chain:
                    </p>

                    <div style={{
                        background: T.surface,
                        border: `1px solid ${T.border}`,
                        borderRadius: '8px',
                        overflow: 'hidden',
                    }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                                    <th style={{ textAlign: 'left', padding: '12px 16px', color: T.textMuted, fontSize: '12px', fontWeight: 600 }}>CTE</th>
                                    <th style={{ textAlign: 'left', padding: '12px 16px', color: T.textMuted, fontSize: '12px', fontWeight: 600 }}>event_type</th>
                                    <th style={{ textAlign: 'left', padding: '12px 16px', color: T.textMuted, fontSize: '12px', fontWeight: 600 }}>Required KDEs</th>
                                </tr>
                            </thead>
                            <tbody>
                                {[
                                    { cte: 'Harvesting', event: 'harvesting', kdes: 'Location, Harvest Date, Lot Code, Product' },
                                    { cte: 'Cooling', event: 'cooling', kdes: 'Location, Cooling Date, Lot Code, Product' },
                                    { cte: 'Initial Packing', event: 'packing', kdes: 'Location, Pack Date, TLC, Quantity' },
                                    { cte: 'Shipping', event: 'shipping', kdes: 'Ship From/To, TLC, Carrier, Date' },
                                    { cte: 'Receiving', event: 'receiving', kdes: 'Location, TLC, Source, Quantity, Date' },
                                    { cte: 'Transformation', event: 'transformation', kdes: 'Input TLCs, Output TLC, Date, Location' },
                                ].map((row, i, arr) => (
                                    <tr key={row.event} style={{ borderBottom: i < arr.length - 1 ? `1px solid ${T.border}` : 'none' }}>
                                        <td style={{ padding: '12px 16px', color: '#ffffff', fontWeight: 500 }}>{row.cte}</td>
                                        <td style={{ padding: '12px 16px' }}>
                                            <code style={{
                                                background: 'rgba(16,185,129,0.2)',
                                                color: T.accent,
                                                padding: '4px 8px',
                                                borderRadius: '4px',
                                                fontSize: '12px',
                                            }}>{row.event}</code>
                                        </td>
                                        <td style={{ padding: '12px 16px', color: T.text, fontSize: '14px' }}>{row.kdes}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </section>

                {/* FDA Request Mode */}
                <section style={{ marginBottom: '56px' }}>
                    <h2 style={{ fontSize: '1.5rem', fontWeight: 600, color: '#ffffff', marginBottom: '16px' }}>
                        FDA Request Mode
                    </h2>
                    <p style={{ color: T.text, lineHeight: 1.7, marginBottom: '16px' }}>
                        When the FDA requests traceability data during a recall, you have <strong style={{ color: '#ffffff' }}>24 hours</strong> to
                        provide an electronic sortable spreadsheet per 21 CFR 1.1455(b)(3). RegEngine generates this with one API call:
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
                            <span style={{ fontSize: '12px', color: T.textMuted }}>GET /fsma/v1/export/fda-request</span>
                        </div>
                        <pre style={{
                            padding: '20px',
                            margin: 0,
                            fontSize: '13px',
                            lineHeight: 1.6,
                            overflowX: 'auto',
                            color: '#e2e8f0',
                        }}>
                            <code>{`curl https://api.regengine.co/fsma/v1/export/fda-request \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -G \\
  -d "start_date=2026-01-01" \\
  -d "end_date=2026-02-05" \\
  -d "lot_code=LOT-2026-001" \\
  -o fda_response.csv`}</code>
                        </pre>
                    </div>

                    <p style={{ color: T.text, lineHeight: 1.7, marginBottom: '16px' }}>
                        The export contains the FDA-mandated 11-column format:
                    </p>

                    <div style={{
                        background: 'rgba(0,0,0,0.4)',
                        padding: '16px 20px',
                        borderRadius: '8px',
                        border: `1px solid ${T.border}`,
                        fontSize: '13px',
                        fontFamily: T.fontMono,
                        color: '#94a3b8',
                        overflowX: 'auto',
                    }}>
                        <code>Entry #, Event Type, Event Date, Product, TLC, Quantity, Unit, Location, Source, Destination, Reference Doc URL</code>
                    </div>
                </section>

                {/* Supply Chain Tracing */}
                <section style={{ marginBottom: '56px' }}>
                    <h2 style={{ fontSize: '1.5rem', fontWeight: 600, color: '#ffffff', marginBottom: '16px' }}>
                        Supply Chain Tracing
                    </h2>
                    <p style={{ color: T.text, lineHeight: 1.7, marginBottom: '16px' }}>
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
                            <span style={{ fontSize: '12px', color: T.textMuted }}>Forward Trace (where did this lot go?)</span>
                        </div>
                        <pre style={{ padding: '16px 20px', margin: 0, fontSize: '13px', lineHeight: 1.5, color: '#94a3b8' }}>
                            <code>{`GET /graph/v1/trace/forward?lot_code=LOT-2026-001`}</code>
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
                            <span style={{ fontSize: '12px', color: T.textMuted }}>Backward Trace (where did this lot come from?)</span>
                        </div>
                        <pre style={{ padding: '16px 20px', margin: 0, fontSize: '13px', lineHeight: 1.5, color: '#94a3b8' }}>
                            <code>{`GET /graph/v1/trace/backward?lot_code=LOT-2026-001`}</code>
                        </pre>
                    </div>
                </section>

                {/* Verify Don't Trust */}
                <section style={{ marginBottom: '56px' }}>
                    <h2 style={{ fontSize: '1.5rem', fontWeight: 600, color: '#ffffff', marginBottom: '16px' }}>
                        Verify, Don&apos;t Trust
                    </h2>
                    <p style={{ color: T.text, lineHeight: 1.7, marginBottom: '16px' }}>
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
                            <span style={{ fontSize: '12px', color: T.textMuted }}>Independent Verification</span>
                        </div>
                        <pre style={{ padding: '16px 20px', margin: 0, fontSize: '13px', lineHeight: 1.5, color: '#94a3b8' }}>
                            <code>{`python verify_chain.py --audit
# ✓ Chain integrity verified
# ✓ 1847 records validated
# ✓ No hash mismatches detected`}</code>
                        </pre>
                    </div>
                </section>

                {/* API Reference Links */}
                <section style={{ marginBottom: '48px' }}>
                    <h2 style={{ fontSize: '1.5rem', fontWeight: 600, color: '#ffffff', marginBottom: '16px' }}>
                        Related Endpoints
                    </h2>

                    <div style={{ display: 'grid', gap: '12px' }}>
                        {[
                            { path: 'POST /v1/records', desc: 'Create compliance events' },
                            { path: 'GET /fsma/v1/export/fda-request', desc: 'Generate FDA-compliant export' },
                            { path: 'GET /graph/v1/trace/forward', desc: 'Forward supply chain trace' },
                            { path: 'GET /graph/v1/trace/backward', desc: 'Backward supply chain trace' },
                            { path: 'GET /compliance/coverage', desc: 'Coverage status and freshness' },
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
                                <span style={{ fontSize: '13px', color: T.textMuted }}>{ep.desc}</span>
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
                    <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#ffffff', marginBottom: '16px' }}>
                        Next Steps
                    </h3>
                    <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                        <Link
                            href="/api-keys"
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
                            <Zap style={{ width: 16, height: 16 }} />
                            Get API Key
                        </Link>
                        <Link
                            href="/docs/api"
                            style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '8px',
                                background: 'rgba(255,255,255,0.1)',
                                color: '#ffffff',
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
                            href="/ftl-checker"
                            style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '8px',
                                background: 'rgba(255,255,255,0.1)',
                                color: '#ffffff',
                                padding: '10px 20px',
                                borderRadius: '6px',
                                fontWeight: 600,
                                fontSize: '14px',
                                textDecoration: 'none',
                                border: `1px solid ${T.border}`,
                            }}
                        >
                            <ExternalLink style={{ width: 16, height: 16 }} />
                            FTL Checker Tool
                        </Link>
                    </div>
                </div>

            </div>
        </div>
    );
}
