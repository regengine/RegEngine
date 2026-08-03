'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  CheckCircle2,
  Circle,
  ChevronRight,
  X,
  Upload,
  Users,
  Shield,
  Factory,
  Leaf,
  Loader2,
} from 'lucide-react';

import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { useTenant } from '@/lib/tenant-context';
import { useOnboardingStatus, useUpdateOnboarding } from '@/hooks/use-onboarding';
import { useSystemMetrics } from '@/hooks/use-api';

interface ChecklistItem {
  id: string;
  label: string;
  href: string;
  icon: typeof Upload;
  settingsKey?: string;
  alwaysComplete?: boolean;
}

const CHECKLIST: ChecklistItem[] = [
  {
    id: 'account',
    label: 'Create account',
    href: '#',
    icon: CheckCircle2,
    alwaysComplete: true,
  },
  {
    id: 'facility',
    label: 'Set up a facility',
    href: '/onboarding/setup/facility',
    icon: Factory,
    settingsKey: 'facility_created',
  },
  {
    id: 'ftl',
    label: 'Check FTL coverage',
    href: '/onboarding/setup/ftl-check',
    icon: Leaf,
    settingsKey: 'ftl_check_completed',
  },
  {
    id: 'import',
    label: 'Import your first document',
    href: '/tools/data-import',
    icon: Upload,
    settingsKey: 'first_document_imported',
  },
  {
    id: 'team',
    label: 'Invite a team member',
    href: '/dashboard/team',
    icon: Users,
    settingsKey: 'team_member_invited',
  },
  {
    id: 'drill',
    label: 'Run a mock recall drill',
    href: '/dashboard/recall-drills',
    icon: Shield,
    settingsKey: 'mock_drill_run',
  },
];

function GettingStartedSlot({ pulse = false }: { pulse?: boolean }) {
  return (
    <div
      className={`min-h-[244px] rounded-lg border border-transparent ${pulse ? 'animate-pulse' : ''}`}
      aria-hidden="true"
    />
  );
}

export function GettingStartedCard() {
  const { tenantId, isTenantReady } = useTenant();
  const { data: status, isLoading } = useOnboardingStatus(isTenantReady ? tenantId : null);
  const { data: metrics } = useSystemMetrics();
  const updateOnboarding = useUpdateOnboarding(tenantId);
  const [dismissing, setDismissing] = useState(false);

  if (isLoading || !status) {
    return (
      <div
        className="min-h-[244px] rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5 animate-pulse"
        aria-hidden="true"
      >
        <div className="h-5 w-36 rounded bg-muted" />
        <div className="mt-2 h-3 w-24 rounded bg-muted" />
        <div className="mt-5 h-2 rounded bg-muted" />
        <div className="mt-5 space-y-3">
          {[1, 2, 3, 4].map((item) => (
            <div key={item} className="h-5 rounded bg-muted" />
          ))}
        </div>
      </div>
    );
  }

  const onboarding = status.onboarding || {};

  // Don't show if dismissed
  if (onboarding.dismissed_at) return <GettingStartedSlot />;

  // The import step used to key ONLY on the data-import tool's settings
  // flag, so tenants whose first records arrived via webhook, supplier
  // portal, or receiving saw "Import your first document" unchecked
  // forever despite having live traceability data. Data presence counts.
  const hasIngestedEvents = (metrics?.events_ingested ?? 0) > 0;

  const isItemDone = (item: (typeof CHECKLIST)[number]): boolean => {
    if (item.alwaysComplete) return true;
    if (item.id === 'import' && hasIngestedEvents) return true;
    return Boolean(item.settingsKey && onboarding[item.settingsKey]);
  };

  const completedCount = CHECKLIST.filter(isItemDone).length;

  // Don't show if all complete
  if (completedCount === CHECKLIST.length) return <GettingStartedSlot />;

  const progress = (completedCount / CHECKLIST.length) * 100;

  const handleDismiss = async () => {
    setDismissing(true);
    try {
      await updateOnboarding.mutateAsync({
        onboarding: { dismissed_at: new Date().toISOString() },
      });
    } catch {
      // best-effort
    }
    setDismissing(false);
  };

  return (
    <Card className="min-h-[244px] border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
      <CardContent className="pt-5 pb-4">
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div>
            <h3 className="text-sm font-semibold text-[var(--re-text-primary)]">
              Getting Started
            </h3>
            <p className="text-xs text-[var(--re-text-muted)] mt-0.5">
              {completedCount} of {CHECKLIST.length} complete
            </p>
          </div>
          <button
            onClick={handleDismiss}
            disabled={dismissing}
            className="text-[var(--re-text-muted)] hover:text-[var(--re-text-secondary)] transition-colors p-1 -m-1"
            title="Dismiss"
          >
            {dismissing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <X className="h-4 w-4" />
            )}
          </button>
        </div>

        <Progress value={progress} className="h-1.5 mb-4" />

        {/* Checklist */}
        <ul className="space-y-1">
          {CHECKLIST.map((item) => {
            const done = isItemDone(item);

            return (
              <li key={item.id}>
                <Link
                  href={done ? '#' : item.href}
                  className={`flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors ${
                    done
                      ? 'text-[var(--re-text-muted)]'
                      : 'text-[var(--re-text-secondary)] hover:bg-[var(--re-surface-elevated)] hover:text-[var(--re-text-primary)]'
                  }`}
                >
                  {done ? (
                    <CheckCircle2 className="h-4 w-4 text-re-brand flex-shrink-0" />
                  ) : (
                    <Circle className="h-4 w-4 text-[var(--re-surface-border)] flex-shrink-0" />
                  )}
                  <span className={done ? 'line-through' : ''}>
                    {item.label}
                  </span>
                  {!done && (
                    <ChevronRight className="ml-auto h-3.5 w-3.5 text-[var(--re-text-muted)]" />
                  )}
                </Link>
              </li>
            );
          })}
        </ul>

        {/* Guided walkthrough link */}
        <div className="mt-3 pt-3 border-t border-[var(--re-surface-border)]">
          <Link
            href="/onboarding/setup/welcome"
            className="text-xs text-[var(--re-text-muted)] hover:text-[var(--re-brand)] transition-colors"
          >
            Prefer a guided tutorial? Take the full walkthrough &rarr;
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
