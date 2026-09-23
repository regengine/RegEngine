"use client";

import React, { useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { Spinner } from '@/components/ui/spinner';
import { useReviewItems, useApproveReviewItem, useRejectReviewItem } from '@/hooks/use-review';
import { useAuth } from '@/lib/auth-context';

type DecisionAction = 'approve' | 'reject';

export function CuratorReview() {
  const { hasAdminSession } = useAuth();
  const [processing, setProcessing] = useState<string | null>(null);

  const { data: items, isLoading, error } = useReviewItems(hasAdminSession);
  const approveMutation = useApproveReviewItem();
  const rejectMutation = useRejectReviewItem();

  const handleDecision = async (id: string, action: DecisionAction) => {
    setProcessing(id);
    try {
      if (action === 'approve') {
        await approveMutation.mutateAsync(id);
      } else {
        await rejectMutation.mutateAsync(id);
      }
    } finally {
      setProcessing(null);
    }
  };

  const sortedItems = useMemo(
    () =>
      items ? [...items].sort((a, b) => {
        const scoreDiff = b.confidence_score - a.confidence_score;
        return scoreDiff !== 0 ? scoreDiff : a.created_at.localeCompare(b.created_at);
      }) : [],
    [items]
  );

  if (!hasAdminSession) {
    return (
      <Callout tone="warning">
        Workspace admin or sysadmin access is required to load the review queue.
      </Callout>
    );
  }

  if (isLoading) {
    return (
      <div className="flex flex-col items-center gap-3 p-6 text-re-text-tertiary">
        <Spinner />
        <p>Loading queue...</p>
      </div>
    );
  }

  if (error) {
    return (
      <Callout tone="danger" role="alert">
        Unable to load review queue. Please verify service connectivity.
      </Callout>
    );
  }

  if (sortedItems.length === 0) {
    return <EmptyState bare title="All caught up! No pending reviews." />;
  }

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-heading text-re-text-primary">Review Queue ({sortedItems.length})</h2>
        <Badge>Curator Review</Badge>
      </div>
      {sortedItems.map((item) => (
        <Card key={item.id}>
          <CardHeader>
            <div className="min-w-0 space-y-1">
              <CardTitle className="font-mono text-[0.8125rem]">
                ID: {item.id?.substring(0, 8) || 'N/A'}...
              </CardTitle>
              <p className="text-small text-re-text-tertiary">
                Created: {new Date(item.created_at).toLocaleDateString()}
              </p>
            </div>
            <Badge size="sm">
              {(item.confidence_score * 100).toFixed(1)}% confidence
            </Badge>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <div className="max-h-60 overflow-y-auto whitespace-pre-wrap rounded-md border border-re-border-subtle bg-re-surface-inset p-3 text-ui text-re-text-secondary">
              <div className="mb-1 text-label text-re-text-muted">
                Source Preview
              </div>
              {item.source_text || 'No source preview available.'}
            </div>
            <div className="space-y-3">
              <div className="text-label text-re-text-muted">Extraction</div>
              <pre className="max-h-48 overflow-auto rounded-md border border-re-border-subtle bg-re-surface-inset p-3 font-mono text-small text-re-text-secondary">
                {JSON.stringify(item.extracted_data, null, 2)}
              </pre>
              <div className="flex justify-end gap-2">
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => handleDecision(item.id, 'reject')}
                  disabled={!!processing || rejectMutation.isPending}
                >
                  {processing === item.id && rejectMutation.isPending ? 'Rejecting...' : 'Reject'}
                </Button>
                <Button
                  size="sm"
                  onClick={() => handleDecision(item.id, 'approve')}
                  disabled={!!processing || approveMutation.isPending}
                >
                  {processing === item.id && approveMutation.isPending ? 'Approving...' : 'Approve'}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
