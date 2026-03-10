import Link from 'next/link';
import { ArrowLeft, FileText } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export default function ChangelogPage() {
    return (
        <div className="re-page">
            {/* Header */}
            <div style={{
                borderBottom: `1px solid ${T.border}`,
                padding: '24px',
            }}>
                <div className="max-w-[700px] mx-auto">
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
                        <FileText className="w-7 h-7 text-re-brand" />
                    </div>

                    <h1 className="re-heading-xl">
                        Changelog
                    </h1>
                    <p className="text-re-text-muted text-base">
                        Latest updates and improvements to RegEngine
                    </p>
                </div>
            </div>

            {/* Content */}
            <div className="re-page-narrow">

                {/* v1.2.0 — Phase 4: Accessibility Polish */}
                <section className="mb-12">
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
                            v1.2.0
                        </span>
                        <span style={{ color: T.textMuted, fontSize: '14px' }}>March 4, 2026</span>
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

                    <h2 className="re-heading-md">
                        Accessibility Polish — WCAG 2.1 AA
                    </h2>

                    <div className="mb-6">
                        <h4 style={{
                            fontSize: '12px',
                            fontWeight: 600,
                            color: T.textMuted,
                            textTransform: 'uppercase',
                            letterSpacing: '0.5px',
                            marginBottom: '12px',
                        }}>
                            ♿ Accessibility
                        </h4>
                        <ul style={{ margin: 0, paddingLeft: '20px', color: T.text, lineHeight: 1.8 }}>
                            <li>Skip-to-content link and ARIA landmark labels on all pages</li>
                            <li>Keyboard-accessible Free Tools dropdown with Escape/ArrowDown navigation</li>
                            <li>Pricing cards now use radio-group semantics with full keyboard support</li>
                            <li>Developer portal tabs upgraded to WAI-ARIA tablist/tab/tabpanel with arrow-key navigation</li>
                            <li><code>prefers-reduced-motion</code> support across all CSS transitions and Framer Motion animations</li>
                            <li>Touch targets increased to WCAG-compliant 44px minimum</li>
                            <li>Heading hierarchy audit and decorative emoji <code>aria-hidden</code> cleanup</li>
                        </ul>
                    </div>
                </section>

                {/* v1.1.0 — Phase 3: Onboarding UX Redesign */}
                <section className="mb-12">
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
                            v1.1.0
                        </span>
                        <span style={{ color: T.textMuted, fontSize: '14px' }}>March 4, 2026</span>
                    </div>

                    <h2 className="re-heading-md">
                        Onboarding UX Redesign
                    </h2>

                    <div className="mb-6">
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
                            <li>New onboarding hub with two-path entry: guided wizard and bulk CSV upload</li>
                            <li>Supplier wizard migrated to dark theme using design tokens</li>
                            <li>Bulk upload page migrated to dark theme for site-wide consistency</li>
                            <li>Onboarding navigation shell with progress indicator and exit-to-home</li>
                            <li>Cross-linking between marketing site, onboarding flow, and dashboard</li>
                        </ul>
                    </div>
                </section>

                {/* v1.0.0 — Initial Public Release */}
                <section className="mb-12">
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
                    </div>

                    <h2 className="re-heading-md">
                        Initial Public Release
                    </h2>

                    <div className="mb-6">
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

                    <div className="mb-6">
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

            </div>
        </div>
    );
}
