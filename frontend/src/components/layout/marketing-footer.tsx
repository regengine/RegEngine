'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
    MARKETING_ALL_TOOLS_LINK,
    MARKETING_FOOTER_COMPANY_LINKS,
    MARKETING_FOOTER_DEVELOPER_LINKS,
    MARKETING_FOOTER_PRODUCT_LINKS,
    MARKETING_FREE_TOOLS,
    type MarketingNavLink,
} from '@/components/layout/marketing-nav';
import { Container } from '@/components/layout/container';
import { RegEngineWordmark } from '@/components/layout/regengine-wordmark';
import { requestShowCookiePrefs } from '@/lib/cookie-consent';
import { shouldHideMarketingChrome } from '@/lib/app-routes';

/**
 * Marketing footer.
 *
 * `<footer aria-label="Site footer">` is load-bearing: the Inflow Lab embed
 * shim hides the site chrome by `footer` selector. Every column, link and href
 * from `marketing-nav.ts` is unchanged — `public-site-fixes.test.tsx` asserts
 * the Product column's data directly.
 *
 * The row above the legal line carries the enforcement date in mono. It is the
 * same string the brand column used to hold, moved — not new copy. Proof-point
 * chips were tried here and removed: asserting compliance status in the site
 * footer is a claim the business makes, not one a restyle gets to add.
 */

const COLUMN_HEADING = 'mb-3 text-label uppercase text-re-text-tertiary';
const FOOTER_LINK =
    'mb-2.5 block text-small text-re-text-muted no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none';

function FooterColumn({ heading, links }: { heading: string; links: MarketingNavLink[] }) {
    return (
        <div>
            <h4 className={COLUMN_HEADING}>{heading}</h4>
            {links.map((link) => (
                <Link key={link.label} href={link.href} className={FOOTER_LINK}>
                    {link.label}
                </Link>
            ))}
        </div>
    );
}

export function MarketingFooter() {
    const pathname = usePathname();

    if (shouldHideMarketingChrome(pathname)) {
        return null;
    }

    return (
        <footer
            aria-label="Site footer"
            className="relative z-[2] border-t border-re-border-subtle bg-re-surface-card text-re-text-secondary"
        >
            <Container width="marketing" className="grid grid-cols-1 gap-10 pb-10 pt-14 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr_1fr]">
                <div>
                    <Link href="/" className="mb-3 flex items-center gap-2 no-underline" aria-label="RegEngine home">
                        <RegEngineWordmark size="sm" />
                    </Link>
                    <p className="max-w-[280px] text-small leading-5 text-re-text-muted">
                        Food traceability compliance for farms and food companies.
                    </p>
                </div>

                <FooterColumn heading="Product" links={MARKETING_FOOTER_PRODUCT_LINKS} />

                <div>
                    <h4 className={COLUMN_HEADING}>Free Tools</h4>
                    {MARKETING_FREE_TOOLS.map((link) => (
                        <Link key={link.href} href={link.href} className={FOOTER_LINK}>
                            {link.label}
                        </Link>
                    ))}
                    <Link
                        href={MARKETING_ALL_TOOLS_LINK.href}
                        className="mt-1 block text-small font-medium text-re-brand no-underline transition-colors duration-120 hover:text-re-brand-dark motion-reduce:transition-none"
                    >
                        View all tools →
                    </Link>
                </div>

                <FooterColumn heading="Developers" links={MARKETING_FOOTER_DEVELOPER_LINKS} />
                <FooterColumn heading="Company" links={MARKETING_FOOTER_COMPANY_LINKS} />
            </Container>

            {/* Trust row — stated proof points only (SPEC §6). */}
            <Container
                width="marketing"
                className="flex flex-wrap items-center gap-x-4 gap-y-3 border-t border-re-border-subtle py-4"
            >
                <span className="font-mono text-small text-re-text-tertiary">
                    FSMA 204 Enforcement: July 20, 2028
                </span>
            </Container>

            <Container
                width="marketing"
                className="flex flex-wrap items-center justify-between gap-4 border-t border-re-border-subtle py-5"
            >
                <span className="text-small text-re-text-muted">
                    &copy; 2026 RegEngine LLC All rights reserved.
                </span>
                <div className="flex flex-wrap items-center gap-4">
                    <Link
                        href="/dpa"
                        className="text-small text-re-text-muted no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
                    >
                        DPA
                    </Link>
                    <button
                        type="button"
                        onClick={requestShowCookiePrefs}
                        className="cursor-pointer border-0 bg-transparent p-0 text-small text-re-text-muted transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
                        aria-label="Manage cookie preferences"
                    >
                        Cookie Preferences
                    </button>
                    <span className="text-small text-re-text-muted">
                        Verify our exports yourself: <code className="font-mono">verify_chain.py</code>
                    </span>
                </div>
            </Container>
        </footer>
    );
}
