'use client';

import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '@/lib/auth-context';
import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Key, Plus, Copy, Trash2, Check, Loader2 } from 'lucide-react';

interface ApiKey {
    id: string;
    name: string;
    key_prefix: string;
    enabled: boolean;
    total_requests: number;
    created_at: string;
    last_used_at: string | null;
    revoked_at: string | null;
}

export default function ApiKeysPage() {
    const { user: authUser } = useAuth();
    const [keys, setKeys] = useState<ApiKey[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isCreating, setIsCreating] = useState(false);
    const [newKeyName, setNewKeyName] = useState('');
    const [showCreate, setShowCreate] = useState(false);
    const [revealedKey, setRevealedKey] = useState<string | null>(null);
    const [copied, setCopied] = useState(false);
    const [developerId, setDeveloperId] = useState<string | null>(null);

    const loadKeys = useCallback(async () => {
        if (!authUser) return;

        const response = await fetch('/api/developer/portal/keys', { credentials: 'include' });
        if (!response.ok) {
            setIsLoading(false);
            return;
        }
        const data = await response.json();
        setDeveloperId(data.developerId);
        setKeys(data.keys || []);
        setIsLoading(false);
    }, [authUser]);

    useEffect(() => { loadKeys(); }, [loadKeys]);

    async function createKey() {
        if (!developerId || !newKeyName.trim()) return;
        setIsCreating(true);

        const response = await fetchWithCsrf('/api/developer/portal/keys', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ name: newKeyName.trim() }),
        });

        if (response.ok) {
            const data = await response.json();
            setRevealedKey(data.rawKey);
            setNewKeyName('');
            setShowCreate(false);
            setKeys(data.keys || []);
        }

        setIsCreating(false);
    }

    async function revokeKey(keyId: string) {
        await fetchWithCsrf(`/api/developer/portal/keys/${encodeURIComponent(keyId)}`, {
            method: 'DELETE',
            credentials: 'include',
        });
        await loadKeys();
    }

    function copyKey() {
        if (revealedKey) {
            navigator.clipboard.writeText(revealedKey);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    }

    if (isLoading) {
        return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin" style={{ color: 'var(--re-text-muted)' }} /></div>;
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold" style={{ color: 'var(--re-text-primary)' }}>API Keys</h1>
                    <p className="text-sm mt-1" style={{ color: 'var(--re-text-muted)' }}>
                        Generate and manage your API keys. Keys are shown once — store them securely.
                    </p>
                </div>
                <Button
                    onClick={() => setShowCreate(true)}
                    style={{ background: 'var(--re-brand)', color: '#000', fontWeight: 600 }}
                >
                    <Plus className="w-4 h-4 mr-2" /> New Key
                </Button>
            </div>

            {/* Revealed key banner */}
            {revealedKey && (
                <Card style={{ background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.3)' }}>
                    <CardContent className="py-4">
                        <p className="text-sm font-medium mb-2" style={{ color: 'var(--re-brand)' }}>
                            Your new API key (copy it now — it won't be shown again):
                        </p>
                        <div className="flex items-center gap-2">
                            <code className="flex-1 text-xs font-mono px-3 py-2 rounded" style={{ background: 'rgba(0,0,0,0.3)', color: 'var(--re-text-primary)' }}>
                                {revealedKey}
                            </code>
                            <Button variant="outline" size="sm" onClick={copyKey}>
                                {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                            </Button>
                        </div>
                        <Button
                            variant="ghost"
                            size="sm"
                            className="mt-2 text-xs"
                            onClick={() => setRevealedKey(null)}
                            style={{ color: 'var(--re-text-muted)' }}
                        >
                            Dismiss
                        </Button>
                    </CardContent>
                </Card>
            )}

            {/* Create key form */}
            {showCreate && (
                <Card style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                    <CardContent className="py-4">
                        <div className="flex items-end gap-3">
                            <div className="flex-1">
                                <label className="text-xs font-medium mb-1 block" style={{ color: 'var(--re-text-muted)' }}>Key Name</label>
                                <Input
                                    placeholder="e.g. Production, Staging, CI/CD"
                                    value={newKeyName}
                                    onChange={(e) => setNewKeyName(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && createKey()}
                                    style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}
                                />
                            </div>
                            <Button
                                onClick={createKey}
                                disabled={!newKeyName.trim() || isCreating}
                                style={{ background: 'var(--re-brand)', color: '#000', fontWeight: 600 }}
                            >
                                {isCreating ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                                Generate
                            </Button>
                            <Button variant="ghost" onClick={() => { setShowCreate(false); setNewKeyName(''); }}>
                                Cancel
                            </Button>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Keys list */}
            <div className="space-y-2">
                {keys.length === 0 ? (
                    <Card style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                        <CardContent className="py-12 text-center">
                            <Key className="w-8 h-8 mx-auto mb-3" style={{ color: 'var(--re-text-disabled)' }} />
                            <p className="text-sm" style={{ color: 'var(--re-text-muted)' }}>No API keys yet. Create one to get started.</p>
                        </CardContent>
                    </Card>
                ) : (
                    keys.map((key) => (
                        <Card key={key.id} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                            <CardContent className="flex items-center gap-4 py-3">
                                <Key className="w-4 h-4 flex-shrink-0" style={{ color: key.enabled ? 'var(--re-brand)' : 'var(--re-text-disabled)' }} />
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <p className="text-sm font-medium truncate" style={{ color: 'var(--re-text-primary)' }}>{key.name}</p>
                                        <Badge variant={key.enabled ? 'default' : 'secondary'} className="text-xs">
                                            {key.enabled ? 'Active' : 'Revoked'}
                                        </Badge>
                                    </div>
                                    <p className="text-xs font-mono" style={{ color: 'var(--re-text-disabled)' }}>
                                        {key.key_prefix}••••••••
                                    </p>
                                </div>
                                <div className="text-right flex-shrink-0">
                                    <p className="text-xs" style={{ color: 'var(--re-text-muted)' }}>{key.total_requests.toLocaleString()} requests</p>
                                    <p className="text-xs" style={{ color: 'var(--re-text-disabled)' }}>
                                        {key.last_used_at ? `Last used ${new Date(key.last_used_at).toLocaleDateString()}` : 'Never used'}
                                    </p>
                                </div>
                                {key.enabled && (
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => revokeKey(key.id)}
                                        className="text-re-danger hover:text-re-danger hover:bg-re-danger/10"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </Button>
                                )}
                            </CardContent>
                        </Card>
                    ))
                )}
            </div>
        </div>
    );
}
