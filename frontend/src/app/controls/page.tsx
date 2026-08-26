'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { Button } from '@/components/ui/button';
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
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl">Loading controls...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl">Sign in to view your controls.</div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold">My Controls</h1>
        <button
          onClick={() => setShowCreateForm(!showCreateForm)}
          className="bg-re-info hover:bg-re-info text-white px-6 py-2 rounded-lg transition"
        >
          {showCreateForm ? 'Cancel' : 'Create Control'}
        </button>
      </div>

      {loadError && (
        <div
          role="alert"
          className="mb-6 rounded-lg border border-re-danger bg-re-danger-muted px-4 py-3 text-sm text-re-danger"
        >
          <p className="font-semibold">Controls unavailable</p>
          <p>{loadError}</p>
          <button
            type="button"
            onClick={() => { setLoading(true); fetchControls(); }}
            className="mt-2 underline underline-offset-2"
          >
            Retry
          </button>
        </div>
      )}

      {actionError && (
        <div
          role="alert"
          className="mb-6 rounded-lg border border-re-danger bg-re-danger-muted px-4 py-3 text-sm text-re-danger"
        >
          {actionError}
        </div>
      )}

      {showCreateForm && (
        <div className="bg-white shadow-lg rounded-lg p-6 mb-8">
          <h2 className="text-2xl font-semibold mb-4">Create New Control</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Control ID</label>
              <input
                type="text"
                required
                value={formData.control_id}
                onChange={(e) => setFormData({ ...formData, control_id: e.target.value })}
                className="w-full border border-re-border rounded-lg px-4 py-2"
                placeholder="e.g., CSF-AC-1"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Title</label>
              <input
                type="text"
                required
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                className="w-full border border-re-border rounded-lg px-4 py-2"
                placeholder="e.g., Access Control Policy"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Description</label>
              <textarea
                required
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full border border-re-border rounded-lg px-4 py-2 h-24"
                placeholder="Detailed description of the control..."
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Standards</label>
              <select
                value={formData.framework}
                onChange={(e) => setFormData({ ...formData, framework: e.target.value })}
                className="w-full border border-re-border rounded-lg px-4 py-2"
              >
                <option value="FSMA 204">FSMA 204</option>
                <option value="FDA CTE">FDA CTE</option>
                <option value="EPCIS 2.0">EPCIS 2.0</option>
                <option value="GS1">GS1</option>
              </select>
            </div>
            <div className="flex gap-4">
              <button
                type="submit"
                className="bg-re-info hover:bg-re-info text-white px-6 py-2 rounded-lg transition"
              >
                Create Control
              </button>
              <button
                type="button"
                onClick={() => setShowCreateForm(false)}
                className="bg-re-surface-elevated hover:bg-re-surface-elevated text-re-text-primary px-6 py-2 rounded-lg transition"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="bg-white shadow-lg rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-re-surface-card">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-re-text-muted uppercase tracking-wider">
                Control ID
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-re-text-muted uppercase tracking-wider">
                Title
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-re-text-muted uppercase tracking-wider">
                Framework
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-re-text-muted uppercase tracking-wider">
                Created
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-re-text-muted uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {controls.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-12 text-center text-re-text-muted">
                  {/* #2835 An empty list after a failed request is NOT an empty
                      state — say so rather than inviting the user to create a
                      control against a backend we could not reach. */}
                  {loadError
                    ? 'Controls could not be loaded. See the error above.'
                    : 'No controls found. Create your first control to get started.'}
                </td>
              </tr>
            ) : (
              controls.map((control) => (
                <tr key={control.id} className="hover:bg-re-surface-card">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-re-text-primary">
                    {control.control_id}
                  </td>
                  <td className="px-6 py-4 text-sm text-re-text-primary">
                    {control.title}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-re-text-muted">
                    {control.framework}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-re-text-muted">
                    {new Date(control.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => router.push(`/controls/${control.id}`)}
                      className="text-re-info hover:text-re-info mr-4"
                    >
                      View
                    </button>
                    <button
                      onClick={() => setPendingDeleteId(control.id)}
                      className="text-re-danger hover:text-re-danger"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        </div>
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
            <Button variant="outline" onClick={() => setPendingDeleteId(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => pendingDeleteId && handleDelete(pendingDeleteId)}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
