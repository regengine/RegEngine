'use client';

import { experimentalFeaturesEnabled } from '@/lib/experimental-features';
import { FeatureNotEnabled } from '@/components/experimental/FeatureNotEnabled';

import { useState } from 'react';

import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Section } from '@/components/layout/section';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { DataTable, type DataTableColumn } from '@/components/ui/data-table';
import { EmptyState } from '@/components/ui/empty-state';
import { fieldControlClasses } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { StatTile } from '@/components/ui/stat-tile';
import { StatusBadge } from '@/components/ui/status-badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';

import { useAuth } from '@/lib/auth-context';
import { useEntities, useIdentityReviews } from '@/hooks/use-control-plane';
import { DemoBanner } from '@/components/control-plane/demo-banner';

import {
  Building2,
  CheckCircle,
  GitMerge,
  HelpCircle,
  Link2,
  type LucideIcon,
  Package,
  Users,
} from 'lucide-react';

interface Entity {
  entity_id: string;
  entity_type: string;
  canonical_name: string;
  gln?: string;
  gtin?: string;
  verification_status: string;
  confidence_score: number;
}

interface IdentityReview {
  review_id: string;
  match_type: string;
  match_confidence: number;
  status: string;
  entity_a_id?: string;
  entity_a_name?: string;
  entity_b_id?: string;
  entity_b_name?: string;
}

/** Entity type is a *kind*, so it uses the categorical ramp, not status colour. */
const ENTITY_TYPE_CONFIG: Record<string, { icon: LucideIcon; label: string; color: string }> = {
  firm: { icon: Users, label: 'Firm', color: 'text-re-cat-1' },
  facility: { icon: Building2, label: 'Facility', color: 'text-re-cat-2' },
  product: { icon: Package, label: 'Product', color: 'text-re-cat-3' },
  lot: { icon: Link2, label: 'Lot', color: 'text-re-cat-4' },
  trading_relationship: { icon: GitMerge, label: 'Trading', color: 'text-re-cat-5' },
};

const MATCH_TYPE_BADGE: Record<string, { tone: BadgeTone; label: string }> = {
  exact: { tone: 'success', label: 'Exact Match' },
  likely: { tone: 'warning', label: 'Likely Match' },
  ambiguous: { tone: 'neutral', label: 'Ambiguous' },
  unresolved: { tone: 'danger', label: 'Unresolved' },
};

const FILTER_SELECT = 'h-8 w-auto max-w-[12rem] py-0 pr-8 text-small';

function IdentityResolutionPageContent() {
  const { tenantId } = useAuth();
  const tid = tenantId || '';

  const [activeTab, setActiveTab] = useState('entities');
  const [entityTypeFilter, setEntityTypeFilter] = useState<string | undefined>();
  const [searchQuery, setSearchQuery] = useState('');

  const entities = useEntities(tid, entityTypeFilter);
  const reviews = useIdentityReviews(tid);

  const entityList = (entities.data?.entities ?? []) as unknown as Entity[];
  const reviewList = (reviews.data?.reviews ?? []) as unknown as IdentityReview[];
  const pendingReviewCount = reviewList.filter((r: IdentityReview) => r.status === 'pending').length;

  if (entities.error || reviews.error) {
    const err = (entities.error || reviews.error) as Error;
    const refetchAll = () => { entities.refetch(); reviews.refetch(); };
    return (
      <PageContainer>
        <Callout
          tone="danger"
          role="alert"
          title="Unable to load data from the control plane API."
          action={
            <Button variant="secondary" size="sm" onClick={refetchAll}>
              Retry
            </Button>
          }
        >
          {err.message}
        </Callout>
      </PageContainer>
    );
  }

  const visibleEntities = entityList.filter((e: Entity) => !searchQuery ||
    e.canonical_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    e.gln?.includes(searchQuery) ||
    e.gtin?.includes(searchQuery)
  );

  const columns: DataTableColumn<Entity>[] = [
    {
      key: 'entity_type',
      header: 'Type',
      width: '9rem',
      cell: (entity) => {
        const config = ENTITY_TYPE_CONFIG[entity.entity_type] || ENTITY_TYPE_CONFIG.firm;
        const Icon = config.icon;
        return (
          <span className="flex items-center gap-1.5 text-re-text-secondary">
            <Icon
              className={cn('h-4 w-4 shrink-0', config.color)}
              strokeWidth={1.75}
              aria-hidden="true"
            />
            {config.label}
          </span>
        );
      },
    },
    {
      key: 'canonical_name',
      header: 'Name',
      cell: (entity) => (
        <span className="font-medium text-re-text-primary">{entity.canonical_name}</span>
      ),
    },
    { key: 'gln', header: 'GLN', mono: true, cell: (entity) => entity.gln || '-' },
    { key: 'gtin', header: 'GTIN', mono: true, cell: (entity) => entity.gtin || '-' },
    {
      key: 'verification_status',
      header: 'Status',
      width: '10rem',
      cell: (entity) =>
        entity.verification_status === 'verified' ? (
          <StatusBadge state="compliant" label="Verified" size="sm" />
        ) : (
          <StatusBadge state="pending" label={entity.verification_status} size="sm" />
        ),
    },
    {
      key: 'confidence_score',
      header: 'Confidence',
      align: 'right',
      width: '8rem',
      // Colour alone used to carry the threshold here; the number carries it now.
      cell: (entity) => (
        <span className="tabular-nums text-re-text-primary">
          {(entity.confidence_score * 100).toFixed(0)}%
        </span>
      ),
    },
  ];

  return (
    <PageContainer>
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <PageHeader
          title="Identity Resolution"
          description="Canonical entities, alias management, and ambiguous match review"
          meta={
            pendingReviewCount > 0 ? (
              <StatusBadge state="at-risk" label={`${pendingReviewCount} Pending Reviews`} />
            ) : undefined
          }
          tabs={
            <TabsList>
              <TabsTrigger value="entities">
                <Building2 className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                Entities ({entityList.length})
              </TabsTrigger>
              <TabsTrigger value="reviews">
                <HelpCircle className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                Review Queue ({pendingReviewCount})
              </TabsTrigger>
            </TabsList>
          }
        />

        <DemoBanner visible={!!(entities.data?.__isDemo)} />

        <TabsContent value="entities">
          <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
            {Object.entries(ENTITY_TYPE_CONFIG)
              .filter(([k]) => k !== 'trading_relationship')
              .map(([type, config]) => {
                const count = entityList.filter((e: Entity) => e.entity_type === type).length;
                const label = config.label === 'Facility' ? 'Facilities' : `${config.label}s`;
                const pressed = entityTypeFilter === type;
                return (
                  <button
                    key={type}
                    type="button"
                    aria-pressed={pressed}
                    onClick={() => setEntityTypeFilter(pressed ? undefined : type)}
                    className="block w-full rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-ring-offset"
                  >
                    <StatTile
                      label={label}
                      value={count}
                      className={cn(pressed && 'border-re-border-strong bg-re-surface-inset')}
                    />
                  </button>
                );
              })}
          </div>

          <Section
            spacing="app"
            title="Canonical Entities"
            description={entities.isLoading ? 'Loading...' : `${entityList.length} entities`}
          >
            <DataTable
              caption="Canonical identity entities"
              columns={columns}
              data={visibleEntities}
              minWidth="880px"
              rowKey={(entity) => entity.entity_id}
              status={entities.isLoading ? 'loading' : visibleEntities.length === 0 ? 'empty' : 'idle'}
              empty={{
                icon: Building2,
                title: 'No entities registered',
                description: 'Entities are auto-registered from ingested traceability events',
              }}
              toolbar={{
                search: {
                  placeholder: 'Search entities...',
                  value: searchQuery,
                  onChange: setSearchQuery,
                  label: 'Search entities by name, GLN or GTIN',
                },
                filters: (
                  <>
                    <label htmlFor="identity-type-filter" className="sr-only">
                      Filter by entity type
                    </label>
                    <select
                      id="identity-type-filter"
                      className={cn(fieldControlClasses, FILTER_SELECT)}
                      value={entityTypeFilter || ''}
                      onChange={e => setEntityTypeFilter(e.target.value || undefined)}
                    >
                      <option value="">All Types</option>
                      <option value="firm">Firms</option>
                      <option value="facility">Facilities</option>
                      <option value="product">Products</option>
                      <option value="lot">Lots</option>
                    </select>
                  </>
                ),
              }}
            />
          </Section>
        </TabsContent>

        <TabsContent value="reviews">
          <Card>
            <CardHeader>
              <div className="min-w-0">
                <CardTitle>Ambiguous Match Review Queue</CardTitle>
                <CardDescription className="mt-1">
                  Potential duplicates requiring human review — confirm match, confirm distinct, or defer
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              {reviews.isLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map(i => <Skeleton key={i} className="h-20 w-full" />)}
                </div>
              ) : reviewList.length === 0 ? (
                <EmptyState
                  bare
                  icon={CheckCircle}
                  title="No pending reviews"
                  description="All identity matches have been resolved"
                />
              ) : (
                <div className="space-y-3">
                  {reviewList.map((review: IdentityReview) => {
                    const matchBadge = MATCH_TYPE_BADGE[review.match_type] || MATCH_TYPE_BADGE.ambiguous;
                    const isPending = review.status === 'pending';
                    return (
                      <Card key={review.review_id} variant="inset" padding="compact">
                        <div className="flex flex-wrap items-start justify-between gap-4">
                          <div className="min-w-0 flex-1">
                            <div className="mb-2 flex flex-wrap items-center gap-2">
                              <Badge tone={matchBadge.tone} size="sm">{matchBadge.label}</Badge>
                              <span className="text-ui text-re-text-tertiary">
                                {(review.match_confidence * 100).toFixed(0)}% confidence
                              </span>
                            </div>
                            <dl className="grid gap-3 sm:grid-cols-2">
                              <div className="rounded-md border border-re-border-subtle bg-re-surface-card p-2">
                                <dt className="text-label text-re-text-muted">Entity A</dt>
                                <dd className="mt-0.5 text-ui font-medium text-re-text-primary">
                                  {review.entity_a_name || review.entity_a_id?.slice(0, 8)}
                                </dd>
                              </div>
                              <div className="rounded-md border border-re-border-subtle bg-re-surface-card p-2">
                                <dt className="text-label text-re-text-muted">Entity B</dt>
                                <dd className="mt-0.5 text-ui font-medium text-re-text-primary">
                                  {review.entity_b_name || review.entity_b_id?.slice(0, 8)}
                                </dd>
                              </div>
                            </dl>
                          </div>
                          {!isPending && (
                            <Badge size="sm">{review.status?.replace(/_/g, ' ')}</Badge>
                          )}
                        </div>
                      </Card>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </PageContainer>
  );
}

export default function IdentityResolutionPage() {
    return experimentalFeaturesEnabled()
        ? <IdentityResolutionPageContent />
        : <FeatureNotEnabled featureName="Identity" backHref="/dashboard" backLabel="Back to dashboard" />;
}
