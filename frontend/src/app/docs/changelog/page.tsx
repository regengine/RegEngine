import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowLeft, FileText } from 'lucide-react';
import { T as _T } from '@/lib/design-tokens';

export const metadata: Metadata = {
    title: 'Changelog | RegEngine',
    description:
        'Latest RegEngine product updates, API improvements, and FSMA 204 compliance workflow releases.',
};

const T = {
  ..._T,
  heading: 'var(--re-text-primary)',
  text: 'var(--re-text-secondary)',
  textMuted: 'var(--re-text-muted)',
  textDim: 'var(--re-text-muted)',
  surface: 'var(--re-surface-card)',
  border: 'var(--re-surface-border)',
};

export default function ChangelogPage() {
    return (
        <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
            {/* Header */}
            <div className="p-6" style={{ borderBottom: `1px solid ${T.border}` }}>
                <div className="max-w-[700px] mx-auto">
                    <Link
                        href="/docs"
                        className="inline-flex items-center gap-2 text-sm no-underline mb-4"
                        style={{ color: T.accent }}
                    >
                        <ArrowLeft className="w-4 h-4" />
                        Back to Docs
                    </Link>

                    <div className="flex items-center gap-3 mb-3">
                        <FileText className="w-7 h-7 text-re-brand" />
                    </div>

                    <h1 className="text-[1.75rem] sm:text-[2.5rem] font-bold text-[var(--re-text-primary)] mb-2">
                        Changelog
                    </h1>
                    <p className="text-re-text-muted text-base">
                        Latest updates and improvements to RegEngine
                    </p>
                </div>
            </div>

            {/* Content */}
            <div className="max-w-[700px] mx-auto py-12 px-6">

                {/* v1.2.0 — Phase 4: Accessibility Polish */}
                <section className="mb-12">
                    <div className="flex items-center gap-3 mb-5 pb-4" style={{ borderBottom: `1px solid ${T.border}` }}>
                        <span className="text-white text-xs font-semibold px-2.5 py-1 rounded" style={{ background: T.accent }}>
                            v1.2.0
                        </span>
                        <span className="text-sm" style={{ color: T.textMuted }}>March 4, 2026</span>
                        <span className="bg-[rgba(16,185,129,0.2)] text-[11px] font-semibold px-2 py-0.5 rounded" style={{ color: T.accent }}>
                            Latest
                        </span>
                    </div>

                    <h2 className="text-[1.1rem] sm:text-[1.3rem] font-semibold text-[var(--re-text-primary)] mb-4">
                        Accessibility Polish — WCAG 2.1 AA
                    </h2>

                    <div className="mb-6">
                        <h4 className="text-xs font-semibold uppercase tracking-wide mb-3" style={{ color: T.textMuted }}>
                            ♿ Accessibility
                        </h4>
                        <ul className="m-0 pl-5 leading-[1.8]" style={{ color: T.text }}>
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
                    <div className="flex items-center gap-3 mb-5 pb-4" style={{ borderBottom: `1px solid ${T.border}` }}>
                        <span className="text-white text-xs font-semibold px-2.5 py-1 rounded" style={{ background: T.accent }}>
                            v1.1.0
                        </span>
                        <span className="text-sm" style={{ color: T.textMuted }}>March 4, 2026</span>
                    </div>

                    <h2 className="text-[1.1rem] sm:text-[1.3rem] font-semibold text-[var(--re-text-primary)] mb-4">
                        Onboarding UX Redesign
                    </h2>

                    <div className="mb-6">
                        <h4 className="text-xs font-semibold uppercase tracking-wide mb-3" style={{ color: T.textMuted }}>
                            ✨ Features
                        </h4>
                        <ul className="m-0 pl-5 leading-[1.8]" style={{ color: T.text }}>
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
                    <div className="flex items-center gap-3 mb-5 pb-4" style={{ borderBottom: `1px solid ${T.border}` }}>
                        <span className="text-white text-xs font-semibold px-2.5 py-1 rounded" style={{ background: T.accent }}>
                            v1.0.0
                        </span>
                        <span className="text-sm" style={{ color: T.textMuted }}>February 5, 2026</span>
                    </div>

                    <h2 className="text-[1.1rem] sm:text-[1.3rem] font-semibold text-[var(--re-text-primary)] mb-4">
                        Initial Public Release
                    </h2>

                    <div className="mb-6">
                        <h4 className="text-xs font-semibold uppercase tracking-wide mb-3" style={{ color: T.textMuted }}>
                            ✨ Features
                        </h4>
                        <ul className="m-0 pl-5 leading-[1.8]" style={{ color: T.text }}>
                            <li>FSMA 204 compliance module with CTEs and KDEs</li>
                            <li>FDA Request Mode for 24-hour export compliance</li>
                            <li>Graph-based supply chain tracing (forward/backward)</li>
                            <li>Cryptographic record hashing for tamper evidence</li>
                            <li>FTL Checker tool for Food Traceability List verification</li>
                        </ul>
                    </div>

                    <div className="mb-6">
                        <h4 className="text-xs font-semibold uppercase tracking-wide mb-3" style={{ color: T.textMuted }}>
                            📚 Documentation
                        </h4>
                        <ul className="m-0 pl-5 leading-[1.8]" style={{ color: T.text }}>
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
