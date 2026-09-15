'use client';

import { ReactNode, useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronDown } from 'lucide-react';
import { Container } from '@/components/layout/container';
import { DocSidebar } from '@/components/developer/DocSidebar';
import { DocPrevNext } from '@/components/developer/DocPrevNext';
import { DOC_PAGES } from '@/lib/doc-pages';

/**
 * Docs shell — SPEC §3.1 `docs` container plus a real responsive grid:
 * `[232px | 1fr (capped at 760px) | 200px at ≥1280]`.
 *
 * This replaces a hand-rolled flexbox with a `dangerouslySetInnerHTML` <style>
 * block whose only job was to hide the sidebar under 768px — where it simply
 * vanished with no replacement, leaving a phone reader no way to reach any
 * other docs page. A `<details>` disclosure now carries the same list there.
 *
 * `.re-docs-shell` and `.doc-sidebar-wrapper` are kept: globals.css styles the
 * shell and hides the sidebar wrapper in the print stylesheet.
 */
type Heading = { id: string; text: string };

/** "On this page" — the ≥1280 rail. Reads the headings the page already renders. */
function DocsToc({ pathname }: { pathname: string }) {
    const [headings, setHeadings] = useState<Heading[]>([]);

    useEffect(() => {
        let cancelled = false;

        const scan = () => {
            if (cancelled) return;
            const main = document.getElementById('docs-main');
            if (!main) return;
            const found: Heading[] = [];
            main.querySelectorAll('h2').forEach((el, i) => {
                const text = (el.textContent ?? '').trim();
                if (!text) return;
                if (!el.id) el.id = `docs-section-${i + 1}`;
                found.push({ id: el.id, text });
            });
            setHeadings((prev) =>
                prev.length === found.length && prev.every((h, i) => h.id === found[i].id && h.text === found[i].text)
                    ? prev
                    : found
            );
        };

        const raf = requestAnimationFrame(scan);
        const timer = setTimeout(scan, 400);
        return () => {
            cancelled = true;
            cancelAnimationFrame(raf);
            clearTimeout(timer);
        };
    }, [pathname]);

    if (headings.length === 0) return null;

    return (
        <div data-docs-toc className="sticky top-[76px] self-start">
            <p className="mb-2 text-label uppercase text-re-text-muted">On this page</p>
            <ul className="list-none border-l border-re-border-subtle p-0">
                {headings.map((h) => (
                    <li key={h.id}>
                        <a
                            href={`#${h.id}`}
                            className="-ml-px block border-l border-transparent py-1.5 pl-3 text-small text-re-text-tertiary no-underline transition-colors duration-120 hover:border-re-border-strong hover:text-re-text-primary motion-reduce:transition-none"
                        >
                            {h.text}
                        </a>
                    </li>
                ))}
            </ul>
        </div>
    );
}

export default function DocsLayout({ children }: { children: ReactNode }) {
    const pathname = usePathname();

    // The docs index page (/docs) gets no sidebar/prev-next treatment
    const isIndex = pathname === '/docs';
    // Check if current page is one of the doc sub-pages
    const isDocPage = DOC_PAGES.some((p) => p.href === pathname);

    if (isIndex) {
        return <>{children}</>;
    }

    return (
        <div className="re-docs-shell min-h-screen">
            <Container width="docs" className="py-8 sm:py-10">
                {/* Mobile affordance for the sidebar, which is hidden under 768px. */}
                <details className="group mb-6 rounded-md border border-re-border bg-re-surface-card md:hidden">
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-ui font-medium text-re-text-primary">
                        Documentation
                        <ChevronDown
                            aria-hidden="true"
                            size={16}
                            strokeWidth={1.75}
                            className="shrink-0 text-re-text-muted transition-transform duration-180 group-open:rotate-180 motion-reduce:transition-none"
                        />
                    </summary>
                    <ul className="list-none border-t border-re-border-subtle p-2">
                        {DOC_PAGES.map((page) => {
                            const isActive = pathname === page.href;
                            return (
                                <li key={page.href}>
                                    <Link
                                        href={page.href}
                                        aria-current={isActive ? 'page' : undefined}
                                        className={`flex min-h-[44px] items-center rounded-md px-3 text-ui no-underline ${
                                            isActive
                                                ? 'bg-re-surface-inset font-medium text-re-text-primary'
                                                : 'text-re-text-secondary hover:bg-re-surface-inset hover:text-re-text-primary'
                                        } transition-colors duration-120 motion-reduce:transition-none`}
                                    >
                                        {page.title}
                                    </Link>
                                </li>
                            );
                        })}
                    </ul>
                </details>

                <div className="grid grid-cols-1 gap-8 md:grid-cols-[232px_minmax(0,1fr)] xl:grid-cols-[232px_minmax(0,1fr)_200px] xl:gap-10">
                    <div className="doc-sidebar-wrapper hidden md:block">
                        <DocSidebar />
                    </div>

                    <div id="docs-main" className="min-w-0 max-w-[760px]">
                        {children}

                        {/* Prev/Next navigation at the bottom of every sub-page */}
                        {isDocPage && <DocPrevNext />}
                    </div>

                    <aside className="hidden xl:block">
                        <DocsToc pathname={pathname} />
                    </aside>
                </div>
            </Container>
        </div>
    );
}
