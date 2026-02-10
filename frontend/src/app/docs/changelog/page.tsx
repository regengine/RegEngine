import Link from 'next/link';
import { ArrowLeft, FileText, CheckCircle, Clock, Zap } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export default function ChangelogPage() {
    return (
        <div style={{ minHeight: '100vh', background: T.bg, color: T.text, fontFamily: T.fontSans }}>
            {/* Header */}
            <div style={{
                borderBottom: `1px solid ${T.border}`,
                padding: '24px',
            }}>
                <div style={{ maxWidth: '700px', margin: '0 auto' }}>
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
                        <FileText style={{ width: 28, height: 28, color: T.accent }} />
                    </div>

                    <h1 style={{ fontSize: '2.5rem', fontWeight: 700, color: 'var(--re-text-primary)', marginBottom: '8px' }}>
                        Changelog
                    </h1>
                    <p style={{ color: T.textMuted, fontSize: '16px' }}>
                        Latest updates and improvements to RegEngine
                    </p>
                </div>
            </div>

            {/* Content */}
            <div style={{ maxWidth: '700px', margin: '0 auto', padding: '48px 24px' }}>

                {/* Latest Release */}
                <section style={{ marginBottom: '48px' }}>
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '12px',
                        marginBottom: '20px',
                        paddingBottom: '16px',
                        borderBottom: `1px solid ${T.border}`,
                    }}>
                        <span style={{
                            background: T.accent,
                            color: 'white',
                            fontSize: '12px',
                            fontWeight: 600,
                            padding: '4px 10px',
                            borderRadius: '4px',
                        }}>
                            v1.0.0
                        </span>
                        <span style={{ color: T.textMuted, fontSize: '14px' }}>February 5, 2026</span>
                        <span style={{
                            background: 'rgba(16,185,129,0.2)',
                            color: T.accent,
                            fontSize: '11px',
                            fontWeight: 600,
                            padding: '2px 8px',
                            borderRadius: '4px',
                        }}>
                            Latest
                        </span>
                    </div>

                    <h2 style={{ fontSize: '1.3rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '16px' }}>
                        Initial Public Release
                    </h2>

                    <div style={{ marginBottom: '24px' }}>
                        <h4 style={{
                            fontSize: '12px',
                            fontWeight: 600,
                            color: T.textMuted,
                            textTransform: 'uppercase',
                            letterSpacing: '0.5px',
                            marginBottom: '12px',
                        }}>
                            ✨ Features
                        </h4>
                        <ul style={{ margin: 0, paddingLeft: '20px', color: T.text, lineHeight: 1.8 }}>
                            <li>FSMA 204 compliance module with CTEs and KDEs</li>
                            <li>FDA Request Mode for 24-hour export compliance</li>
                            <li>Graph-based supply chain tracing (forward/backward)</li>
                            <li>Cryptographic record hashing for tamper evidence</li>
                            <li>FTL Checker tool for Food Traceability List verification</li>
                        </ul>
                    </div>

                    <div style={{ marginBottom: '24px' }}>
                        <h4 style={{
                            fontSize: '12px',
                            fontWeight: 600,
                            color: T.textMuted,
                            textTransform: 'uppercase',
                            letterSpacing: '0.5px',
                            marginBottom: '12px',
                        }}>
                            📚 Documentation
                        </h4>
                        <ul style={{ margin: 0, paddingLeft: '20px', color: T.text, lineHeight: 1.8 }}>
                            <li>API Reference with all endpoints</li>
                            <li>FSMA 204 Integration Guide</li>
                            <li>Quickstart tutorial</li>
                            <li>Authentication guide</li>
                            <li>Error codes reference</li>
                        </ul>
                    </div>
                </section>

                {/* Roadmap Preview */}
                <section style={{
                    background: T.surface,
                    border: `1px solid ${T.border}`,
                    borderRadius: '8px',
                    padding: '24px',
                }}>
                    <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '16px' }}>
                        <Clock style={{ width: 18, height: 18, display: 'inline', verticalAlign: 'middle', marginRight: '8px' }} />
                        Coming Next
                    </h3>

                    <div style={{ display: 'grid', gap: '12px' }}>
                        {[
                            { item: 'Python & Node.js SDKs', quarter: 'Q2 2026' },
                            { item: 'Webhook notifications', quarter: 'Q2 2026' },
                            { item: 'Finance vertical (SOX 404, SEC)', quarter: 'Q2 2026' },
                            { item: 'Energy vertical (NERC CIP-013)', quarter: 'Q2 2026' },
                        ].map((item) => (
                            <div key={item.item} style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                padding: '8px 0',
                                borderBottom: `1px solid ${T.border}`,
                            }}>
                                <span style={{ color: T.text, fontSize: '14px' }}>{item.item}</span>
                                <span style={{ color: T.textMuted, fontSize: '12px' }}>{item.quarter}</span>
                            </div>
                        ))}
                    </div>
                </section>
            </div>
        </div>
    );
}
