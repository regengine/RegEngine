'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
    MARKETING_FOOTER_COMPANY_LINKS,
    MARKETING_FOOTER_DEVELOPER_LINKS,
    MARKETING_FOOTER_PRODUCT_LINKS,
    MARKETING_FREE_TOOLS,
} from '@/components/layout/marketing-nav';
import { requestShowCookiePrefs } from '@/lib/cookie-consent';

export function MarketingFooter() {
    const pathname = usePathname();

    // Hide global footer on standalone mobile app and dashboard routes
    if (
        pathname === '/mobile/capture' ||
        pathname === '/fsma/field-capture' ||
        pathname.startsWith('/dashboard') ||
        pathname.startsWith('/onboarding')
    ) {
        return null;
    }

    return (
        <footer
            aria-label="Site footer"
            className="relative z-[2] border-t border-[var(--re-surface-border)] bg-[#0f172a] text-white"
        >
            <div className="max-w-[1100px] mx-auto px-6 pt-12 pb-8 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr_1fr] gap-10">
                <div>
                    <Link href="/" className="flex items-center gap-2 mb-3 no-underline">
                        <span className="font-mono text-[0.85rem] text-[#aaa]">
                            Reg<span className="text-[var(--re-brand-light)]">Engine</span>
                        </span>
                    </Link>
                    <p className="text-[13px] text-[#777] leading-relaxed mb-4 max-w-[280px]">
                        Food traceability compliance for farms and food companies.
                    </p>
                    <div className="font-mono text-[12px] text-[#555]">
                        FSMA 204 Deadline: July 20, 2028
                    </div>
                </div>

                <div>
                    <h4 className="font-mono text-[0.65rem] uppercase tracking-[0.08em] text-[#555] mb-3">
                        Product
                    </h4>
                    {MARKETING_FOOTER_PRODUCT_LINKS.map((link) => (
                        <Link
                            key={link.label}
                            href={link.href}
                            className="block text-[13px] text-[#999] no-underline mb-2.5 hover:text-white transition-colors"
                        >
                            {link.label}
                        </Link>
                    ))}
                </div>
                <div>
                    <h4 className="font-mono text-[0.65rem] uppercase tracking-[0.08em] text-[#555] mb-3">
                        Free Tools
                    </h4>
                    {MARKETING_FREE_TOOLS.map((link) => (
                        <Link
                            key={link.href}
                            href={link.href}
                            className="block text-[13px] text-[#999] no-underline mb-2.5 hover:text-white transition-colors"
                        >
                            {link.label}
                        </Link>
                    ))}
                    <Link
                        href="/tools"
                        className="block text-[13px] text-[var(--re-brand-light)] no-underline mt-1 font-semibold hover:text-white transition-colors"
                    >
                        View all tools →
                    </Link>
                </div>

                <div>
                    <h4 className="font-mono text-[0.65rem] uppercase tracking-[0.08em] text-[#555] mb-3">
                        Developers
                    </h4>
                    {MARKETING_FOOTER_DEVELOPER_LINKS.map((link) => (
                        <Link
                            key={link.label}
                            href={link.href}
                            className="block text-[13px] text-[#999] no-underline mb-2.5 hover:text-white transition-colors"
                        >
                            {link.label}
                        </Link>
                    ))}
                </div>

                <div>
                    <h4 className="font-mono text-[0.65rem] uppercase tracking-[0.08em] text-[#555] mb-3">
                        Company
                    </h4>
                    {MARKETING_FOOTER_COMPANY_LINKS.map((item) => (
                        <Link
                            key={item.label}
                            href={item.href}
                            className="block text-[13px] text-[#999] no-underline mb-2.5 hover:text-white transition-colors"
                        >
                            {item.label}
                        </Link>
                    ))}
                </div>
            </div>
            <div className="max-w-[1100px] mx-auto px-6 py-5 border-t border-[rgba(255,255,255,0.08)] flex flex-wrap justify-between items-center gap-4">
                <span className="text-[0.72rem] text-[#555]">
                    &copy; 2026 RegEngine Inc. All rights reserved.
                </span>
                <div className="flex flex-wrap items-center gap-4">
                    <Link href="/dpa" className="text-[0.72rem] text-[#555] hover:text-[#999] transition-colors no-underline">
                        DPA
                    </Link>
                    <button
                        onClick={requestShowCookiePrefs}
                        className="text-[0.72rem] text-[#555] hover:text-[#999] transition-colors cursor-pointer bg-transparent border-0 p-0"
                        aria-label="Manage cookie preferences"
                    >
                        Cookie Preferences
                    </button>
                    <code className="font-mono text-[0.68rem] text-[#555]">
                        verify_chain.py — don&apos;t trust, verify
                    </code>
                </div>
            </div>
        </footer>
    );
}
