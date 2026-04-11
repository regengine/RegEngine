"use client";

import React, { useEffect, useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Spinner } from '@/components/ui/spinner';
import { useReviewItems, useApproveReviewItem, useRejectReviewItem } from '@/hooks/use-review';
import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';

/* 
const API_URL = '/api/review/items'; 
*/

type DecisionAction = 'approve' | 'reject';

type ReviewItem = {
  id: string;
  doc_hash: string;
  confidence_score: number;
  created_at: string;
  updated_at: string;
  status: string;
  tenant_id: string;
  source_text: string;
  extracted_data: Record<string, unknown>;
};


export function CuratorReview() {
  const { apiKey } = useAuth();
  const { tenantId } = useTenant();
  const [processing, setProcessing] = useState<string | null>(null);

  const { data: items, isLoading, error } = useReviewItems(apiKey || '');
  const approveMutation = useApproveReviewItem();
  const rejectMutation = useRejectReviewItem();

  const handleDecision = async (id: string, action: DecisionAction) => {
    setProcessing(id);
    try {
      if (action === 'approve') {
        await approveMutation.mutateAsync({ adminKey: apiKey || '', itemId: id });
      } else {
        await rejectMutation.mutateAsync({ adminKey: apiKey || '', itemId: id });
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

  if (isLoading) {
    return (
      <div className="flex flex-col items-center gap-3 p-6 text-muted-foreground">
        <Spinner />
        <p>Loading queue...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-sm text-re-danger bg-re-danger-muted border border-re-danger rounded-lg">
        Unable to load review queue. Please verify service connectivity.
      </div>
    );
  }

  if (sortedItems.length === 0) {
    return (
      <div className="p-6 text-center text-muted-foreground border rounded-lg bg-muted/20">
        All caught up! No pending reviews.
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Review Queue ({sortedItems.length})</h2>
        <Badge variant="secondary">Curator Review</Badge>
      </div>
      {sortedItems.map((item) => (
        <Card key={item.id} className="border-l-4 border-l-yellow-400 shadow-sm">
          <CardHeader className="flex flex-row justify-between items-start gap-3">
            <div className="space-y-1">
              <CardTitle className="text-sm font-mono">ID: {item.id?.substring(0, 8) || 'N/A'}...</CardTitle>
              <p className="text-xs text-muted-foreground">
                Created: {new Date(item.created_at).toLocaleDateString()}
              </p>
            </div>
            <Badge variant="outline" className="text-xs">
              {(item.confidence_score * 100).toFixed(1)}% confidence
            </Badge>
          </CardHeader>
          <CardContent className="grid md:grid-cols-2 gap-4">
            <div className="bg-slate-100 p-3 rounded text-sm whitespace-pre-wrap dark:bg-slate-900/60 max-h-60 overflow-y-auto">
              <div className="font-semibold text-xs text-muted-foreground mb-1 uppercase">Source Text</div>
              {item.source_text}
            </div>
            <div className="space-y-3">
              <div className="font-semibold text-xs text-muted-foreground mb-1 uppercase">Extraction</div>
              <pre className="bg-re-info-muted p-3 rounded text-xs overflow-auto max-h-48 dark:bg-re-info/30 border">
                {JSON.stringify(item.extracted_data, null, 2)}
              </pre>
              <div className="flex gap-2 justify-end">
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => handleDecision(item.id, 'reject')}
                  disabled={!!processing || rejectMutation.isPending}
                >
                  {processing === item.id && rejectMutation.isPending ? 'Rejecting...' : 'Reject'}
                </Button>
                <Button
                  className="bg-re-success hover:bg-re-success"
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
