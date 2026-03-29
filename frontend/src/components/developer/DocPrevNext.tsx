'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { DOC_PAGES } from '@/lib/doc-pages';

export function DocPrevNext() {
  const pathname = usePathname();
  const currentIndex = DOC_PAGES.findIndex((p) => p.href === pathname);

  // Don't render on the docs index page or if page not found in list
  if (currentIndex === -1) return null;

  const prev = currentIndex > 0 ? DOC_PAGES[currentIndex - 1] : null;
  const next =
    currentIndex < DOC_PAGES.length - 1 ? DOC_PAGES[currentIndex + 1] : null;

  if (!prev && !next) return null;

  return (
    <nav
      aria-label="Previous and next documentation pages"
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        borderTop: '1px solid var(--re-border, rgba(255,255,255,0.06))',
        marginTop: 48,
        paddingTop: 24,
      }}
    >
      {prev ? (
        <Link
          href={prev.href}
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
            textDecoration: 'none',
            color: 'var(--re-text-secondary, #c8d1dc)',
            fontSize: 14,
            transition: 'color 0.15s',
          }}
        >
          <span
            style={{
              fontSize: 12,
              color: 'var(--re-text-muted, #64748b)',
            }}
          >
            &larr; Previous
          </span>
          <span style={{ fontWeight: 500, color: 'var(--re-brand, #10b981)' }}>
            {prev.title}
          </span>
        </Link>
      ) : (
        <div />
      )}

      {next ? (
        <Link
          href={next.href}
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-end',
            gap: 4,
            textDecoration: 'none',
            color: 'var(--re-text-secondary, #c8d1dc)',
            fontSize: 14,
            transition: 'color 0.15s',
          }}
        >
          <span
            style={{
              fontSize: 12,
              color: 'var(--re-text-muted, #64748b)',
            }}
          >
            Next &rarr;
          </span>
          <span style={{ fontWeight: 500, color: 'var(--re-brand, #10b981)' }}>
            {next.title}
          </span>
        </Link>
      ) : (
        <div />
      )}
    </nav>
  );
}
