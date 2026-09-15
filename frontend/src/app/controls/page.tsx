'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input, fieldControlClasses } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

interface Control {
  id: string;
  control_id: string;
  title: string;
  description: string;
  framework: string;
  created_at: string;
}

export default function MyControlsPage() {
  const { isAuthenticated, isHydrated } = useAuth();
  const [controls, setControls] = useState<Control[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [formData, setFormData] = useState({
    control_id: '',
    title: '',
    description: '',
    framework: 'FSMA 204'
  });
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const router = useRouter();

  // #2835 Every response here previously went straight to .json() with no
  // response.ok check, so a 404 from the backend deserialized to `{detail: ...}`,
  // `data.controls` was undefined, and the page rendered its normal
  // "No controls found" empty state — a hard routing failure was invisible.
  // Create and delete were worse: they swallowed the failure entirely and
  // appeared to succeed. Surface the failure instead.
  const describeFailure = async (response: Response, fallback: string): Promise<string> => {
    let detail = '';
    try {
      const body = await response.json();
      if (typeof body?.detail === 'string') detail = body.detail;
      else if (typeof body?.error === 'string') detail = body.error;
    } catch {
      // Non-JSON error body (HTML error page, empty 502) — status alone it is.
    }
    return detail
      ? `${fallback} (HTTP ${response.status}): ${detail}`
      : `${fallback} (HTTP ${response.status})`;
  };

  const fetchControls = useCallback(async () => {
    try {
      const response = await fetchWithCsrf('/api/controls/controls', {
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        setLoadError(await describeFailure(response, 'Could not load controls'));
        setControls([]);
        return;
      }

      const data = await response.json();
      setLoadError(null);
      setControls(data.controls || []);
    } catch (error) {
      console.error('Failed to fetch controls:', error);
      setLoadError(
        error instanceof Error
          ? `Could not load controls: ${error.message}`
          : 'Could not load controls.',
      );
      setControls([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isHydrated) {
      return;
    }

    if (!isAuthenticated) {
      setLoading(false);
      return;
    }

    fetchControls();
  }, [fetchControls, isAuthenticated, isHydrated]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionError(null);
    try {
      const response = await fetchWithCsrf('/api/controls/controls', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData)
      });

      if (!response.ok) {
        setActionError(await describeFailure(response, 'Could not create control'));
        return;
      }

      setShowCreateForm(false);
      setFormData({ control_id: '', title: '', description: '', framework: 'FSMA 204' });
      fetchControls();
    } catch (error) {
      console.error('Failed to create control:', error);
      setActionError(
        error instanceof Error
          ? `Could not create control: ${error.message}`
          : 'Could not create control.',
      );
    }
  };

  const handleDelete = async (controlId: string) => {
    setActionError(null);
    try {
      const response = await fetchWithCsrf(`/api/controls/controls/${controlId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        setActionError(await describeFailure(response, 'Could not delete control'));
        return;
      }

      fetchControls();
    } catch (error) {
      console.error('Failed to delete control:', error);
      setActionError(
        error instanceof Error
          ? `Could not delete control: ${error.message}`
          : 'Could not delete control.',
      );
    } finally {
      setPendingDeleteId(null);
    }
  };

  if (!isHydrated || loading) {
    return (
      <PageContainer>
        <p className="py-16 text-center text-ui text-re-text-tertiary">Loading controls...</p>
      </PageContainer>
    );
  }

  if (!isAuthenticated) {
    return (
      <PageContainer>
        <p className="py-16 text-center text-ui text-re-text-tertiary">
          Sign in to view your controls.
        </p>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <PageHeader
        title="My Controls"
        primaryAction={
          <Button
            variant={showCreateForm ? 'secondary' : 'primary'}
            onClick={() => setShowCreateForm(!showCreateForm)}
          >
            {showCreateForm ? 'Cancel' : 'Create Control'}
          </Button>
        }
      />

      {loadError && (
        <Callout
          tone="danger"
          role="alert"
          className="mb-6"
          title="Controls unavailable"
          action={
            <Button
              variant="secondary"
              size="sm"
              onClick={() => { setLoading(true); fetchControls(); }}
            >
              Retry
            </Button>
          }
        >
          {loadError}
        </Callout>
      )}

      {actionError && (
        <Callout tone="danger" role="alert" className="mb-6">
          {actionError}
        </Callout>
      )}

      {showCreateForm && (
        <Card className="mb-8">
          <CardHeader>
            <h2 className="text-subheading text-re-text-primary">Create New Control</h2>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <Field label="Control ID" htmlFor="control-id">
                <Input
                  id="control-id"
                  type="text"
                  required
                  value={formData.control_id}
                  onChange={(e) => setFormData({ ...formData, control_id: e.target.value })}
                  placeholder="e.g., CSF-AC-1"
                />
              </Field>
              <Field label="Title" htmlFor="control-title">
                <Input
                  id="control-title"
                  type="text"
                  required
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  placeholder="e.g., Access Control Policy"
                />
              </Field>
              <Field label="Description" htmlFor="control-description">
                <textarea
                  id="control-description"
                  required
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className={cn(fieldControlClasses, 'h-24 py-2')}
                  placeholder="Detailed description of the control..."
                />
              </Field>
              <Field label="Standards" htmlFor="control-framework">
                <select
                  id="control-framework"
                  value={formData.framework}
                  onChange={(e) => setFormData({ ...formData, framework: e.target.value })}
                  className={fieldControlClasses}
                >
                  <option value="FSMA 204">FSMA 204</option>
                  <option value="FDA CTE">FDA CTE</option>
                  <option value="EPCIS 2.0">EPCIS 2.0</option>
                  <option value="GS1">GS1</option>
                </select>
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button type="submit">Create Control</Button>
                <Button type="button" variant="ghost" onClick={() => setShowCreateForm(false)}>
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* The column headers stay mounted even with no rows: an e2e spec asserts
          the "Control ID" columnheader is visible on an empty tenant. */}
      <div className="rounded-lg border border-re-border bg-re-surface-card">
        <Table className="min-w-[720px]">
          <TableHeader>
            <TableRow>
              <TableHead>Control ID</TableHead>
              <TableHead>Title</TableHead>
              <TableHead>Framework</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {controls.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={5}
                  className="py-12 text-center font-normal text-re-text-tertiary"
                >
                  {/* #2835 An empty list after a failed request is NOT an empty
                      state — say so rather than inviting the user to create a
                      control against a backend we could not reach. */}
                  {loadError
                    ? 'Controls could not be loaded. See the error above.'
                    : 'No controls found. Create your first control to get started.'}
                </TableCell>
              </TableRow>
            ) : (
              controls.map((control) => (
                <TableRow key={control.id}>
                  <TableCell className="font-mono text-[0.8125rem]">{control.control_id}</TableCell>
                  <TableCell>{control.title}</TableCell>
                  <TableCell>{control.framework}</TableCell>
                  <TableCell className="text-re-text-tertiary">
                    {new Date(control.created_at).toLocaleDateString()}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => router.push(`/controls/${control.id}`)}
                      >
                        View
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-re-danger hover:text-re-danger"
                        onClick={() => setPendingDeleteId(control.id)}
                      >
                        Delete
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={pendingDeleteId !== null} onOpenChange={(open) => { if (!open) setPendingDeleteId(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this control?</DialogTitle>
            <DialogDescription>
              This permanently removes the control and cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setPendingDeleteId(null)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={() => pendingDeleteId && handleDelete(pendingDeleteId)}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}
