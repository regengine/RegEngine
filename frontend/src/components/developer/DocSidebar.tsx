'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { DOC_PAGES } from '@/lib/doc-pages';

export function DocSidebar() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Documentation navigation"
      style={{
        width: 240,
        flexShrink: 0,
        position: 'sticky',
        top: 24,
        alignSelf: 'flex-start',
        padding: '16px',
        border: '1px solid var(--re-surface-border)',
        borderRadius: 'var(--re-radius-lg)',
        background: 'var(--re-surface-elevated)',
        boxShadow: 'var(--re-shadow-sm)',
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          color: 'var(--re-text-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
          marginBottom: 12,
          paddingLeft: 8,
        }}
      >
        Documentation
      </div>

      <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {DOC_PAGES.map((page) => {
          const isActive = pathname === page.href;
          return (
            <li key={page.href}>
              <Link
                href={page.href}
                style={{
                  display: 'block',
                  padding: '8px 12px',
                  borderRadius: 6,
                  fontSize: 14,
                  fontWeight: isActive ? 600 : 400,
                  color: isActive
                    ? '#fff'
                    : 'var(--re-text-secondary)',
                  background: isActive
                    ? 'var(--re-brand)'
                    : 'transparent',
                  textDecoration: 'none',
                  transition: 'background 0.15s, color 0.15s',
                }}
              >
                {page.title}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
