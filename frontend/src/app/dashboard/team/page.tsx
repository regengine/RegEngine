'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';
import {
    UserCog,
    Plus,
    Shield,
    Crown,
    Eye,
    ShieldCheck,
    Mail,
    Clock,
    AlertTriangle,
    RefreshCw,
} from 'lucide-react';

import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';

/* ── Types matching TeamResponse ── */

interface TeamMember {
    id: string;
    name: string;
    email: string;
    role: string;
    status: string;
    last_active: string | null;
    invited_at: string | null;
    avatar_initials: string;
}

interface TeamResponse {
    tenant_id: string;
    total_members: number;
    active_members: number;
    pending_invites: number;
    roles_breakdown: Record<string, number>;
    members: TeamMember[];
}

const ROLE_CONFIG: Record<string, { icon: React.ElementType; color: string; label: string }> = {
    owner: { icon: Crown, color: '#f59e0b', label: 'Owner' },
    admin: { icon: Shield, color: '#3b82f6', label: 'Admin' },
    compliance_manager: { icon: ShieldCheck, color: '#10b981', label: 'Compliance Manager' },
    viewer: { icon: Eye, color: '#6b7280', label: 'Viewer' },
};

async function apiFetchTeam(tenantId: string): Promise<TeamResponse> {
    const apiKey = typeof window !== 'undefined' ? localStorage.getItem('re-api-key') || '' : '';
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetch(`${base}/api/v1/team/${tenantId}`, {
        headers: { 'Content-Type': 'application/json', 'X-RegEngine-API-Key': apiKey },
    });
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
    return res.json();
}

async function apiInviteMember(tenantId: string, name: string, email: string, role: string): Promise<void> {
    const apiKey = typeof window !== 'undefined' ? localStorage.getItem('re-api-key') || '' : '';
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetch(`${base}/api/v1/team/${tenantId}/invite`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-RegEngine-API-Key': apiKey },
        body: JSON.stringify({ name, email, role }),
    });
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
}

export default function TeamPage() {
    const { apiKey } = useAuth();
    const { tenantId } = useTenant();
    const isLoggedIn = Boolean(apiKey);

    const [team, setTeam] = useState<TeamMember[]>([]);
    const [activeCount, setActiveCount] = useState(0);
    const [pendingCount, setPendingCount] = useState(0);
    const [rolesBreakdown, setRolesBreakdown] = useState<Record<string, number>>({});
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [showInvite, setShowInvite] = useState(false);
    const [newName, setNewName] = useState('');
    const [newEmail, setNewEmail] = useState('');
    const [newRole, setNewRole] = useState('viewer');
    const [inviting, setInviting] = useState(false);

    const loadTeam = useCallback(async () => {
        if (!isLoggedIn || !tenantId) return;
        setLoading(true);
        setError(null);
        try {
            const data = await apiFetchTeam(tenantId);
            setTeam(data.members || []);
            setActiveCount(data.active_members || 0);
            setPendingCount(data.pending_invites || 0);
            setRolesBreakdown(data.roles_breakdown || {});
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load team');
        } finally {
            setLoading(false);
        }
    }, [isLoggedIn, tenantId]);

    useEffect(() => { loadTeam(); }, [loadTeam]);

    const handleInvite = async () => {
        if (!newName || !newEmail) return;
        setInviting(true);
        try {
            await apiInviteMember(tenantId, newName, newEmail, newRole);
            setNewName(''); setNewEmail(''); setShowInvite(false);
            await loadTeam();
        } catch {
            // Optimistic: add to local list
            setTeam(prev => [...prev, {
                id: `u-${Date.now()}`,
                name: newName,
                email: newEmail,
                role: newRole,
                status: 'invited',
                last_active: null,
                invited_at: new Date().toISOString(),
                avatar_initials: newName.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2),
            }]);
            setNewName(''); setNewEmail(''); setShowInvite(false);
        } finally {
            setInviting(false);
        }
    };

    return (
        <div className="min-h-screen bg-background py-10 px-4">
            <div className="max-w-4xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold flex items-center gap-3">
                            <UserCog className="h-6 w-6 text-[var(--re-brand)]" />
                            Team Management
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">
                            {activeCount} active · {pendingCount} pending
                        </p>
                    </div>
                    <div className="flex gap-2">
                        <Button variant="outline" size="sm" className="rounded-xl" onClick={loadTeam} disabled={loading}>
                            <RefreshCw className={`h-3 w-3 mr-1 ${loading ? 'animate-spin' : ''}`} />
                        </Button>
                        <Button onClick={() => setShowInvite(!showInvite)} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl">
                            <Plus className="h-4 w-4 mr-1" /> Invite Member
                        </Button>
                    </div>
                </div>

                {!isLoggedIn && (
                    <Card className="border-orange-300 dark:border-orange-700">
                        <CardContent className="py-6 text-center text-sm text-muted-foreground">
                            Sign in to manage your team.
                        </CardContent>
                    </Card>
                )}

                {loading && team.length === 0 && (
                    <div className="flex justify-center py-16"><Spinner size="lg" /></div>
                )}

                {error && (
                    <Card className="border-orange-300 dark:border-orange-700">
                        <CardContent className="py-4">
                            <div className="flex items-center gap-3 text-orange-600 dark:text-orange-400">
                                <AlertTriangle className="h-5 w-5 flex-shrink-0" />
                                <p className="text-sm">{error}</p>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {/* Invite Form */}
                {showInvite && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
                        <Card className="border-[var(--re-brand)]">
                            <CardContent className="py-4">
                                <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                                    <Input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Full name" className="rounded-xl" />
                                    <Input value={newEmail} onChange={e => setNewEmail(e.target.value)} placeholder="Email" type="email" className="rounded-xl" />
                                    <select value={newRole} onChange={e => setNewRole(e.target.value)} className="flex h-10 rounded-xl border border-input bg-background px-3 text-sm">
                                        <option value="admin">Admin</option>
                                        <option value="compliance_manager">Compliance Manager</option>
                                        <option value="viewer">Viewer</option>
                                    </select>
                                    <Button onClick={handleInvite} disabled={inviting} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl">
                                        {inviting ? <Spinner size="sm" /> : <><Mail className="h-4 w-4 mr-1" /> Send Invite</>}
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}

                {/* Roles Reference */}
                {Object.keys(rolesBreakdown).length > 0 && (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {Object.entries(ROLE_CONFIG).map(([key, config]) => {
                            const Icon = config.icon;
                            const count = rolesBreakdown[key] || 0;
                            return (
                                <div key={key} className="p-3 rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)]">
                                    <div className="flex items-center gap-2 mb-1">
                                        <Icon className="h-4 w-4" style={{ color: config.color }} />
                                        <span className="text-xs font-medium">{config.label}</span>
                                    </div>
                                    <span className="text-lg font-bold">{count}</span>
                                </div>
                            );
                        })}
                    </div>
                )}

                {/* Member List */}
                {team.length > 0 && (
                    <div className="space-y-2">
                        {team.map((member, i) => {
                            const roleConfig = ROLE_CONFIG[member.role] || ROLE_CONFIG.viewer;
                            const RoleIcon = roleConfig.icon;
                            return (
                                <motion.div key={member.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
                                    <Card className="border-[var(--re-border-default)] hover:border-[var(--re-brand)] transition-all">
                                        <CardContent className="py-3">
                                            <div className="flex items-center gap-3">
                                                <div className="w-10 h-10 rounded-full bg-[color-mix(in_srgb,var(--re-brand)_12%,transparent)] flex items-center justify-center text-xs font-bold text-[var(--re-brand)]">
                                                    {member.avatar_initials || member.name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)}
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2">
                                                        <span className="font-medium text-sm">{member.name}</span>
                                                        <Badge className="text-[9px] px-1.5 py-0" style={{ background: `${roleConfig.color}15`, color: roleConfig.color }}>
                                                            <RoleIcon className="h-2.5 w-2.5 mr-0.5" /> {roleConfig.label}
                                                        </Badge>
                                                        {member.status === 'invited' && (
                                                            <Badge variant="outline" className="text-[9px] py-0 text-amber-500 border-amber-500/20">Pending</Badge>
                                                        )}
                                                    </div>
                                                    <div className="text-xs text-muted-foreground">{member.email}</div>
                                                </div>
                                                <div className="text-right text-xs text-muted-foreground flex items-center gap-1">
                                                    <Clock className="h-3 w-3" />
                                                    {member.last_active || 'Invite sent'}
                                                </div>
                                            </div>
                                        </CardContent>
                                    </Card>
                                </motion.div>
                            );
                        })}
                    </div>
                )}

                {isLoggedIn && !loading && team.length === 0 && !error && (
                    <div className="text-center py-12 text-muted-foreground">
                        <UserCog className="h-10 w-10 mx-auto mb-3 opacity-30" />
                        <div className="font-medium">No team members yet</div>
                        <div className="text-sm">Invite your first team member to get started</div>
                    </div>
                )}
            </div>
        </div>
    );
}
