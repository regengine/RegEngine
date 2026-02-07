import fs from 'fs';
import path from 'path';
import { notFound } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, FileText, Wrench, BookOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import '@/components/whitepaper/whitepaper-print.css';
import { ExportButton } from '@/components/whitepaper/export-button';
import { T } from '@/lib/design-tokens';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface DocPageProps {
    params: {
        vertical: string;
        doc: string;
    };
}

const verticalNames: Record<string, string> = {
    finance: 'Finance',
    healthcare: 'Healthcare',
    energy: 'Energy',
    nuclear: 'Nuclear',
};

const docTypes: Record<string, { title: string; filename: string; readTime: string }> = {
    'executive-brief': {
        title: 'Executive Brief',
        filename: '_executive_brief.md',
        readTime: '2 min read',
    },
    'technical': {
        title: 'Technical Architecture',
        filename: '_technical_architecture.md',
        readTime: '5 min read',
    },
    'business-case': {
        title: 'Full Business Case',
        filename: '_why_regengine.md',
        readTime: '15 min read',
    },
};

export async function generateStaticParams() {
    const verticals = Object.keys(verticalNames);
    const docs = Object.keys(docTypes);

    const params: { vertical: string; doc: string }[] = [];
    verticals.forEach(vertical => {
        docs.forEach(doc => {
            params.push({ vertical, doc });
        });
    });
    return params;
}

export async function generateMetadata({ params }: DocPageProps) {
    const verticalName = verticalNames[params.vertical] || params.vertical;
    const docType = docTypes[params.doc];
    const title = docType?.title || 'White Paper';

    return {
        title: `${title}: RegEngine for ${verticalName}`,
        description: `${title} for RegEngine's ${verticalName} compliance solutions.`,
    };
}

export default function WhitePaperDocPage({ params }: DocPageProps) {
    const { vertical, doc } = params;
    const verticalName = verticalNames[vertical];
    const docType = docTypes[doc];

    if (!verticalName || !docType) {
        notFound();
    }

    // Read markdown file
    const markdownPath = path.join(
        process.cwd(),
        '..',
        'sales_enablement',
        'whitepapers',
        `${vertical}${docType.filename}`
    );

    let content = '';
    try {
        content = fs.readFileSync(markdownPath, 'utf-8');
    } catch (error) {
        console.error(`Failed to load ${doc} for ${vertical}:`, error);
        content = `# Document Not Found\n\nThe ${docType.title} for ${verticalName} is currently unavailable.`;
    }

    const pageStyles = {
        page: {
            minHeight: '100vh',
            background: T.bg,
            color: '#f1f5f9',
            fontFamily: T.fontSans,
        },
        header: {
            background: 'linear-gradient(135deg, rgba(16,185,129,0.15) 0%, rgba(6,182,212,0.1) 100%)',
            borderBottom: `1px solid ${T.border}`,
            padding: '48px 24px',
        },
        contentWrapper: {
            maxWidth: '900px',
            margin: '0 auto',
            padding: '48px 24px',
        },
        article: {
            lineHeight: 1.8,
            fontSize: '1.1rem',
            color: '#e2e8f0',
        },
    };

    return (
        <div style={pageStyles.page}>
            {/* Noise overlay */}
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

            {/* Header */}
            <div style={pageStyles.header} className="print:hidden">
                <div style={{ maxWidth: '900px', margin: '0 auto' }}>
                    <Link
                        href={`/verticals/${vertical}/whitepaper`}
                        style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', color: T.accent, marginBottom: '24px', fontSize: '14px' }}
                    >
                        <ArrowLeft style={{ width: 16, height: 16 }} />
                        Back to White Paper Hub
                    </Link>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                        <span style={{
                            background: 'rgba(16,185,129,0.2)',
                            color: T.accent,
                            padding: '4px 12px',
                            borderRadius: '4px',
                            fontSize: '12px',
                            fontWeight: 600,
                            textTransform: 'uppercase',
                            letterSpacing: '0.5px',
                        }}>
                            {docType.readTime}
                        </span>
                    </div>

                    <h1 style={{ fontSize: '2.5rem', fontWeight: 700, color: '#ffffff', marginBottom: '8px' }}>
                        {docType.title}
                    </h1>
                    <p style={{ fontSize: '1.25rem', color: T.text }}>
                        RegEngine for {verticalName}
                    </p>

                    <div style={{ display: 'flex', gap: '16px', marginTop: '24px' }}>
                        <ExportButton />
                    </div>
                </div>
            </div>

            {/* Document Navigation */}
            <div style={{ background: T.surface, borderBottom: `1px solid ${T.border}`, padding: '16px 24px' }} className="print:hidden">
                <div style={{ maxWidth: '900px', margin: '0 auto', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                    <Link href={`/verticals/${vertical}/whitepaper/executive-brief`}>
                        <Button
                            variant={doc === 'executive-brief' ? 'default' : 'outline'}
                            size="sm"
                            style={doc === 'executive-brief' ? { background: T.accent } : { borderColor: T.border, color: T.text }}
                        >
                            <FileText style={{ width: 14, height: 14, marginRight: 6 }} />
                            Executive Brief
                        </Button>
                    </Link>
                    <Link href={`/verticals/${vertical}/whitepaper/technical`}>
                        <Button
                            variant={doc === 'technical' ? 'default' : 'outline'}
                            size="sm"
                            style={doc === 'technical' ? { background: T.accent } : { borderColor: T.border, color: T.text }}
                        >
                            <Wrench style={{ width: 14, height: 14, marginRight: 6 }} />
                            Technical Architecture
                        </Button>
                    </Link>
                    <Link href={`/verticals/${vertical}/whitepaper`}>
                        <Button
                            variant="outline"
                            size="sm"
                            style={{ borderColor: T.border, color: T.text }}
                        >
                            <BookOpen style={{ width: 14, height: 14, marginRight: 6 }} />
                            Full Business Case
                        </Button>
                    </Link>
                </div>
            </div>

            {/* Content */}
            <div style={pageStyles.contentWrapper}>
                <article style={pageStyles.article}>
                    <style>{`
                        .wp-content h1 { font-size: 2rem; font-weight: 700; color: #ffffff; margin: 2rem 0 1rem; }
                        .wp-content h2 { font-size: 1.5rem; font-weight: 600; color: #f1f5f9; margin: 1.75rem 0 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 0.5rem; }
                        .wp-content h3 { font-size: 1.25rem; font-weight: 600; color: #e2e8f0; margin: 1.5rem 0 0.5rem; }
                        .wp-content p { color: #cbd5e1; margin: 0.75rem 0; }
                        .wp-content strong { color: #ffffff; }
                        .wp-content ul, .wp-content ol { color: #cbd5e1; margin: 1rem 0; padding-left: 1.5rem; }
                        .wp-content li { margin: 0.5rem 0; }
                        .wp-content blockquote { border-left: 3px solid ${T.accent}; padding-left: 1rem; margin: 1.5rem 0; color: #e2e8f0; font-style: italic; background: rgba(16,185,129,0.05); padding: 1rem; border-radius: 0 8px 8px 0; }
                        .wp-content table { width: 100%; border-collapse: collapse; margin: 1.5rem 0; }
                        .wp-content th { background: rgba(16,185,129,0.2); color: #ffffff; padding: 12px; text-align: left; border: 1px solid rgba(255,255,255,0.1); }
                        .wp-content td { padding: 12px; border: 1px solid rgba(255,255,255,0.1); color: #cbd5e1; }
                        .wp-content tr:nth-child(even) { background: rgba(255,255,255,0.02); }
                        .wp-content a { color: ${T.accent}; text-decoration: underline; }
                        .wp-content code { background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
                        .wp-content pre { background: rgba(0,0,0,0.4); padding: 16px; border-radius: 8px; overflow-x: auto; }
                        .wp-content pre code { background: none; padding: 0; }
                        .wp-content hr { border: none; border-top: 1px solid rgba(255,255,255,0.1); margin: 2rem 0; }
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

                {/* CTA */}
                <div style={{
                    marginTop: '48px',
                    padding: '32px',
                    background: `linear-gradient(135deg, ${T.accent} 0%, #059669 100%)`,
                    borderRadius: T.cardRadius,
                    color: 'white',
                }} className="print:hidden">
                    <h3 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '8px' }}>Ready to Get Started?</h3>
                    <p style={{ marginBottom: '16px', opacity: 0.9 }}>Schedule a personalized demo with our team.</p>
                    <a href="mailto:sales@regengine.co?subject=Schedule Demo">
                        <Button style={{ background: 'white', color: T.accent }}>
                            Schedule Demo
                        </Button>
                    </a>
                </div>
            </div>
        </div>
    );
}
