'use client';

import { useState } from 'react';
import Link from 'next/link';
import { motion, AnimatePresence } from 'framer-motion';
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
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { useTenant } from '@/lib/tenant-context';
import { useOnboardingStatus, useUpdateOnboarding } from '@/hooks/use-onboarding';

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

export function GettingStartedCard() {
  const { tenantId } = useTenant();
  const { data: status, isLoading } = useOnboardingStatus(tenantId);
  const updateOnboarding = useUpdateOnboarding(tenantId);
  const [dismissing, setDismissing] = useState(false);

  if (isLoading || !status) return null;

  const onboarding = status.onboarding || {};

  // Don't show if dismissed
  if (onboarding.dismissed_at) return null;

  const completedCount = CHECKLIST.filter((item) => {
    if (item.alwaysComplete) return true;
    return item.settingsKey && onboarding[item.settingsKey];
  }).length;

  // Don't show if all complete
  if (completedCount === CHECKLIST.length) return null;

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
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, height: 0 }}
      >
        <Card className="border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
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
                const done = item.alwaysComplete || (item.settingsKey && onboarding[item.settingsKey]);
                const Icon = item.icon;

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
                href="/onboarding/supplier-flow"
                className="text-xs text-[var(--re-text-muted)] hover:text-[var(--re-brand)] transition-colors"
              >
                Prefer a guided tutorial? Take the full walkthrough &rarr;
              </Link>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </AnimatePresence>
  );
}
