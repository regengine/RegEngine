'use client';

import { useState } from 'react';
import { AlertTriangle, Key, Copy, Check, RefreshCw, UtensilsCrossed } from 'lucide-react';
import Link from 'next/link';

export default function APIKeysPage() {
    const [keys, setKeys] = useState<Array<{ id: string; name: string; key: string; vertical: string; created: string }>>([]);
    const [showNewKeyForm, setShowNewKeyForm] = useState(false);
    const [copiedKey, setCopiedKey] = useState<string | null>(null);
    const [formData, setFormData] = useState({ name: '', vertical: 'fsma204' });

    const verticals = [
        { id: 'fsma204', name: 'Food & Beverage (FSMA 204)', icon: UtensilsCrossed, color: 'emerald' },
    ];

    const generateKey = () => {
        const timestamp = Date.now();
        const random = Math.random().toString(36).substring(2, 15);
        const prefix = formData.vertical.substring(0, 3);
        return `rge_${prefix}_${timestamp}_${random}`;
    };

    const handleCreateKey = () => {
        if (!formData.name.trim()) {
            alert('Please enter a key name');
            return;
        }

        const newKey = {
            id: Math.random().toString(36).substring(7),
            name: formData.name,
            key: generateKey(),
            vertical: formData.vertical,
            created: new Date().toISOString(),
        };

        setKeys([newKey, ...keys]);
        setFormData({ name: '', vertical: 'fsma204' });
        setShowNewKeyForm(false);
    };

    const copyToClipboard = (key: string) => {
        navigator.clipboard.writeText(key);
        setCopiedKey(key);
        setTimeout(() => setCopiedKey(null), 2000);
    };

    const deleteKey = (id: string) => {
        if (confirm('Are you sure? This action cannot be undone.')) {
            setKeys(keys.filter(k => k.id !== id));
        }
    };

    return (
        <div className="min-h-screen bg-re-surface-card dark:bg-re-surface-base">
            {/* Header */}
            <div className="bg-white dark:bg-re-surface-card border-b border-re-border dark:border-re-border">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                    <div className="flex items-center justify-between">
                        <div>
                            <h1 className="text-3xl font-bold text-re-text-primary dark:text-re-text-primary flex items-center gap-3">
                                <Key className="h-8 w-8 text-re-info" />
                                API Keys
                            </h1>
                            <p className="text-re-text-disabled dark:text-re-text-tertiary mt-2">
                                Generate and manage API keys for RegEngine verticals
                            </p>
                        </div>
                        <button
                            onClick={() => setShowNewKeyForm(true)}
                            className="px-6 py-3 bg-re-info text-white rounded-lg font-semibold hover:bg-re-info transition-colors flex items-center gap-2"
                        >
                            <Key className="h-5 w-5" />
                            Create New Key
                        </button>
                    </div>
                </div>
            </div>

            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                <div className="mb-6 p-3 rounded-lg bg-re-warning-muted dark:bg-re-warning/20 border border-amber-200 dark:border-amber-800 flex items-center gap-2 text-re-warning dark:text-re-warning text-sm">
                    <AlertTriangle className="h-4 w-4 shrink-0" />
                    <span>Simulated keys — connect your backend to manage real API keys.</span>
                </div>

                {/* New Key Form */}
                {showNewKeyForm && (
                    <div className="bg-white dark:bg-re-surface-card rounded-lg shadow-lg p-6 mb-8 border border-re-border dark:border-re-border">
                        <h2 className="text-xl font-bold text-re-text-primary dark:text-re-text-primary mb-4">
                            Create New API Key
                        </h2>

                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-re-text-disabled dark:text-re-text-secondary mb-2">
                                    Key Name
                                </label>
                                <input
                                    type="text"
                                    value={formData.name}
                                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                    placeholder="e.g., Production Key, Development Key"
                                    className="w-full px-4 py-2 rounded-lg border border-re-border dark:border-re-border bg-white dark:bg-re-surface-elevated text-re-text-primary dark:text-re-text-primary"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-re-text-disabled dark:text-re-text-secondary mb-2">
                                    Vertical
                                </label>
                                <select
                                    value={formData.vertical}
                                    onChange={(e) => setFormData({ ...formData, vertical: e.target.value })}
                                    className="w-full px-4 py-2 rounded-lg border border-re-border dark:border-re-border bg-white dark:bg-re-surface-elevated text-re-text-primary dark:text-re-text-primary"
                                >
                                    {verticals.map(v => (
                                        <option key={v.id} value={v.id}>{v.name}</option>
                                    ))}
                                </select>
                            </div>

                            <div className="flex gap-3">
                                <button
                                    onClick={handleCreateKey}
                                    className="px-6 py-2 bg-re-info text-white rounded-lg font-semibold hover:bg-re-info transition-colors"
                                >
                                    Generate Key
                                </button>
                                <button
                                    onClick={() => setShowNewKeyForm(false)}
                                    className="px-6 py-2 bg-re-surface-elevated dark:bg-re-surface-elevated text-re-text-primary dark:text-re-text-primary rounded-lg font-semibold hover:bg-re-surface-elevated dark:hover:bg-re-surface-elevated transition-colors"
                                >
                                    Cancel
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* Quick Start */}
                {keys.length === 0 && !showNewKeyForm && (
                    <div className="bg-re-info-muted dark:bg-re-info/20 border border-blue-200 dark:border-blue-800 rounded-lg p-8 text-center">
                        <Key className="h-12 w-12 text-re-info dark:text-re-info mx-auto mb-4" />
                        <h2 className="text-xl font-bold text-re-text-primary dark:text-re-text-primary mb-2">
                            No API Keys Yet
                        </h2>
                        <p className="text-re-text-disabled dark:text-re-text-tertiary mb-6">
                            Create your first API key to start using RegEngine&apos;s compliance APIs
                        </p>
                        <button
                            onClick={() => setShowNewKeyForm(true)}
                            className="px-6 py-3 bg-re-info text-white rounded-lg font-semibold hover:bg-re-info transition-colors inline-flex items-center gap-2"
                        >
                            <Key className="h-5 w-5" />
                            Create Your First Key
                        </button>
                    </div>
                )}

                {/* Keys List */}
                {keys.length > 0 && (
                    <div className="space-y-4">
                        <h2 className="text-xl font-bold text-re-text-primary dark:text-re-text-primary">
                            Your API Keys ({keys.length})
                        </h2>

                        {keys.map((apiKey) => {
                            const vertical = verticals.find(v => v.id === apiKey.vertical);
                            const Icon = vertical?.icon || Key;

                            return (
                                <div
                                    key={apiKey.id}
                                    className="bg-white dark:bg-re-surface-card rounded-lg shadow p-6 border border-re-border dark:border-re-border"
                                >
                                    <div className="flex items-start justify-between mb-4">
                                        <div className="flex items-center gap-3">
                                            <div className={`p-2 bg-${vertical?.color}-100 dark:bg-${vertical?.color}-900 rounded-lg`}>
                                                <Icon className={`h-6 w-6 text-${vertical?.color}-600 dark:text-${vertical?.color}-400`} />
                                            </div>
                                            <div>
                                                <h3 className="text-lg font-semibold text-re-text-primary dark:text-re-text-primary">
                                                    {apiKey.name}
                                                </h3>
                                                <p className="text-sm text-re-text-muted dark:text-re-text-tertiary">
                                                    {vertical?.name}
                                                </p>
                                            </div>
                                        </div>
                                        <button
                                            onClick={() => deleteKey(apiKey.id)}
                                            className="text-re-danger hover:text-re-danger text-sm font-medium"
                                        >
                                            Delete
                                        </button>
                                    </div>

                                    <div className="bg-re-surface-card dark:bg-re-surface-base rounded-lg p-4 font-mono text-sm flex items-center justify-between">
                                        <code className="text-re-text-primary dark:text-re-text-primary">
                                            {apiKey.key}
                                        </code>
                                        <button
                                            onClick={() => copyToClipboard(apiKey.key)}
                                            className="ml-4 p-2 hover:bg-re-surface-elevated dark:hover:bg-re-surface-elevated rounded transition-colors"
                                        >
                                            {copiedKey === apiKey.key ? (
                                                <Check className="h-5 w-5 text-re-success" />
                                            ) : (
                                                <Copy className="h-5 w-5 text-re-text-disabled dark:text-re-text-tertiary" />
                                            )}
                                        </button>
                                    </div>

                                    <div className="mt-4 flex items-center gap-4 text-sm text-re-text-muted dark:text-re-text-tertiary">
                                        <span>Created: {new Date(apiKey.created).toLocaleDateString()}</span>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}

                {/* Documentation */}
                <div className="mt-12 bg-white dark:bg-re-surface-card rounded-lg shadow p-6 border border-re-border dark:border-re-border">
                    <h2 className="text-xl font-bold text-re-text-primary dark:text-re-text-primary mb-4">
                        Using Your API Key
                    </h2>

                    <div className="space-y-6">
                        <div>
                            <h3 className="font-semibold text-re-text-primary dark:text-re-text-primary mb-2">
                                Authentication
                            </h3>
                            <div className="bg-re-surface-base dark:bg-black rounded-lg p-4 font-mono text-sm text-re-success">
                                <code>{`curl -X POST https://regengine.co/api/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: YOUR_API_KEY" \\
  -H "X-Tenant-ID: YOUR_TENANT_UUID" \\
  -H "Content-Type: application/json"`}</code>
                            </div>
                        </div>

                        <div>
                            <h3 className="font-semibold text-re-text-primary dark:text-re-text-primary mb-2">
                                Security Best Practices
                            </h3>
                            <ul className="list-disc list-inside space-y-2 text-re-text-disabled dark:text-re-text-tertiary">
                                <li>Never commit API keys to version control</li>
                                <li>Use environment variables for production</li>
                                <li>Rotate keys regularly</li>
                                <li>Use separate keys for development and production</li>
                                <li>Delete unused keys immediately</li>
                            </ul>
                        </div>
                    </div>

                    <div className="mt-6 pt-6 border-t border-re-border dark:border-re-border">
                        <h3 className="font-semibold text-re-text-primary dark:text-re-text-primary mb-3">
                            Next Steps
                        </h3>
                        <div className="grid md:grid-cols-2 gap-4">
                            <Link
                                href="/docs/fsma-204"
                                className="p-4 border border-re-border dark:border-re-border rounded-lg hover:border-re-info transition-colors"
                            >
                                <h4 className="font-semibold text-re-text-primary dark:text-re-text-primary mb-1">
                                    FSMA 204 Guide
                                </h4>
                                <p className="text-sm text-re-text-disabled dark:text-re-text-tertiary">
                                    API documentation and compliance reference
                                </p>
                            </Link>
                            <Link
                                href="/docs"
                                className="p-4 border border-re-border dark:border-re-border rounded-lg hover:border-re-info transition-colors"
                            >
                                <h4 className="font-semibold text-re-text-primary dark:text-re-text-primary mb-1">
                                    Read Documentation
                                </h4>
                                <p className="text-sm text-re-text-disabled dark:text-re-text-tertiary">
                                    Get started with quickstart guides
                                </p>
                            </Link>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
