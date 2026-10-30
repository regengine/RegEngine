'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';
import { BookCallLink } from '@/components/conversion/BookCallLink';
import { RegEngineWordmark } from '@/components/layout/regengine-wordmark';
import { Button } from '@/components/ui/button';
import { shortLabel, type Scenario, type ViewId } from '@/lib/demo-workspace/model';
import { cn } from '@/lib/utils';
import { HueDot, LiveDot } from './HueDot';

export const NAV_ITEMS: ReadonlyArray<{ id: ViewId; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'import', label: 'Import' },
  { id: 'fix', label: 'Fix queue' },
  { id: 'ledger', label: 'Ledger' },
  { id: 'export', label: 'Export' },
];

interface DemoShellProps {
  view: ViewId;
  onNavigate: (view: ViewId) => void;
  openCount: number;
  title: string;
  subtitle: string;
  legend: readonly Scenario[];
  onResetAll: () => void;
  children: ReactNode;
}

/** Sidebar, banner and page header around the public workspace views. */
export function DemoShell({ view, onNavigate, openCount, title, subtitle, legend, onResetAll, children }: DemoShellProps) {
  return (
    <div className="re-demo-shell">
      <aside className="flex flex-col border-b border-r border-re-border-subtle bg-re-surface-card">
        <div className="border-b border-re-border-subtle px-4 pb-3.5 pt-4">
          <Link href="/" className="inline-flex no-underline" aria-label="RegEngine home">
            <RegEngineWordmark size="sm" />
          </Link>
          <div className="mt-3.5 flex items-center gap-2 rounded-md border border-re-border-subtle bg-re-surface-elevated px-2.5 py-2">
            <LiveDot className="h-2 w-2" />
            <div className="min-w-0">
              <p className="truncate text-small font-medium text-re-text-primary">Demo workspace</p>
              <p className="font-mono text-label normal-case tracking-normal text-re-text-muted">public · read-only</p>
            </div>
          </div>
        </div>

        <nav aria-label="Demo workspace" data-demo-nav className="flex flex-1 flex-col gap-0.5 overflow-auto px-2 py-2.5">
          {NAV_ITEMS.map((item) => {
            const active = item.id === view;
            const count = item.id === 'fix' && openCount > 0 ? openCount : null;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onNavigate(item.id)}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-[0.8125rem] transition-colors duration-120 hover:text-re-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none',
                  active ? 'bg-re-brand-muted font-semibold text-re-brand' : 'font-medium text-re-text-tertiary',
                )}
              >
                <span className="flex-1">{item.label}</span>
                {count !== null && (
                  <span className="rounded-full bg-re-warning-bg px-1.5 py-0.5 font-mono text-label font-semibold text-re-warning">
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        <div data-demo-aside-foot className="border-t border-re-border-subtle px-4 py-3 text-small leading-relaxed text-re-text-tertiary">
          Want this on your own records?
          <br />
          <BookCallLink href="/contact" placement="demo_sidebar" className="font-semibold text-re-brand no-underline">
            Book a 30-min call →
          </BookCallLink>
        </div>
      </aside>

      <main className="flex min-w-0 flex-col">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-re-brand-muted bg-re-brand-muted/60 px-6 py-2.5 text-small text-re-text-secondary">
          <span>
            <strong className="font-semibold text-re-text-primary">Demo workspace.</strong> No account needed. Five supply chains of
            synthetic data modelled on FDA major recall notices; every firm, lot and gap is invented.
          </span>
          <span className="whitespace-nowrap font-mono text-label uppercase tracking-[0.1em] text-re-brand">
            Live: CSV upload · JSON API
          </span>
        </div>

        <div className="mx-auto w-full max-w-[1280px] px-4 pb-12 pt-6 sm:px-6">
          <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="font-display text-title text-re-text-primary">{title}</h1>
              <p className="mt-1.5 max-w-[720px] text-[0.8438rem] text-re-text-tertiary">{subtitle}</p>
              <div className="mt-2.5 flex flex-wrap gap-3.5 text-small text-re-text-tertiary">
                <span className="font-mono text-label uppercase tracking-[0.1em] text-re-text-muted">FTL food</span>
                {legend.map((scenario) => (
                  <span key={scenario.id} className="inline-flex items-center gap-1.5">
                    <HueDot hue={scenario.hue} />
                    {shortLabel(scenario)}
                  </span>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap gap-2.5">
              <Button type="button" variant="secondary" size="sm" onClick={onResetAll}>
                Reset demo
              </Button>
              <Button type="button" variant="primary" size="sm" onClick={() => onNavigate('export')}>
                Export packages
              </Button>
            </div>
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}
