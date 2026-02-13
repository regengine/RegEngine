import fs from 'fs';
import path from 'path';
import { notFound } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Calculator as CalcIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import '@/components/whitepaper/whitepaper-print.css';
import { ExportButton } from '@/components/whitepaper/export-button';
import { T } from '@/lib/design-tokens';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Whitepaper-specific styles for readable light text on dark background
const wpStyles = {
    page: {
        minHeight: '100vh',
        background: T.bg,
        color: 'var(--re-text-primary)', // Very light text for readability
        fontFamily: T.fontSans,
    },
    header: {
        background: 'linear-gradient(135deg, rgba(16,185,129,0.15) 0%, rgba(6,182,212,0.1) 100%)',
        borderBottom: `1px solid ${T.border}`,
        padding: '48px 24px',
    },
    backLink: {
        display: 'inline-flex',
        alignItems: 'center',
        gap: '8px',
        color: T.accent,
        marginBottom: '24px',
        fontSize: '14px',
    },
    title: {
        fontSize: '2.5rem',
        fontWeight: 700,
        color: 'var(--re-text-primary)',
        marginBottom: '8px',
    },
    subtitle: {
        fontSize: '1.25rem',
        color: T.text,
    },
    contentWrapper: {
        maxWidth: '900px',
        margin: '0 auto',
        padding: '48px 24px',
    },
    article: {
        lineHeight: 1.8,
        fontSize: '1.1rem',
        color: 'var(--re-text-primary)', // High contrast light text
    },
    cta: {
        marginTop: '48px',
        padding: '32px',
        background: `linear-gradient(135deg, ${T.accent} 0%, #059669 100%)`,
        borderRadius: T.cardRadius,
        color: 'white',
    },
};

interface WhitePaperPageProps {
    params: Promise<{
        vertical: string;
    }>;
}

const verticalNames: Record<string, string> = {
    gaming: 'Gaming',
    automotive: 'Automotive',
    aerospace: 'Aerospace',
    manufacturing: 'Manufacturing',
    construction: 'Construction',
    energy: 'Energy',
    nuclear: 'Nuclear',
    finance: 'Finance',
    healthcare: 'Healthcare',
    technology: 'Technology',
};

export async function generateStaticParams() {
    return Object.keys(verticalNames).map((vertical) => ({
        vertical,
    }));
}

export async function generateMetadata({ params }: WhitePaperPageProps) {
    const { vertical } = await params;
    const verticalName = verticalNames[vertical];
    return {
        title: `Why RegEngine for ${verticalName}? | White Paper`,
        description: `Comprehensive white paper on RegEngine's ${verticalName} compliance solutions.`,
    };
}

export default async function WhitePaperPage({ params }: WhitePaperPageProps) {
    const { vertical } = await params;
    const verticalName = verticalNames[vertical];

    if (!verticalName) {
        notFound();
    }

    // Read markdown file from sales_enablement directory
    const markdownPath = path.join(
        process.cwd(),
        '..',
        'sales_enablement',
        'whitepapers',
        `${vertical}_why_regengine.md`
    );

    let content = '';
    try {
        content = fs.readFileSync(markdownPath, 'utf-8');
    } catch (error) {
        console.error(`Failed to load white paper for ${vertical}:`, error);
        content = `# White Paper Not Found\n\nThe white paper for ${verticalName} is currently unavailable.`;
    }

    // Vertical-specific key stats for visual appeal
    const verticalStats: Record<string, { stat: string; label: string; icon: string }[]> = {
        finance: [
            { stat: '200%+', label: 'Annual ROI', icon: '📈' },
            { stat: '$5M+', label: 'Revenue Acceleration', icon: '💰' },
            { stat: '67%', label: 'Faster Audits', icon: '⚡' },
        ],
        healthcare: [
            { stat: '175%+', label: 'Annual ROI', icon: '📈' },
            { stat: '$4M+', label: 'Penalties Avoided', icon: '🛡️' },
            { stat: '85%', label: 'Breach Risk Reduction', icon: '🔒' },
        ],
        energy: [
            { stat: '250%+', label: 'Annual ROI', icon: '📈' },
            { stat: '$12M+', label: 'FERC Violations Prevented', icon: '⚡' },
            { stat: '18→4', label: 'Months to Approval', icon: '🚀' },
        ],
        nuclear: [
            { stat: '300%+', label: 'Annual ROI', icon: '📈' },
            { stat: '$24M', label: 'Shutdown Prevention', icon: '🏭' },
            { stat: '36→14', label: 'Months for License', icon: '📋' },
        ],
    };

    const stats = verticalStats[vertical] || verticalStats.finance;

    return (
        <div style={wpStyles.page}>
            {/* Noise overlay for premium feel */}
            <div
                style={{
                    position: 'fixed',
                    inset: 0,
                    backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
                    opacity: 0.015,
                    pointerEvents: 'none',
                    zIndex: 1,
                }}
            />

            {/* Header Section */}
            <div style={wpStyles.header} className="print:hidden">
                <div className="max-w-[900px] mx-auto">
                    <Link
                        href={`/verticals/${vertical}`}
                        style={wpStyles.backLink}
                    >
                        <ArrowLeft className="w-4 h-4" />
                        Back to {verticalName} Vertical
                    </Link>

                    <h1 style={wpStyles.title}>
                        Why RegEngine for {verticalName}?
                    </h1>
                    <p style={wpStyles.subtitle}>
                        Competitive positioning white paper
                    </p>

                    <div style={{ display: 'flex', gap: '16px', marginTop: '24px' }}>
                        <ExportButton />
                        <Link href={`/verticals/${vertical}/calculator`}>
                            <Button variant="outline" style={{ borderColor: T.border, color: T.text }}>
                                <CalcIcon style={{ width: 16, height: 16, marginRight: 8 }} />
                                View ROI Calculator
                            </Button>
                        </Link>
                    </div>
                </div>
            </div>

            {/* Persona Routing Box */}
            <div style={{ background: 'rgba(16,185,129,0.08)', borderBottom: `1px solid ${T.border}`, padding: '24px' }} className="print:hidden">
                <div style={{
                    maxWidth: '900px',
                    margin: '0 auto',
                    border: `1px solid rgba(16,185,129,0.3)`,
                    borderRadius: T.cardRadius,
                    padding: '20px 24px',
                    background: 'rgba(0,0,0,0.3)',
                }}>
                    <p style={{
                        color: 'var(--re-text-primary)',
                        fontSize: '15px',
                        margin: 0,
                        lineHeight: 1.8,
                    }}>
                        <strong className="text-re-brand">Choose your path:</strong><br />
                        <span className="text-re-text-secondary">CFO/CRO?</span>{' '}
                        <Link href={`/verticals/${vertical}/whitepaper/executive-brief`} style={{ color: T.accent, textDecoration: 'underline' }}>
                            Read the Executive Brief
                        </Link>
                        <span className="text-re-text-muted"> (2 min)</span><br />
                        <span className="text-re-text-secondary">CISO/Compliance?</span>{' '}
                        <Link href={`/verticals/${vertical}/whitepaper/technical`} style={{ color: T.accent, textDecoration: 'underline' }}>
                            Read the Technical Architecture
                        </Link>
                        <span className="text-re-text-muted"> (5 min)</span><br />
                        <span className="text-re-text-secondary">Building the business case?</span>{' '}
                        <span className="text-re-text-primary">Keep scrolling.</span>
                    </p>
                </div>
            </div>

            {/* Visual Stats Section - Non-technical friendly */}
            <div style={{ background: T.surface, borderBottom: `1px solid ${T.border}`, padding: '32px 24px' }} className="print:hidden">
                <div className="max-w-[900px] mx-auto">
                    <p style={{ color: T.textMuted, fontSize: '14px', marginBottom: '16px', textTransform: 'uppercase', letterSpacing: '1px' }}>
                        Key Benefits at a Glance
                    </p>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '24px' }}>
                        {stats.map((item, idx) => (
                            <div
                                key={idx}
                                style={{
                                    background: 'rgba(255,255,255,0.03)',
                                    border: `1px solid ${T.border}`,
                                    borderRadius: T.cardRadius,
                                    padding: '24px',
                                    textAlign: 'center',
                                }}
                            >
                                <div style={{ fontSize: '2rem', marginBottom: '8px' }}>{item.icon}</div>
                                <div style={{ fontSize: '2rem', fontWeight: 700, color: T.accent }}>{item.stat}</div>
                                <div style={{ fontSize: '14px', color: T.text, marginTop: '4px' }}>{item.label}</div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Content Section */}
            <div style={wpStyles.contentWrapper}>
                {/* Print Header */}
                <div className="hidden print:block" style={{ marginBottom: '32px', borderBottom: `1px solid ${T.border}`, paddingBottom: '16px' }}>
                    <h1 style={{ fontSize: '1.875rem', fontWeight: 700, color: '#111' }}>Why RegEngine for {verticalName}?</h1>
                    <p style={{ color: '#666' }}>Generated on {new Date().toLocaleDateString()}</p>
                </div>

                {/* Main Article with enhanced typography */}
                <article style={wpStyles.article}>
                    <style>{`
                        .wp-content h1 { font-size: 2rem; font-weight: 700; color: #ffffff; margin: 2rem 0 1rem; }
                        .wp-content h2 { font-size: 1.5rem; font-weight: 600; color: #f1f5f9; margin: 1.75rem 0 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 0.5rem; }
                        .wp-content h3 { font-size: 1.25rem; font-weight: 600; color: #e2e8f0; margin: 1.5rem 0 0.5rem; }
                        .wp-content p { color: #cbd5e1; margin: 0.75rem 0; }
                        .wp-content strong { color: #ffffff; }
                        .wp-content ul, .wp-content ol { color: #cbd5e1; margin: 1rem 0; padding-left: 1.5rem; }
                        .wp-content li { margin: 0.5rem 0; }
                        .wp-content blockquote { border-left: 3px solid ${T.accent}; padding-left: 1rem; margin: 1.5rem 0; color: #e2e8f0; font-style: italic; }
                        .wp-content table { width: 100%; border-collapse: collapse; margin: 1.5rem 0; }
                        .wp-content th { background: rgba(16,185,129,0.2); color: #ffffff; padding: 12px; text-align: left; border: 1px solid rgba(255,255,255,0.1); }
                        .wp-content td { padding: 12px; border: 1px solid rgba(255,255,255,0.1); color: #cbd5e1; }
                        .wp-content tr:nth-child(even) { background: rgba(255,255,255,0.02); }
                        .wp-content a { color: ${T.accent}; text-decoration: underline; }
                        .wp-content code { background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 4px; font-family: ${T.fontMono}; font-size: 0.9em; }
                        @media print {
                            .wp-content h1, .wp-content h2, .wp-content h3 { color: #111 !important; }
                            .wp-content p, .wp-content li, .wp-content td { color: #333 !important; }
                        }
                    `}</style>
                    <div className="wp-content">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {content}
                        </ReactMarkdown>
                    </div>
                </article>

                {/* Footer CTA Section */}
                <div style={wpStyles.cta} className="print:hidden">
                    <h3 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '8px' }}>Ready to Get Started?</h3>
                    <p style={{ marginBottom: '16px', opacity: 0.9 }}>Contact our sales team to schedule a personalized demo.</p>
                    <div className="flex gap-4">
                        <a href="mailto:sales@regengine.co?subject=Schedule Demo&body=Hi, I'd like to schedule a personalized demo of RegEngine.">
                            <Button style={{ background: 'white', color: T.accent }}>
                                Schedule Demo
                            </Button>
                        </a>
                        <Link href={`/verticals/${vertical}/calculator`}>
                            <Button variant="outline" style={{ borderColor: 'white', color: 'white' }}>
                                Calculate Your ROI
                            </Button>
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    );
}
