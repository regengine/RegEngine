'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { DOC_PAGES } from '@/lib/doc-pages';

/**
 * Previous / next pager at the foot of every docs sub-page.
 *
 * `nav[aria-label="Previous and next documentation pages"]` and the
 * "← Previous" / "Next →" strings are unchanged. The titles are ink, not brand
 * green: brand is reserved for the six places in SPEC §1.6, and a pager label
 * is not one of them.
 */
const LINK_CLASS =
  'group flex min-w-0 flex-col gap-1 rounded-md no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-ring-offset';

const TITLE_CLASS =
  'truncate text-ui font-medium text-re-text-primary transition-colors duration-120 group-hover:text-re-brand motion-reduce:transition-none';

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
      className="mt-12 flex items-center justify-between gap-4 border-t border-re-border-subtle pt-6"
    >
      {prev ? (
        <Link href={prev.href} className={LINK_CLASS}>
          <span className="text-small text-re-text-muted">&larr; Previous</span>
          <span className={TITLE_CLASS}>{prev.title}</span>
        </Link>
      ) : (
        <div />
      )}

      {next ? (
        <Link href={next.href} className={`${LINK_CLASS} items-end text-right`}>
          <span className="text-small text-re-text-muted">Next &rarr;</span>
          <span className={TITLE_CLASS}>{next.title}</span>
        </Link>
      ) : (
        <div />
      )}
    </nav>
  );
}
