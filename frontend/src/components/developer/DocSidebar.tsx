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
        paddingRight: 24,
        borderRight: '1px solid var(--re-border, rgba(255,255,255,0.06))',
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          color: 'var(--re-text-muted, #64748b)',
          textTransform: 'uppercase',
          letterSpacing: '1px',
          marginBottom: 12,
          paddingLeft: 12,
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
                    ? 'var(--re-brand, #10b981)'
                    : 'var(--re-text-secondary, #c8d1dc)',
                  background: isActive
                    ? 'rgba(16,185,129,0.1)'
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
