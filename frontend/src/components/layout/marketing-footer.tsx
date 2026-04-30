'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
    MARKETING_ALL_TOOLS_LINK,
    MARKETING_FOOTER_COMPANY_LINKS,
    MARKETING_FOOTER_DEVELOPER_LINKS,
    MARKETING_FOOTER_PRODUCT_LINKS,
    MARKETING_FREE_TOOLS,
} from '@/components/layout/marketing-nav';
import { RegEngineWordmark } from '@/components/layout/regengine-wordmark';
import { requestShowCookiePrefs } from '@/lib/cookie-consent';
import { shouldHideMarketingChrome } from '@/lib/app-routes';

export function MarketingFooter() {
    const pathname = usePathname();

    if (shouldHideMarketingChrome(pathname)) {
        return null;
    }

    return (
        <footer
            aria-label="Site footer"
            className="relative z-[2] border-t border-[var(--re-surface-border)] bg-[var(--re-surface-card)] text-[var(--re-text-secondary)]"
        >
            <div className="max-w-[1100px] mx-auto px-6 pt-12 pb-8 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr_1fr] gap-10">
                <div>
                    <Link href="/" className="flex items-center gap-2 mb-3 no-underline" aria-label="RegEngine home">
                        <RegEngineWordmark size="sm" />
                    </Link>
                    <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed mb-4 max-w-[280px]">
                        Food traceability compliance for farms and food companies.
                    </p>
                    <div className="font-mono text-[12px] text-[var(--re-text-tertiary)]">
                        FSMA 204 Deadline: July 20, 2028
                    </div>
                </div>

                <div>
                    <h4 className="font-mono text-[0.65rem] uppercase tracking-[0.08em] text-[var(--re-text-tertiary)] mb-3">
                        Product
                    </h4>
                    {MARKETING_FOOTER_PRODUCT_LINKS.map((link) => (
                        <Link
                            key={link.label}
                            href={link.href}
                            className="block text-[13px] text-[var(--re-text-muted)] no-underline mb-2.5 hover:text-[var(--re-text-primary)] transition-colors"
                        >
                            {link.label}
                        </Link>
                    ))}
                </div>
                <div>
                    <h4 className="font-mono text-[0.65rem] uppercase tracking-[0.08em] text-[var(--re-text-tertiary)] mb-3">
                        Free Tools
                    </h4>
                    {MARKETING_FREE_TOOLS.map((link) => (
                        <Link
                            key={link.href}
                            href={link.href}
                            className="block text-[13px] text-[var(--re-text-muted)] no-underline mb-2.5 hover:text-[var(--re-text-primary)] transition-colors"
                        >
                            {link.label}
                        </Link>
                    ))}
                    <Link
                        href={MARKETING_ALL_TOOLS_LINK.href}
                        className="block text-[13px] text-[var(--re-brand-light)] no-underline mt-1 font-semibold hover:text-[var(--re-text-primary)] transition-colors"
                    >
                        View all tools →
                    </Link>
                </div>

                <div>
                    <h4 className="font-mono text-[0.65rem] uppercase tracking-[0.08em] text-[var(--re-text-tertiary)] mb-3">
                        Developers
                    </h4>
                    {MARKETING_FOOTER_DEVELOPER_LINKS.map((link) => (
                        <Link
                            key={link.label}
                            href={link.href}
                            className="block text-[13px] text-[var(--re-text-muted)] no-underline mb-2.5 hover:text-[var(--re-text-primary)] transition-colors"
                        >
                            {link.label}
                        </Link>
                    ))}
                </div>

                <div>
                    <h4 className="font-mono text-[0.65rem] uppercase tracking-[0.08em] text-[var(--re-text-tertiary)] mb-3">
                        Company
                    </h4>
                    {MARKETING_FOOTER_COMPANY_LINKS.map((item) => (
                        <Link
                            key={item.label}
                            href={item.href}
                            className="block text-[13px] text-[var(--re-text-muted)] no-underline mb-2.5 hover:text-[var(--re-text-primary)] transition-colors"
                        >
                            {item.label}
                        </Link>
                    ))}
                </div>
            </div>
            <div className="max-w-[1100px] mx-auto px-6 py-5 border-t border-[var(--re-surface-border)] flex flex-wrap justify-between items-center gap-4">
                <span className="text-[0.72rem] text-[var(--re-text-muted)]">
                    &copy; 2026 RegEngine Inc. All rights reserved.
                </span>
                <div className="flex flex-wrap items-center gap-4">
                    <Link href="/dpa" className="text-[0.72rem] text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)] transition-colors no-underline">
                        DPA
                    </Link>
                    <button
                        onClick={requestShowCookiePrefs}
                        className="text-[0.72rem] text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)] transition-colors cursor-pointer bg-transparent border-0 p-0"
                        aria-label="Manage cookie preferences"
                    >
                        Cookie Preferences
                    </button>
                    <code className="font-mono text-[0.68rem] text-[var(--re-text-muted)]">
                        verify_chain.py — don&apos;t trust, verify
                    </code>
                </div>
            </div>
        </footer>
    );
}
