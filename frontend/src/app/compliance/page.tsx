'use client';

import { useState } from 'react';
import Link from 'next/link';

import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { EmptyState } from '@/components/ui/empty-state';
import { ChecklistCardSkeleton, Skeleton } from '@/components/ui/skeleton';
import { HelpTooltip } from '@/components/ui/tooltip';
import { useChecklists, useIndustries } from '@/hooks/use-api';
import { useAuth } from '@/lib/auth-context';
import { CheckCircle, Search, Shield, ArrowRight, Upload, Lightbulb } from 'lucide-react';
import { Input } from '@/components/ui/input';

export default function CompliancePage() {
  const { hasTenantSession, isAuthenticated } = useAuth();
  const [selectedIndustry, setSelectedIndustry] = useState<string | undefined>();
  const [searchQuery, setSearchQuery] = useState('');
  const setupHref = isAuthenticated ? '/onboarding' : '/login';
  const setupLabel = isAuthenticated ? 'Finish Setup' : 'Sign In';

  const { data: industries, isLoading: industriesLoading } = useIndustries();
  const {
    data: checklists,
    isLoading: checklistsLoading,
    isError: checklistsError,
    refetch: refetchChecklists,
  } = useChecklists(selectedIndustry);

  const filteredChecklists = checklists?.filter((checklist) =>
    checklist.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    checklist.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <PageContainer>
      <PageHeader
        title="Compliance Checklists"
        description={
          <span className="inline-flex items-start gap-1">
            Browse and validate against FSMA 204 compliance requirements
            <HelpTooltip content="Pre-built checklists help you validate your configuration against FSMA 204 traceability requirements." />
          </span>
        }
        meta={
          <span className="inline-flex items-center gap-1.5">
            <CheckCircle className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            FSMA 204
          </span>
        }
      />

      <div className="space-y-6">
        {/* Workspace Setup Info */}
        {!hasTenantSession && (
          <div className="flex gap-3 rounded-md border border-l-[3px] border-re-border border-l-re-info bg-re-surface-card px-4 py-3 text-ui text-re-text-secondary">
            <Lightbulb
              className="mt-0.5 h-4 w-4 shrink-0 text-re-info"
              strokeWidth={1.75}
              aria-hidden="true"
            />
            <div className="min-w-0 flex-1">
              <p className="font-medium text-re-text-primary">
                {isAuthenticated ? 'Finish workspace setup' : 'Sign in to connect a workspace'}
              </p>
              <p className="mt-1">
                {isAuthenticated
                  ? 'Connect a workspace to validate these checklists against your live configuration.'
                  : 'Sign in to connect a workspace and validate these checklists against your live configuration.'}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button size="sm" variant="secondary" asChild>
                  <Link href={setupHref}>
                    {setupLabel}
                    <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                  </Link>
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="rounded-lg border border-re-border bg-re-surface-card px-4 py-3">
          <div className="flex flex-col gap-3 md:flex-row md:items-center">
            {/* Search */}
            <div className="w-full md:max-w-sm">
              <label htmlFor="checklist-search" className="sr-only">
                Search checklists
              </label>
              <Input
                id="checklist-search"
                type="search"
                placeholder="Search checklists..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                leadingIcon={<Search strokeWidth={1.75} />}
              />
            </div>

            {/* Industry Filter */}
            <div className="no-scrollbar flex flex-wrap items-center gap-1.5">
              <Button
                variant="secondary"
                size="sm"
                aria-pressed={selectedIndustry === undefined}
                onClick={() => setSelectedIndustry(undefined)}
                className={selectedIndustry === undefined ? 'bg-re-brand-muted text-re-brand' : undefined}
              >
                All
              </Button>
              {industriesLoading ? (
                <>
                  <Skeleton className="h-8 w-24" />
                  <Skeleton className="h-8 w-20" />
                  <Skeleton className="h-8 w-28" />
                </>
              ) : (
                industries?.map((industry) => (
                  <Button
                    key={industry.id}
                    variant="secondary"
                    size="sm"
                    aria-pressed={selectedIndustry === industry.id}
                    onClick={() => setSelectedIndustry(industry.id)}
                    className={selectedIndustry === industry.id ? 'bg-re-brand-muted text-re-brand' : undefined}
                  >
                    {industry.name}
                  </Button>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Checklists Grid */}
        {checklistsError ? (
          <div
            role="alert"
            className="flex gap-3 rounded-md border border-l-[3px] border-re-border border-l-re-danger bg-re-danger-bg px-4 py-3 text-ui text-re-text-secondary"
          >
            <Shield className="mt-0.5 h-4 w-4 shrink-0 text-re-danger" strokeWidth={1.75} aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="font-medium text-re-text-primary">Couldn&apos;t load compliance checklists</p>
              <p className="mt-1">Check your connection and retry.</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button variant="secondary" size="sm" onClick={() => refetchChecklists()}>
                  Retry
                </Button>
              </div>
            </div>
          </div>
        ) : checklistsLoading ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <ChecklistCardSkeleton key={i} />
            ))}
          </div>
        ) : filteredChecklists && filteredChecklists.length > 0 ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {filteredChecklists.map((checklist) => (
              <Card key={checklist.id} className="flex h-full flex-col">
                <CardHeader className="flex-col items-stretch gap-2">
                  <div className="flex items-start justify-between gap-3">
                    <Shield className="h-5 w-5 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                    <Badge tone="neutral">{checklist.industry}</Badge>
                  </div>
                  <CardTitle>{checklist.name}</CardTitle>
                  <CardDescription className="line-clamp-2">
                    {checklist.description}
                  </CardDescription>
                </CardHeader>
                <CardContent className="mt-auto">
                  <div className="flex items-center justify-between text-ui">
                    <span className="text-re-text-tertiary">
                      {checklist.items?.length || 0} requirements
                    </span>
                    <Badge tone="neutral" mono>v{checklist.version}</Badge>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={Shield}
            title="No checklists found"
            description={
              searchQuery
                ? 'Try adjusting your search criteria or clearing the filter.'
                : 'No compliance checklists available for the selected industry.'
            }
            action={
              <div className="flex w-full max-w-sm flex-col items-center gap-4">
                {searchQuery && (
                  <Button variant="secondary" onClick={() => setSearchQuery('')}>
                    Clear Search
                  </Button>
                )}

                <div className="w-full border-t border-re-border-subtle pt-4">
                  <p className="mb-3 text-small text-re-text-tertiary">
                    Want to add custom checklists?
                  </p>
                  <Button variant="secondary" size="sm" asChild>
                    <Link href="/ingest">
                      <Upload className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                      Ingest Documents
                    </Link>
                  </Button>
                </div>

                {!hasTenantSession && (
                  <div className="w-full border-t border-re-border-subtle pt-4">
                    <p className="mb-2 text-small text-re-text-tertiary">
                      {isAuthenticated ? 'Need to finish setup?' : 'Need to connect a workspace?'}
                    </p>
                    <Button size="sm" asChild>
                      <Link href={setupHref}>
                        {setupLabel}
                        <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                      </Link>
                    </Button>
                  </div>
                )}
              </div>
            }
          />
        )}

        {/* Info Cards */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <Card>
            <CardHeader className="flex-col items-stretch gap-1">
              <CardTitle>Rule Evaluation API</CardTitle>
              <CardDescription>
                Evaluate traceability events against the FSMA 204 rules engine programmatically
              </CardDescription>
            </CardHeader>
            <CardContent>
              <code className="block overflow-x-auto rounded-md bg-re-surface-inset px-3 py-2 font-mono text-[0.8125rem] text-re-text-secondary">
                POST /api/v1/rules/evaluate
              </code>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex-col items-stretch gap-1">
              <CardTitle>FSMA 204 Coverage</CardTitle>
              <CardDescription>
                Pre-built checklists and KDE templates for FDA Food Traceability List commodity groupings
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                <Badge tone="neutral">FSMA 204</Badge>
                <Badge tone="neutral">EPCIS 2.0</Badge>
                <Badge tone="neutral">GS1</Badge>
                <Badge tone="neutral">FDA CTEs</Badge>
                <Badge tone="neutral">KDEs</Badge>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex-col items-stretch gap-1">
              <CardTitle>FSMA Workspace</CardTitle>
              <CardDescription>
                Open advanced compliance tools for labels and traceability planning
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              <Button variant="secondary" className="w-full justify-start" asChild>
                <Link href="/compliance/labels">
                  Label Compliance
                </Link>
              </Button>
              <Button variant="secondary" className="w-full justify-start" asChild>
                <Link href="/compliance/traceability-plan">
                  Traceability Plan
                </Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </PageContainer>
  );
}
