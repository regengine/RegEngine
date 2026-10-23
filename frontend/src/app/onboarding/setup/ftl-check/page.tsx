'use client';

import { useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Leaf,
  Fish,
  Egg,
  Milk,
  Apple,
  Check,
  ArrowRight,
  Loader2,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { useAuth } from '@/lib/auth-context';
import { useUpdateOnboarding } from '@/hooks/use-onboarding';
import { FTL_CATEGORIES, type FTLCategory } from '@/lib/ftl-data';
import { StepIndicator } from '@/components/onboarding/StepIndicator';

const CATEGORY_ICONS: Record<string, typeof Leaf> = {
  Produce: Leaf,
  Seafood: Fish,
  Dairy: Milk,
  Eggs: Egg,
  Other: Apple,
};

function CategoryCard({
  cat,
  selected,
  onToggle,
}: {
  cat: FTLCategory;
  selected: boolean;
  onToggle: () => void;
}) {
  const Icon = CATEGORY_ICONS[cat.category] || Apple;

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={selected}
      className={cn(
        'relative flex flex-col items-start gap-1.5 rounded-lg border p-3 text-left transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-ring-offset motion-reduce:transition-none',
        selected
          ? 'border-re-text-primary bg-re-surface-inset'
          : 'border-re-border hover:border-re-border-strong',
      )}
    >
      {selected && (
        <Check
          className="absolute right-2 top-2 h-4 w-4 text-re-text-primary"
          strokeWidth={1.75}
          aria-hidden="true"
        />
      )}
      <span className="flex items-center gap-2 pr-6">
        <Icon
          className={cn(
            'h-4 w-4 shrink-0',
            selected ? 'text-re-text-primary' : 'text-re-text-tertiary',
          )}
          strokeWidth={1.75}
          aria-hidden="true"
        />
        <span className="text-ui font-medium text-re-text-primary">{cat.name}</span>
      </span>
      <span className="line-clamp-1 text-small text-re-text-tertiary">
        {cat.examples}
      </span>
      {cat.covered ? (
        <Badge tone="info" size="sm" className="mt-0.5">
          On FTL
        </Badge>
      ) : (
        <Badge tone="neutral" size="sm" className="mt-0.5">
          Not on FTL
        </Badge>
      )}
    </button>
  );
}

export default function FTLCheckPage() {
  const router = useRouter();
  const { completeOnboarding, tenantId } = useAuth();
  const updateOnboarding = useUpdateOnboarding(tenantId);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showResults, setShowResults] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setShowResults(false);
  };

  const results = useMemo(() => {
    const selectedCats = FTL_CATEGORIES.filter((c) => selected.has(c.id));
    const covered = selectedCats.filter((c) => c.covered);
    const notCovered = selectedCats.filter((c) => !c.covered);
    const highRisk = covered.filter((c) => c.outbreakFrequency === 'HIGH');
    const allCTEs = [...new Set(covered.flatMap((c) => c.ctes))];
    return { total: selectedCats.length, covered, notCovered, highRisk, allCTEs };
  }, [selected]);

  const handleCheck = () => setShowResults(true);

  const handleContinue = async () => {
    if (!tenantId) return;
    setSaving(true);
    setSaveError(null);

    try {
      await updateOnboarding.mutateAsync({
        onboarding: { ftl_check_completed: true },
      });
      // completeOnboarding() only runs after the mutation succeeds so the
      // onboarding state in localStorage / backend stays consistent.
      completeOnboarding();
      router.push('/dashboard');
    } catch {
      // #541 — Don't silently redirect on failure. Show an error banner so
      // the user can retry. Navigating to /dashboard with onboarding marked
      // incomplete causes a redirect loop back to /onboarding/setup.
      setSaveError('Could not save your progress. Please check your connection and try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card padding="spacious">
        <StepIndicator step={3} />
        <h1 className="mt-4 text-heading text-re-text-primary">
          Check Your FTL Coverage
        </h1>
        <p className="mt-1 text-ui text-re-text-secondary">
          Select the product categories your facility handles.
        </p>

        <div className="mt-6 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {FTL_CATEGORIES.map((cat) => (
            <CategoryCard
              key={cat.id}
              cat={cat}
              selected={selected.has(cat.id)}
              onToggle={() => toggle(cat.id)}
            />
          ))}
        </div>

        <div className="mt-8 flex flex-col-reverse gap-3 border-t border-re-border-subtle pt-5 sm:flex-row sm:items-center sm:justify-between">
          <Button
            variant="ghost"
            size="lg"
            onClick={() => router.push('/dashboard')}
          >
            Skip for now. I&apos;ll set up later
          </Button>
          {!showResults ? (
            <Button
              size="lg"
              disabled={selected.size === 0}
              onClick={handleCheck}
            >
              Check FTL Coverage ({selected.size} selected)
            </Button>
          ) : null}
        </div>
      </Card>

      {/* Results */}
      <AnimatePresence>
        {showResults && results.total > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
          >
            <Card padding="spacious">
              <div className="space-y-4">
                {/* Summary */}
                <div className="space-y-2 text-center">
                  <div className="text-title tabular-nums text-re-text-primary">
                    {results.covered.length} of {results.total}
                  </div>
                  <p className="text-ui text-re-text-secondary">
                    categories you selected are on the FDA Food Traceability List
                  </p>
                  <Progress
                    value={results.total > 0 ? (results.covered.length / results.total) * 100 : 0}
                    className="mx-auto h-2 max-w-xs"
                  />
                </div>

                {/* Risk callout */}
                {results.highRisk.length > 0 && (
                  <Callout tone="warning">
                    <span className="font-medium text-re-text-primary">
                      {results.highRisk.length} high-risk
                    </span>
                    <span>
                      {' '}categories with frequent FDA outbreak history:{' '}
                      {results.highRisk.map((c) => c.name).join(', ')}
                    </span>
                  </Callout>
                )}

                {/* Required CTEs */}
                {results.allCTEs.length > 0 && (
                  <div className="space-y-2">
                    <h3 className="text-ui font-medium text-re-text-primary">
                      Critical Tracking Events you&apos;ll need to record:
                    </h3>
                    <div className="flex flex-wrap gap-1.5">
                      {results.allCTEs.map((cte) => (
                        <Badge key={cte} tone="neutral" mono>
                          {cte}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {/* Not covered */}
                {results.notCovered.length > 0 && (
                  <p className="text-small text-re-text-tertiary">
                    Not on the FTL (no FSMA 204 traceability required):{' '}
                    {results.notCovered.map((c) => c.name).join(', ')}
                  </p>
                )}

                {/* #541 — Error banner with retry; no silent redirect on failure */}
                {saveError && (
                  <Callout tone="danger" role="alert">
                    {saveError}
                  </Callout>
                )}

                <Button
                  className="w-full"
                  size="lg"
                  disabled={saving}
                  onClick={handleContinue}
                >
                  {saving ? (
                    <>
                      <Loader2 className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                      Setting up dashboard...
                    </>
                  ) : (
                    <>
                      {saveError ? 'Retry' : 'Continue to Dashboard'}
                      <ArrowRight aria-hidden="true" />
                    </>
                  )}
                </Button>
              </div>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
