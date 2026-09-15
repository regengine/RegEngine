'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { DOC_PAGES } from '@/lib/doc-pages';

/**
 * Docs sidebar — the same nav-item recipe as the app sidebar (SPEC §3.3):
 * 36px rows, inset tint plus a 2px brand rail when active. The solid navy pill
 * with white text is gone, and so is the boxed, shadowed card the nav used to
 * sit in — the docs grid already separates it from the prose.
 *
 * `nav[aria-label="Documentation navigation"]` is kept: globals.css hides it
 * when the docs are printed.
 */
export function DocSidebar() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Documentation navigation"
      className="sticky top-[76px] self-start"
    >
      <p className="mb-2 px-3 text-label uppercase text-re-text-muted">Documentation</p>

      <ul className="list-none p-0">
        {DOC_PAGES.map((page) => {
          const isActive = pathname === page.href;
          return (
            <li key={page.href}>
              <Link
                href={page.href}
                aria-current={isActive ? 'page' : undefined}
                className={`relative flex h-9 items-center rounded-md px-3 text-ui no-underline ${
                  isActive
                    ? 'bg-re-surface-inset font-medium text-re-text-primary'
                    : 'text-re-text-secondary hover:bg-re-surface-inset hover:text-re-text-primary'
                } transition-colors duration-120 motion-reduce:transition-none`}
              >
                {isActive && (
                  <span
                    aria-hidden="true"
                    className="absolute bottom-1.5 left-0 top-1.5 w-0.5 rounded-full bg-re-brand"
                  />
                )}
                {page.title}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
