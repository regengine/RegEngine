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
import { Skeleton } from '@/components/ui/skeleton';
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
    href: '/ingest',
    icon: Upload,
    settingsKey: 'first_document_imported',
  },
  {
    id: 'team',
    label: 'Invite a team member',
    href: '/dashboard/settings/users',
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

/** Renders nothing once the checklist is complete or dismissed. */
function GettingStartedSlot() {
  return null;
}

export function GettingStartedCard() {
  const { tenantId, isTenantReady } = useTenant();
  const { data: status, isLoading, isError } = useOnboardingStatus(isTenantReady ? tenantId : null);
  const { data: metrics } = useSystemMetrics();
  const updateOnboarding = useUpdateOnboarding(tenantId);
  const [dismissing, setDismissing] = useState(false);

  // Never leave a skeleton on the page: if onboarding status cannot be read
  // (backend unreachable, no tenant yet), render nothing rather than a grey
  // block that never resolves.
  if (isError || (!isLoading && !status)) return <GettingStartedSlot />;

  if (isLoading || !status) {
    return (
      <Card aria-hidden="true">
        <CardContent className="space-y-3">
          <Skeleton className="h-5 w-36" />
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-1.5 w-full" />
          {[1, 2, 3, 4].map((item) => (
            <Skeleton key={item} className="h-5 w-full" />
          ))}
        </CardContent>
      </Card>
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
    <Card>
      <CardContent className="space-y-4">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div>
            <h3 className="text-subheading text-re-text-primary">Getting Started</h3>
            <p className="mt-0.5 text-small text-re-text-muted">
              {completedCount} of {CHECKLIST.length} complete
            </p>
          </div>
          <button
            type="button"
            onClick={handleDismiss}
            disabled={dismissing}
            aria-label="Dismiss"
            title="Dismiss"
            className="-m-1 rounded-md p-1 text-re-text-muted transition-colors duration-120 hover:text-re-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none"
          >
            {dismissing ? (
              <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            ) : (
              <X className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        </div>

        <Progress value={progress} className="h-1.5" />

        {/* Checklist */}
        <ul className="space-y-1">
          {CHECKLIST.map((item) => {
            const done = isItemDone(item);

            return (
              <li key={item.id}>
                <Link
                  href={done ? '#' : item.href}
                  className={`flex items-center gap-2.5 rounded-md px-2 py-1.5 text-ui no-underline transition-colors duration-120 motion-reduce:transition-none ${
                    done
                      ? 'text-re-text-muted'
                      : 'text-re-text-secondary hover:bg-re-surface-inset hover:text-re-text-primary'
                  }`}
                >
                  {done ? (
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-re-success" aria-hidden="true" />
                  ) : (
                    <Circle className="h-4 w-4 shrink-0 text-re-border-strong" aria-hidden="true" />
                  )}
                  <span className={done ? 'line-through' : ''}>
                    {item.label}
                  </span>
                  {!done && (
                    <ChevronRight className="ml-auto h-3.5 w-3.5 text-re-text-muted" aria-hidden="true" />
                  )}
                </Link>
              </li>
            );
          })}
        </ul>

        {/* Guided walkthrough link */}
        <div className="border-t border-re-border-subtle pt-3">
          <Link
            href="/onboarding/setup/welcome"
            className="text-small text-re-text-muted no-underline transition-colors duration-120 hover:text-re-brand motion-reduce:transition-none"
          >
            Prefer a guided tutorial? Take the full walkthrough &rarr;
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
