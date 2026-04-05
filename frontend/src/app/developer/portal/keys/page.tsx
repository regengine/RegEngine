'use client';

import { useEffect, useState, useCallback } from 'react';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { useAuth } from '@/lib/auth-context';
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

function generateApiKey(): string {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let result = 'rge_dev_';
    for (let i = 0; i < 32; i++) {
        result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
}

async function hashKey(key: string): Promise<string> {
    const encoder = new TextEncoder();
    const data = encoder.encode(key);
    const hash = await crypto.subtle.digest('SHA-256', data);
    return Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2, '0')).join('');
}

export default function ApiKeysPage() {
    const supabase = createSupabaseBrowserClient();
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

        const { data: profile, error: profileError } = await supabase
            .from('developer_profiles')
            .select('id')
            .eq('auth_user_id', authUser.id)
            .maybeSingle();

        if (profileError && process.env.NODE_ENV !== 'production') {
            console.error('Failed to fetch developer profile:', profileError.message);
        }
        if (!profile) return;
        setDeveloperId(profile.id);

        const { data, error } = await supabase
            .from('developer_api_keys')
            .select('*')
            .eq('developer_id', profile.id)
            .order('created_at', { ascending: false });

        if (error && process.env.NODE_ENV !== 'production') {
            console.error('Failed to fetch API keys:', error.message);
        }
        setKeys(data || []);
        setIsLoading(false);
    }, [supabase, authUser]);

    useEffect(() => { loadKeys(); }, [loadKeys]);

    async function createKey() {
        if (!developerId || !newKeyName.trim()) return;
        setIsCreating(true);

        const rawKey = generateApiKey();
        const keyHash = await hashKey(rawKey);
        const keyPrefix = rawKey.substring(0, 12);

        const { error } = await supabase
            .from('developer_api_keys')
            .insert({
                developer_id: developerId,
                name: newKeyName.trim(),
                key_prefix: keyPrefix,
                key_hash: keyHash,
                scopes: ['read', 'write'],
            });

        if (!error) {
            setRevealedKey(rawKey);
            setNewKeyName('');
            setShowCreate(false);
            await loadKeys();
        }

        setIsCreating(false);
    }

    async function revokeKey(keyId: string) {
        await supabase
            .from('developer_api_keys')
            .update({ enabled: false, revoked_at: new Date().toISOString() })
            .eq('id', keyId);
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
                                        className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
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
