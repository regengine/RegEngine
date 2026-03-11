'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';

interface Control {
  id: string;
  control_id: string;
  title: string;
  description: string;
  framework: string;
  created_at: string;
}

export default function MyControlsPage() {
  const { apiKey, isLoggedIn } = useAuth();
  const [controls, setControls] = useState<Control[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [formData, setFormData] = useState({
    control_id: '',
    title: '',
    description: '',
    framework: 'NIST CSF'
  });
  const router = useRouter();

  useEffect(() => {
    fetchControls();
  }, []);

  const fetchControls = async () => {
    try {
      const response = await fetch('/api/controls/controls', {
        headers: {
          'X-RegEngine-API-Key': apiKey || ''
        }
      });
      const data = await response.json();
      setControls(data.controls || []);
    } catch (error) {
      console.error('Failed to fetch controls:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const response = await fetch('/api/controls/controls', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-RegEngine-API-Key': apiKey || ''
        },
        body: JSON.stringify(formData)
      });

      if (response.ok) {
        setShowCreateForm(false);
        setFormData({ control_id: '', title: '', description: '', framework: 'NIST CSF' });
        fetchControls();
      }
    } catch (error) {
      console.error('Failed to create control:', error);
    }
  };

  const handleDelete = async (controlId: string) => {
    if (!confirm('Are you sure you want to delete this control?')) return;

    try {
      await fetch(`/api/controls/controls/${controlId}`, {
        method: 'DELETE',
        headers: {
          'X-RegEngine-API-Key': apiKey || ''
        }
      });
      fetchControls();
    } catch (error) {
      console.error('Failed to delete control:', error);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-xl">Loading controls...</div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold">My Controls</h1>
        <button
          onClick={() => setShowCreateForm(!showCreateForm)}
          className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg transition"
        >
          {showCreateForm ? 'Cancel' : 'Create Control'}
        </button>
      </div>

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
                className="w-full border border-gray-300 rounded-lg px-4 py-2"
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
                className="w-full border border-gray-300 rounded-lg px-4 py-2"
                placeholder="e.g., Access Control Policy"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Description</label>
              <textarea
                required
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-4 py-2 h-24"
                placeholder="Detailed description of the control..."
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Framework</label>
              <select
                value={formData.framework}
                onChange={(e) => setFormData({ ...formData, framework: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-4 py-2"
              >
                <option value="FSMA 204">FSMA 204</option>
                <option value="EPCIS 2.0">EPCIS 2.0</option>
                <option value="GS1">GS1</option>
                <option value="FDA CTE">FDA CTE</option>
              </select>
            </div>
            <div className="flex gap-4">
              <button
                type="submit"
                className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg transition"
              >
                Create Control
              </button>
              <button
                type="button"
                onClick={() => setShowCreateForm(false)}
                className="bg-gray-300 hover:bg-gray-400 text-gray-800 px-6 py-2 rounded-lg transition"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="bg-white shadow-lg rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Control ID
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Title
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Framework
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Created
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {controls.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-12 text-center text-gray-500">
                  No controls found. Create your first control to get started.
                </td>
              </tr>
            ) : (
              controls.map((control) => (
                <tr key={control.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    {control.control_id}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-900">
                    {control.title}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {control.framework}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {new Date(control.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => router.push(`/controls/${control.id}`)}
                      className="text-blue-600 hover:text-blue-900 mr-4"
                    >
                      View
                    </button>
                    <button
                      onClick={() => handleDelete(control.id)}
                      className="text-red-600 hover:text-red-900"
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
  );
}
