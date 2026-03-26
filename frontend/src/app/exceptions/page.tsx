'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import Link from 'next/link';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { Skeleton } from '@/components/ui/skeleton';

import { useAuth } from '@/lib/auth-context';
import {
  useExceptions,
  useBlockingExceptionCount,
  useResolveException,
  useWaiveException,
  useAssignException,
} from '@/hooks/use-control-plane';

import {
  AlertTriangle,
  CheckCircle,
  Clock,
  Filter,
  Shield,
  User,
  XCircle,
} from 'lucide-react';

const SEVERITY_BADGE: Record<string, { variant: 'destructive' | 'warning' | 'secondary'; label: string }> = {
  critical: { variant: 'destructive', label: 'Critical' },
  warning: { variant: 'warning', label: 'Warning' },
  info: { variant: 'secondary', label: 'Info' },
};

const STATUS_BADGE: Record<string, { className: string; label: string }> = {
  open: { className: 'bg-red-100 text-red-800 border-red-200', label: 'Open' },
  in_review: { className: 'bg-blue-100 text-blue-800 border-blue-200', label: 'In Review' },
  awaiting_supplier: { className: 'bg-amber-100 text-amber-800 border-amber-200', label: 'Awaiting Supplier' },
  resolved: { className: 'bg-green-100 text-green-800 border-green-200', label: 'Resolved' },
  waived: { className: 'bg-gray-100 text-gray-600 border-gray-200', label: 'Waived' },
};

export default function ExceptionQueuePage() {
  const { apiKey, tenantId } = useAuth();
  const tid = tenantId || '';

  const [severityFilter, setSeverityFilter] = useState<string | undefined>();
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [supplierFilter, setSupplierFilter] = useState('');

  const exceptions = useExceptions(tid, {
    severity: severityFilter,
    status: statusFilter,
    source_supplier: supplierFilter || undefined,
  });
  const blocking = useBlockingExceptionCount(tid);
  const resolveException = useResolveException(tid);
  const waiveException = useWaiveException(tid);
  const assignException = useAssignException(tid);

  const blockingCount = blocking.data?.blocking_count ?? 0;
  const cases = exceptions.data?.cases ?? [];

  return (
    <PageContainer>
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Shield className="h-6 w-6 text-red-500" />
            Exception Queue
          </h1>
          <p className="text-muted-foreground mt-1">
            Manage compliance exceptions — resolve defects before they block response packages
          </p>
        </div>
        <div className="flex items-center gap-3">
          {blockingCount > 0 && (
            <Badge variant="destructive" className="text-sm px-3 py-1">
              <AlertTriangle className="h-3.5 w-3.5 mr-1" />
              {blockingCount} Blocking
            </Badge>
          )}
          {blockingCount === 0 && (
            <Badge className="bg-green-100 text-green-800 border-green-200 text-sm px-3 py-1">
              <CheckCircle className="h-3.5 w-3.5 mr-1" />
              No Blockers
            </Badge>
          )}
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {[
          { label: 'Open', count: cases.filter(c => c.status === 'open').length, color: 'text-red-600' },
          { label: 'In Review', count: cases.filter(c => c.status === 'in_review').length, color: 'text-blue-600' },
          { label: 'Awaiting Supplier', count: cases.filter(c => c.status === 'awaiting_supplier').length, color: 'text-amber-600' },
          { label: 'Resolved', count: cases.filter(c => c.status === 'resolved' || c.status === 'waived').length, color: 'text-green-600' },
        ].map(stat => (
          <Card key={stat.label}>
            <CardContent className="pt-4 pb-3">
              <p className="text-xs text-muted-foreground uppercase tracking-wider">{stat.label}</p>
              <p className={`text-2xl font-bold ${stat.color}`}>{stat.count}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <Card className="mb-6">
        <CardContent className="pt-4 pb-4">
          <div className="flex flex-wrap items-center gap-3">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <select
              className="text-sm border rounded px-2 py-1.5 bg-background"
              value={severityFilter || ''}
              onChange={e => setSeverityFilter(e.target.value || undefined)}
            >
              <option value="">All Severities</option>
              <option value="critical">Critical</option>
              <option value="warning">Warning</option>
              <option value="info">Info</option>
            </select>
            <select
              className="text-sm border rounded px-2 py-1.5 bg-background"
              value={statusFilter || ''}
              onChange={e => setStatusFilter(e.target.value || undefined)}
            >
              <option value="">All Statuses</option>
              <option value="open">Open</option>
              <option value="in_review">In Review</option>
              <option value="awaiting_supplier">Awaiting Supplier</option>
              <option value="resolved">Resolved</option>
              <option value="waived">Waived</option>
            </select>
            <Input
              placeholder="Filter by supplier..."
              className="w-48 text-sm h-8"
              value={supplierFilter}
              onChange={e => setSupplierFilter(e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      {/* Exception Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Exception Cases</CardTitle>
          <CardDescription>
            {exceptions.isLoading ? 'Loading...' : `${cases.length} cases`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {exceptions.isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3, 4, 5].map(i => <Skeleton key={i} className="h-12 w-full" />)}
            </div>
          ) : cases.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <CheckCircle className="h-12 w-12 mx-auto mb-3 text-green-400" />
              <p className="font-medium">No exceptions found</p>
              <p className="text-sm">All records are compliant with current filters</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Severity</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Supplier</TableHead>
                  <TableHead>Owner</TableHead>
                  <TableHead>Due</TableHead>
                  <TableHead>Remediation</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cases.map(exc => {
                  const sev = SEVERITY_BADGE[exc.severity] || SEVERITY_BADGE.info;
                  const stat = STATUS_BADGE[exc.status] || STATUS_BADGE.open;
                  const isActive = exc.status !== 'resolved' && exc.status !== 'waived';
                  const isOverdue = exc.due_date && new Date(exc.due_date) < new Date();

                  return (
                    <TableRow key={exc.case_id}>
                      <TableCell>
                        <Badge variant={sev.variant}>{sev.label}</Badge>
                      </TableCell>
                      <TableCell>
                        <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${stat.className}`}>
                          {stat.label}
                        </span>
                      </TableCell>
                      <TableCell className="text-sm">
                        {exc.rule_category?.replace(/_/g, ' ') || '-'}
                      </TableCell>
                      <TableCell className="text-sm max-w-[150px] truncate">
                        {exc.source_supplier || '-'}
                      </TableCell>
                      <TableCell className="text-sm">
                        {exc.owner_user_id ? (
                          <span className="flex items-center gap-1">
                            <User className="h-3 w-3" />
                            {exc.owner_user_id}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">Unassigned</span>
                        )}
                      </TableCell>
                      <TableCell className="text-sm">
                        {exc.due_date ? (
                          <span className={isOverdue ? 'text-red-600 font-medium' : ''}>
                            {isOverdue && <Clock className="h-3 w-3 inline mr-1" />}
                            {new Date(exc.due_date).toLocaleDateString()}
                          </span>
                        ) : '-'}
                      </TableCell>
                      <TableCell className="text-sm max-w-[200px] truncate">
                        {exc.recommended_remediation || '-'}
                      </TableCell>
                      <TableCell className="text-right">
                        {isActive && (
                          <div className="flex gap-1 justify-end">
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 text-xs"
                              onClick={() => resolveException.mutate({
                                caseId: exc.case_id,
                                resolutionSummary: 'Resolved from queue',
                                resolvedBy: 'dashboard_user',
                              })}
                            >
                              Resolve
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 text-xs text-muted-foreground"
                              onClick={() => waiveException.mutate({
                                caseId: exc.case_id,
                                waiverReason: 'Waived from queue',
                                waiverApprovedBy: 'dashboard_user',
                              })}
                            >
                              Waive
                            </Button>
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </PageContainer>
  );
}
