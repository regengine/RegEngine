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
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
            {/* Header */}
            <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                    <div className="flex items-center justify-between">
                        <div>
                            <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 flex items-center gap-3">
                                <Key className="h-8 w-8 text-blue-600" />
                                API Keys
                            </h1>
                            <p className="text-gray-600 dark:text-gray-400 mt-2">
                                Generate and manage API keys for RegEngine verticals
                            </p>
                        </div>
                        <button
                            onClick={() => setShowNewKeyForm(true)}
                            className="px-6 py-3 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition-colors flex items-center gap-2"
                        >
                            <Key className="h-5 w-5" />
                            Create New Key
                        </button>
                    </div>
                </div>
            </div>

            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                <div className="mb-6 p-3 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 flex items-center gap-2 text-amber-800 dark:text-amber-200 text-sm">
                    <AlertTriangle className="h-4 w-4 shrink-0" />
                    <span>Demo Data — This page shows simulated keys and usage. Connect your backend and tenant context for production behavior.</span>
                </div>

                {/* New Key Form */}
                {showNewKeyForm && (
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 mb-8 border border-gray-200 dark:border-gray-700">
                        <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-4">
                            Create New API Key
                        </h2>

                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                    Key Name
                                </label>
                                <input
                                    type="text"
                                    value={formData.name}
                                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                    placeholder="e.g., Production Key, Development Key"
                                    className="w-full px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                    Vertical
                                </label>
                                <select
                                    value={formData.vertical}
                                    onChange={(e) => setFormData({ ...formData, vertical: e.target.value })}
                                    className="w-full px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                                >
                                    {verticals.map(v => (
                                        <option key={v.id} value={v.id}>{v.name}</option>
                                    ))}
                                </select>
                            </div>

                            <div className="flex gap-3">
                                <button
                                    onClick={handleCreateKey}
                                    className="px-6 py-2 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition-colors"
                                >
                                    Generate Key
                                </button>
                                <button
                                    onClick={() => setShowNewKeyForm(false)}
                                    className="px-6 py-2 bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-lg font-semibold hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
                                >
                                    Cancel
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* Quick Start */}
                {keys.length === 0 && !showNewKeyForm && (
                    <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-8 text-center">
                        <Key className="h-12 w-12 text-blue-600 dark:text-blue-400 mx-auto mb-4" />
                        <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-2">
                            No API Keys Yet
                        </h2>
                        <p className="text-gray-600 dark:text-gray-400 mb-6">
                            Create your first API key to start using RegEngine&apos;s compliance APIs
                        </p>
                        <button
                            onClick={() => setShowNewKeyForm(true)}
                            className="px-6 py-3 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition-colors inline-flex items-center gap-2"
                        >
                            <Key className="h-5 w-5" />
                            Create Your First Key
                        </button>
                    </div>
                )}

                {/* Keys List */}
                {keys.length > 0 && (
                    <div className="space-y-4">
                        <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
                            Your API Keys ({keys.length})
                        </h2>

                        {keys.map((apiKey) => {
                            const vertical = verticals.find(v => v.id === apiKey.vertical);
                            const Icon = vertical?.icon || Key;

                            return (
                                <div
                                    key={apiKey.id}
                                    className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700"
                                >
                                    <div className="flex items-start justify-between mb-4">
                                        <div className="flex items-center gap-3">
                                            <div className={`p-2 bg-${vertical?.color}-100 dark:bg-${vertical?.color}-900 rounded-lg`}>
                                                <Icon className={`h-6 w-6 text-${vertical?.color}-600 dark:text-${vertical?.color}-400`} />
                                            </div>
                                            <div>
                                                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                                                    {apiKey.name}
                                                </h3>
                                                <p className="text-sm text-gray-500 dark:text-gray-400">
                                                    {vertical?.name}
                                                </p>
                                            </div>
                                        </div>
                                        <button
                                            onClick={() => deleteKey(apiKey.id)}
                                            className="text-red-600 hover:text-red-800 text-sm font-medium"
                                        >
                                            Delete
                                        </button>
                                    </div>

                                    <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-4 font-mono text-sm flex items-center justify-between">
                                        <code className="text-gray-800 dark:text-gray-200">
                                            {apiKey.key}
                                        </code>
                                        <button
                                            onClick={() => copyToClipboard(apiKey.key)}
                                            className="ml-4 p-2 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-colors"
                                        >
                                            {copiedKey === apiKey.key ? (
                                                <Check className="h-5 w-5 text-green-600" />
                                            ) : (
                                                <Copy className="h-5 w-5 text-gray-600 dark:text-gray-400" />
                                            )}
                                        </button>
                                    </div>

                                    <div className="mt-4 flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
                                        <span>Created: {new Date(apiKey.created).toLocaleDateString()}</span>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}

                {/* Documentation */}
                <div className="mt-12 bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-4">
                        Using Your API Key
                    </h2>

                    <div className="space-y-6">
                        <div>
                            <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                Authentication
                            </h3>
                            <div className="bg-gray-900 dark:bg-black rounded-lg p-4 font-mono text-sm text-green-400">
                                <code>{`curl -X POST https://www.regengine.co/api/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: YOUR_API_KEY" \\
  -H "X-Tenant-ID: YOUR_TENANT_UUID" \\
  -H "Content-Type: application/json"`}</code>
                            </div>
                        </div>

                        <div>
                            <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                Security Best Practices
                            </h3>
                            <ul className="list-disc list-inside space-y-2 text-gray-600 dark:text-gray-400">
                                <li>Never commit API keys to version control</li>
                                <li>Use environment variables for production</li>
                                <li>Rotate keys regularly</li>
                                <li>Use separate keys for development and production</li>
                                <li>Delete unused keys immediately</li>
                            </ul>
                        </div>
                    </div>

                    <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
                        <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-3">
                            Next Steps
                        </h3>
                        <div className="grid md:grid-cols-2 gap-4">
                            <Link
                                href="/docs/fsma-204"
                                className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-blue-500 transition-colors"
                            >
                                <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                                    FSMA 204 Guide
                                </h4>
                                <p className="text-sm text-gray-600 dark:text-gray-400">
                                    API documentation and compliance reference
                                </p>
                            </Link>
                            <Link
                                href="/docs"
                                className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-blue-500 transition-colors"
                            >
                                <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                                    Read Documentation
                                </h4>
                                <p className="text-sm text-gray-600 dark:text-gray-400">
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
