'use client';

import { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { DocSidebar } from '@/components/developer/DocSidebar';
import { DocPrevNext } from '@/components/developer/DocPrevNext';
import { DOC_PAGES } from '@/lib/doc-pages';

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
        <div
            style={{
                display: 'flex',
                maxWidth: 1200,
                margin: '0 auto',
                padding: '32px 24px',
                gap: 32,
                minHeight: '100vh',
            }}
        >
            {/* Sidebar -- hidden on mobile via CSS */}
            <div className="doc-sidebar-wrapper">
                <DocSidebar />
            </div>

            {/* Main content area */}
            <div style={{ flex: 1, minWidth: 0, maxWidth: 860 }}>
                {children}

                {/* Prev/Next navigation at the bottom of every sub-page */}
                {isDocPage && <DocPrevNext />}
            </div>

            {/* Responsive styles: hide sidebar on screens < 768px */}
            <style dangerouslySetInnerHTML={{ __html: `
                .doc-sidebar-wrapper {
                    display: block;
                }
                @media (max-width: 768px) {
                    .doc-sidebar-wrapper {
                        display: none;
                    }
                }
            `}} />
        </div>
    );
}
