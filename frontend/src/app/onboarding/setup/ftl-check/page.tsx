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
  ShieldCheck,
  AlertTriangle,
  Loader2,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { useAuth } from '@/lib/auth-context';
import { useUpdateOnboarding } from '@/hooks/use-onboarding';
import { FTL_CATEGORIES, type FTLCategory } from '@/lib/ftl-data';

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
      className={`group relative flex flex-col items-start gap-1.5 rounded-lg border p-3 text-left transition-all ${
        selected
          ? 'border-[var(--re-brand)] bg-[var(--re-brand)]/5'
          : 'border-[var(--re-surface-border)] hover:border-[var(--re-text-muted)]'
      }`}
    >
      {selected && (
        <div className="absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-[var(--re-brand)]">
          <Check className="h-3 w-3 text-white" />
        </div>
      )}
      <div className="flex items-center gap-2">
        <Icon className={`h-4 w-4 ${selected ? 'text-[var(--re-brand)]' : 'text-[var(--re-text-muted)]'}`} />
        <span className={`text-sm font-medium ${selected ? 'text-[var(--re-text-primary)]' : 'text-[var(--re-text-secondary)]'}`}>
          {cat.name}
        </span>
      </div>
      <span className="text-xs text-[var(--re-text-muted)] line-clamp-1">
        {cat.examples}
      </span>
      {cat.covered ? (
        <Badge variant="outline" className="mt-0.5 border-emerald-500/30 text-emerald-400 text-[10px] px-1.5 py-0">
          On FTL
        </Badge>
      ) : (
        <Badge variant="outline" className="mt-0.5 border-[var(--re-surface-border)] text-[var(--re-text-muted)] text-[10px] px-1.5 py-0">
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

    try {
      await updateOnboarding.mutateAsync({
        onboarding: { ftl_check_completed: true },
      });
      completeOnboarding();
      router.push('/dashboard');
    } catch {
      // best-effort
      router.push('/dashboard');
    }
  };

  return (
    <div className="space-y-4">
      <Card className="border-[var(--re-surface-border)] bg-[var(--re-surface-card)]/95">
        <CardHeader className="space-y-2 pb-2">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-500/10">
              <ShieldCheck className="h-5 w-5 text-amber-500" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-[var(--re-text-primary)]">
                Check Your FTL Coverage
              </h1>
              <p className="text-sm text-[var(--re-text-muted)]">
                Select the product categories your facility handles.
              </p>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-4">
            {FTL_CATEGORIES.map((cat) => (
              <CategoryCard
                key={cat.id}
                cat={cat}
                selected={selected.has(cat.id)}
                onToggle={() => toggle(cat.id)}
              />
            ))}
          </div>

          {!showResults ? (
            <Button
              className="h-11 w-full"
              disabled={selected.size === 0}
              onClick={handleCheck}
            >
              Check FTL Coverage ({selected.size} selected)
            </Button>
          ) : null}
        </CardContent>
      </Card>

      {/* Results */}
      <AnimatePresence>
        {showResults && results.total > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
          >
            <Card className="border-[var(--re-surface-border)] bg-[var(--re-surface-card)]/95">
              <CardContent className="pt-6 space-y-4">
                {/* Summary */}
                <div className="text-center space-y-2">
                  <div className="text-3xl font-bold text-[var(--re-text-primary)]">
                    {results.covered.length} of {results.total}
                  </div>
                  <p className="text-sm text-[var(--re-text-muted)]">
                    categories you selected are on the FDA Food Traceability List
                  </p>
                  <Progress
                    value={results.total > 0 ? (results.covered.length / results.total) * 100 : 0}
                    className="h-2 mx-auto max-w-xs"
                  />
                </div>

                {/* Risk callout */}
                {results.highRisk.length > 0 && (
                  <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
                    <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-500" />
                    <div className="text-sm">
                      <span className="font-medium text-amber-400">
                        {results.highRisk.length} high-risk
                      </span>
                      <span className="text-[var(--re-text-muted)]">
                        {' '}categories with frequent FDA outbreak history:{' '}
                        {results.highRisk.map((c) => c.name).join(', ')}
                      </span>
                    </div>
                  </div>
                )}

                {/* Required CTEs */}
                {results.allCTEs.length > 0 && (
                  <div className="space-y-2">
                    <h3 className="text-sm font-medium text-[var(--re-text-secondary)]">
                      Critical Tracking Events you&apos;ll need to record:
                    </h3>
                    <div className="flex flex-wrap gap-1.5">
                      {results.allCTEs.map((cte) => (
                        <Badge
                          key={cte}
                          variant="outline"
                          className="border-[var(--re-surface-border)] text-[var(--re-text-secondary)]"
                        >
                          {cte}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {/* Not covered */}
                {results.notCovered.length > 0 && (
                  <p className="text-xs text-[var(--re-text-muted)]">
                    Not on the FTL (no FSMA 204 traceability required):{' '}
                    {results.notCovered.map((c) => c.name).join(', ')}
                  </p>
                )}

                <Button
                  className="h-11 w-full"
                  disabled={saving}
                  onClick={handleContinue}
                >
                  {saving ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Setting up dashboard...
                    </>
                  ) : (
                    <>
                      Continue to Dashboard
                      <ArrowRight className="ml-2 h-4 w-4" />
                    </>
                  )}
                </Button>
              </CardContent>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
