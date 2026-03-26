'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import { useAuth } from '@/lib/auth-context';
import { useEntities, useIdentityReviews } from '@/hooks/use-control-plane';
import { DemoBanner } from '@/components/control-plane/demo-banner';

import {
  Building2,
  CheckCircle,
  GitMerge,
  HelpCircle,
  Link2,
  MapPin,
  Package,
  Search,
  Users,
  XCircle,
} from 'lucide-react';

const ENTITY_TYPE_CONFIG: Record<string, { icon: any; label: string; color: string }> = {
  firm: { icon: Users, label: 'Firm', color: 'text-blue-500' },
  facility: { icon: Building2, label: 'Facility', color: 'text-green-500' },
  product: { icon: Package, label: 'Product', color: 'text-purple-500' },
  lot: { icon: Link2, label: 'Lot', color: 'text-amber-500' },
  trading_relationship: { icon: GitMerge, label: 'Trading', color: 'text-cyan-500' },
};

const MATCH_TYPE_BADGE: Record<string, { variant: 'default' | 'destructive' | 'warning' | 'secondary'; label: string }> = {
  exact: { variant: 'default', label: 'Exact Match' },
  likely: { variant: 'warning', label: 'Likely Match' },
  ambiguous: { variant: 'secondary', label: 'Ambiguous' },
  unresolved: { variant: 'destructive', label: 'Unresolved' },
};

export default function IdentityResolutionPage() {
  const { apiKey, tenantId } = useAuth();
  const tid = tenantId || '';

  const [activeTab, setActiveTab] = useState('entities');
  const [entityTypeFilter, setEntityTypeFilter] = useState<string | undefined>();
  const [searchQuery, setSearchQuery] = useState('');

  const entities = useEntities(tid, entityTypeFilter);
  const reviews = useIdentityReviews(tid);

  const entityList = entities.data?.entities ?? [];
  const reviewList = reviews.data?.reviews ?? [];
  const pendingReviewCount = reviewList.filter((r: any) => r.status === 'pending').length;

  return (
    <PageContainer>
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <GitMerge className="h-6 w-6 text-cyan-500" />
            Identity Resolution
          </h1>
          <p className="text-muted-foreground mt-1">
            Canonical entities, alias management, and ambiguous match review
          </p>
        </div>
        {pendingReviewCount > 0 && (
          <Badge variant="warning" className="text-sm px-3 py-1">
            <HelpCircle className="h-3.5 w-3.5 mr-1" />
            {pendingReviewCount} Pending Reviews
          </Badge>
        )}
      </div>

      <DemoBanner visible={!!(entities.data?.__isDemo)} />

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="mb-6">
          <TabsTrigger value="entities">
            <Building2 className="h-4 w-4 mr-1" />
            Entities ({entityList.length})
          </TabsTrigger>
          <TabsTrigger value="reviews">
            <HelpCircle className="h-4 w-4 mr-1" />
            Review Queue ({pendingReviewCount})
          </TabsTrigger>
        </TabsList>

        {/* Entities Tab */}
        <TabsContent value="entities">
          {/* Filters */}
          <Card className="mb-6">
            <CardContent className="pt-4 pb-4">
              <div className="flex flex-wrap items-center gap-3">
                <div className="relative flex-1 min-w-[200px]">
                  <Search className="absolute left-2.5 top-2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search entities..."
                    className="pl-9 h-9 text-sm"
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                  />
                </div>
                <select
                  className="text-sm border rounded px-2 py-1.5 bg-background h-9"
                  value={entityTypeFilter || ''}
                  onChange={e => setEntityTypeFilter(e.target.value || undefined)}
                >
                  <option value="">All Types</option>
                  <option value="firm">Firms</option>
                  <option value="facility">Facilities</option>
                  <option value="product">Products</option>
                  <option value="lot">Lots</option>
                </select>
              </div>
            </CardContent>
          </Card>

          {/* Entity Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            {Object.entries(ENTITY_TYPE_CONFIG).filter(([k]) => k !== 'trading_relationship').map(([type, config]) => {
              const count = entityList.filter((e: any) => e.entity_type === type).length;
              const Icon = config.icon;
              return (
                <Card key={type} className="cursor-pointer hover:border-primary/50 transition-colors"
                  onClick={() => setEntityTypeFilter(entityTypeFilter === type ? undefined : type)}
                >
                  <CardContent className="pt-4 pb-3">
                    <div className="flex items-center gap-2 mb-1">
                      <Icon className={`h-4 w-4 ${config.color}`} />
                      <span className="text-xs text-muted-foreground uppercase tracking-wider">{config.label === 'Facility' ? 'Facilities' : config.label + 's'}</span>
                    </div>
                    <p className="text-2xl font-bold">{count}</p>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {/* Entity List */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Canonical Entities</CardTitle>
              <CardDescription>
                {entities.isLoading ? 'Loading...' : `${entityList.length} entities`}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {entities.isLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3, 4, 5].map(i => <Skeleton key={i} className="h-12 w-full" />)}
                </div>
              ) : entityList.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <Building2 className="h-12 w-12 mx-auto mb-3 text-gray-300" />
                  <p className="font-medium">No entities registered</p>
                  <p className="text-sm">Entities are auto-registered from ingested traceability events</p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Type</TableHead>
                      <TableHead>Name</TableHead>
                      <TableHead>GLN</TableHead>
                      <TableHead>GTIN</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Confidence</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {entityList
                      .filter((e: any) => !searchQuery ||
                        e.canonical_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
                        e.gln?.includes(searchQuery) ||
                        e.gtin?.includes(searchQuery)
                      )
                      .map((entity: any) => {
                        const config = ENTITY_TYPE_CONFIG[entity.entity_type] || ENTITY_TYPE_CONFIG.firm;
                        const Icon = config.icon;
                        return (
                          <TableRow key={entity.entity_id}>
                            <TableCell>
                              <div className="flex items-center gap-1.5">
                                <Icon className={`h-4 w-4 ${config.color}`} />
                                <span className="text-xs">{config.label}</span>
                              </div>
                            </TableCell>
                            <TableCell className="font-medium">{entity.canonical_name}</TableCell>
                            <TableCell className="font-mono text-xs">{entity.gln || '-'}</TableCell>
                            <TableCell className="font-mono text-xs">{entity.gtin || '-'}</TableCell>
                            <TableCell>
                              <Badge variant={entity.verification_status === 'verified' ? 'default' : 'outline'} className="text-xs">
                                {entity.verification_status === 'verified' ? (
                                  <><CheckCircle className="h-3 w-3 mr-0.5" /> Verified</>
                                ) : entity.verification_status}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <span className={`text-sm ${entity.confidence_score >= 0.9 ? 'text-green-600' : entity.confidence_score >= 0.7 ? 'text-amber-600' : 'text-red-600'}`}>
                                {(entity.confidence_score * 100).toFixed(0)}%
                              </span>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Review Queue Tab */}
        <TabsContent value="reviews">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <HelpCircle className="h-5 w-5 text-amber-500" />
                Ambiguous Match Review Queue
              </CardTitle>
              <CardDescription>
                Potential duplicates requiring human review — confirm match, confirm distinct, or defer
              </CardDescription>
            </CardHeader>
            <CardContent>
              {reviews.isLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map(i => <Skeleton key={i} className="h-20 w-full" />)}
                </div>
              ) : reviewList.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <CheckCircle className="h-12 w-12 mx-auto mb-3 text-green-400" />
                  <p className="font-medium">No pending reviews</p>
                  <p className="text-sm">All identity matches have been resolved</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {reviewList.map((review: any) => {
                    const matchBadge = MATCH_TYPE_BADGE[review.match_type] || MATCH_TYPE_BADGE.ambiguous;
                    const isPending = review.status === 'pending';
                    return (
                      <div
                        key={review.review_id}
                        className={`border rounded-lg p-4 ${isPending ? '' : 'opacity-60'}`}
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-2">
                              <Badge variant={matchBadge.variant}>{matchBadge.label}</Badge>
                              <span className="text-sm text-muted-foreground">
                                {(review.match_confidence * 100).toFixed(0)}% confidence
                              </span>
                            </div>
                            <div className="grid grid-cols-2 gap-4 text-sm">
                              <div className="border rounded p-2 bg-muted/30">
                                <p className="text-xs text-muted-foreground mb-1">Entity A</p>
                                <p className="font-medium">{review.entity_a_name || review.entity_a_id?.slice(0, 8)}</p>
                              </div>
                              <div className="border rounded p-2 bg-muted/30">
                                <p className="text-xs text-muted-foreground mb-1">Entity B</p>
                                <p className="font-medium">{review.entity_b_name || review.entity_b_id?.slice(0, 8)}</p>
                              </div>
                            </div>
                          </div>
                          {isPending && (
                            <div className="flex flex-col gap-1">
                              <Button size="sm" variant="outline" className="text-xs h-7">
                                <CheckCircle className="h-3 w-3 mr-1 text-green-500" />
                                Match
                              </Button>
                              <Button size="sm" variant="outline" className="text-xs h-7">
                                <XCircle className="h-3 w-3 mr-1 text-red-500" />
                                Distinct
                              </Button>
                            </div>
                          )}
                          {!isPending && (
                            <Badge variant="outline" className="text-xs">
                              {review.status?.replace(/_/g, ' ')}
                            </Badge>
                          )}
                        </div>
                      </div>
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
