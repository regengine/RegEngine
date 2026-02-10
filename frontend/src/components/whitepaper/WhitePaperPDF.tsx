/**
 * WhitePaperPDF Component
 * 
 * PDF-optimized white paper template following RegEngine formatting standards.
 * Designed for clean print output with professional headers, footers, and typography.
 * 
 * Usage:
 * <WhitePaperPDF vertical="energy" title="Why RegEngine for Energy?">
 *   <ReactMarkdown>{content}</ReactMarkdown>
 * </WhitePaperPDF>
 */

import React from 'react';
import Image from 'next/image';
import './whitepaper-print.css';

interface WhitePaperPDFProps {
    vertical: string;
    title: string;
    subtitle?: string;
    publicationDate?: string;
    children: React.ReactNode;
    coverImage?: string;
}

const verticalColors: Record<string, string> = {
    energy: 'var(--re-brand)',      // Green
    nuclear: 'var(--re-accent-blue)',     // Blue
    finance: 'var(--re-accent-purple)',     // Purple
    healthcare: 'var(--re-accent-pink)',  // Pink
    manufacturing: 'var(--re-warning)', // Amber
    aerospace: 'var(--re-accent-cyan)',   // Cyan
    automotive: 'var(--re-danger)',  // Red
    construction: 'var(--re-warning)', // Orange
    gaming: 'var(--re-accent-purple)',      // Purple
    technology: 'var(--re-accent-purple)',  // Indigo
};

export function WhitePaperPDF({
    vertical,
    title,
    subtitle = 'A Technical White Paper',
    publicationDate = 'January 2026',
    children,
    coverImage,
}: WhitePaperPDFProps) {
    const brandColor = verticalColors[vertical] || 'var(--re-brand)';

    return (
        <div className="whitepaper-container">
            {/* Print-only styles */}
            <style jsx>{`
                .whitepaper-container {
                    --brand-color: ${brandColor};
                }
            `}</style>

            {/* Cover Page */}
            <div className="whitepaper-cover">
                {coverImage && (
                    <div className="cover-image">
                        <Image
                            src={coverImage}
                            alt={`${vertical} industry visual`}
                            fill
                            style={{ objectFit: 'cover' }}
                            priority
                        />
                    </div>
                )}
                <div className="cover-content">
                    <h1 className="cover-title">{title}</h1>
                    <p className="cover-subtitle">{subtitle}</p>
                    <p className="cover-publication">
                        Prepared by RegEngine | {publicationDate}
                    </p>
                </div>
            </div>

            {/* Document Pages with Headers/Footers */}
            <div className="whitepaper-pages">
                {/* Header - appears on every page */}
                <header className="whitepaper-header">
                    <div className="header-logo">
                        <Image
                            src="/logo.svg"
                            alt="RegEngine"
                            width={120}
                            height={40}
                        />
                    </div>
                    <div className="header-title">{title}</div>
                    <div className="header-page">Page <span className="page-number"></span></div>
                    <div className="header-line" style={{ backgroundColor: brandColor }}></div>
                </header>

                {/* Main Content */}
                <main className="whitepaper-content">
                    {children}
                </main>

                {/* Footer - appears on every page */}
                <footer className="whitepaper-footer">
                    <div className="footer-copyright">
                        © {new Date().getFullYear()} RegEngine Inc. | Confidential
                    </div>
                    <div className="footer-website">regengine.co</div>
                </footer>
            </div>
        </div>
    );
}

/**
 * WhitePaperTable Component
 * Styled table with alternating row shading and brand color header
 */
interface WhitePaperTableProps {
    headers: string[];
    rows: string[][];
    caption?: string;
}

export function WhitePaperTable({ headers, rows, caption }: WhitePaperTableProps) {
    return (
        <div className="whitepaper-table-container">
            <table className="whitepaper-table">
                <thead>
                    <tr>
                        {headers.map((header, i) => (
                            <th key={i}>{header}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row, i) => (
                        <tr key={i} className={i % 2 === 0 ? 'even' : 'odd'}>
                            {row.map((cell, j) => (
                                <td key={j}>{cell}</td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
            {caption && <p className="table-caption">{caption}</p>}
        </div>
    );
}

/**
 * WhitePaperCallout Component
 * Highlighted box for key stats or important notes
 */
interface WhitePaperCalloutProps {
    type?: 'stat' | 'note' | 'warning';
    children: React.ReactNode;
}

export function WhitePaperCallout({ type = 'note', children }: WhitePaperCalloutProps) {
    const classNames = `whitepaper-callout whitepaper-callout-${type}`;

    return (
        <div className={classNames}>
            {children}
        </div>
    );
}

/**
 * WhitePaperStat Component
 * Large number with context (for callout boxes)
 */
interface WhitePaperStatProps {
    value: string;
    label: string;
}

export function WhitePaperStat({ value, label }: WhitePaperStatProps) {
    return (
        <div className="whitepaper-stat">
            <div className="stat-value">{value}</div>
            <div className="stat-label">{label}</div>
        </div>
    );
}

/**
 * WhitePaperCodeBlock Component  
 * Technical code display with proper formatting
 */
interface WhitePaperCodeBlockProps {
    children: React.ReactNode;
    caption?: string;
}

export function WhitePaperCodeBlock({ children, caption }: WhitePaperCodeBlockProps) {
    return (
        <div className="whitepaper-code-container">
            <pre className="whitepaper-code">
                <code>{children}</code>
            </pre>
            {caption && <p className="code-caption">{caption}</p>}
        </div>
    );
}
