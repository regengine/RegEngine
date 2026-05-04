'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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

async function apiFetchTeam(tenantId: string, apiKey: string): Promise<TeamResponse> {
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetchWithCsrf(`${base}/api/v1/team/${tenantId}`, {
        signal: AbortSignal.timeout(8000),
        headers: { 'Content-Type': 'application/json', 'X-RegEngine-API-Key': apiKey },
    });
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
    return res.json();
}

async function apiInviteMember(tenantId: string, apiKey: string, name: string, email: string, role: string): Promise<void> {
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetchWithCsrf(`${base}/api/v1/team/${tenantId}/invite`, {
        method: 'POST',
        signal: AbortSignal.timeout(12000),
        headers: { 'Content-Type': 'application/json', 'X-RegEngine-API-Key': apiKey },
        body: JSON.stringify({ name, email, role }),
    });
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
}

export default function TeamPage() {
    const { isAuthenticated, apiKey } = useAuth();
    const { tenantId } = useTenant();
    const isLoggedIn = isAuthenticated;

    const teamQueryClient = useQueryClient();

    const { data: teamData, isLoading: loading, error: teamError, refetch: loadTeam } = useQuery({
        queryKey: ['team', tenantId],
        queryFn: () => apiFetchTeam(tenantId, apiKey || ''),
        enabled: isLoggedIn && !!tenantId,
        retry: false,
    });

    const team = teamData?.members ?? [];
    const activeCount = teamData?.active_members ?? 0;
    const pendingCount = teamData?.pending_invites ?? 0;
    const rolesBreakdown = teamData?.roles_breakdown ?? {};
    const error = teamError?.message ?? null;

    const [showInvite, setShowInvite] = useState(false);
    const [newName, setNewName] = useState('');
    const [newEmail, setNewEmail] = useState('');
    const [newRole, setNewRole] = useState('viewer');

    const inviteMutation = useMutation({
        mutationFn: () => apiInviteMember(tenantId, apiKey || '', newName, newEmail, newRole),
        onSuccess: () => {
            setNewName(''); setNewEmail(''); setShowInvite(false);
            teamQueryClient.invalidateQueries({ queryKey: ['team', tenantId] });
        },
    });

    const inviting = inviteMutation.isPending;

    const handleInvite = () => {
        if (!newName || !newEmail) return;
        inviteMutation.mutate();
    };

    return (
        <div className="min-h-screen bg-background py-8 sm:py-10 px-4 sm:px-6">
            <div className="max-w-4xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div>
                        <h1 className="text-xl sm:text-2xl font-bold flex items-center gap-2 sm:gap-3">
                            <UserCog className="h-5 w-5 sm:h-6 sm:w-6 text-[var(--re-brand)]" />
                            Team Management
                        </h1>
                        <p className="text-xs sm:text-sm text-muted-foreground mt-1">
                            {activeCount} active · {pendingCount} pending
                        </p>
                    </div>
                    <div className="flex gap-2 w-full sm:w-auto">
                        <Button variant="outline" size="sm" className="rounded-xl min-h-[44px] min-w-[44px] active:scale-[0.97]" onClick={() => loadTeam()} disabled={loading}>
                            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
                        </Button>
                        <Button onClick={() => setShowInvite(!showInvite)} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl min-h-[48px] flex-1 sm:flex-initial active:scale-[0.97]">
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
                                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
                                    <Input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Full name" className="rounded-xl min-h-[44px]" />
                                    <Input value={newEmail} onChange={e => setNewEmail(e.target.value)} placeholder="Email" type="email" className="rounded-xl min-h-[44px]" />
                                    <select value={newRole} onChange={e => setNewRole(e.target.value)} className="flex min-h-[44px] rounded-xl border border-input bg-background px-3 text-sm">
                                        <option value="admin">Admin</option>
                                        <option value="compliance_manager">Compliance Manager</option>
                                        <option value="viewer">Viewer</option>
                                    </select>
                                    <Button onClick={handleInvite} disabled={inviting} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl min-h-[48px] active:scale-[0.97]">
                                        {inviting ? <Spinner size="sm" /> : <><Mail className="h-4 w-4 mr-1" /> Send Invite</>}
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}

                {/* Roles Reference */}
                {Object.keys(rolesBreakdown).length > 0 && (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 sm:gap-3">
                        {Object.entries(ROLE_CONFIG).map(([key, config]) => {
                            const Icon = config.icon;
                            const count = rolesBreakdown[key] || 0;
                            return (
                                <div key={key} className="p-2.5 sm:p-3 rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)]">
                                    <div className="flex items-center gap-1.5 sm:gap-2 mb-1">
                                        <Icon className="h-3.5 w-3.5 sm:h-4 sm:w-4 flex-shrink-0" style={{ color: config.color }} />
                                        <span className="text-[11px] sm:text-xs font-medium truncate">{config.label}</span>
                                    </div>
                                    <span className="text-base sm:text-lg font-bold">{count}</span>
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
                                            <div className="flex items-start sm:items-center gap-2.5 sm:gap-3">
                                                <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-full bg-[color-mix(in_srgb,var(--re-brand)_12%,transparent)] flex items-center justify-center text-[11px] sm:text-xs font-bold text-[var(--re-brand)] flex-shrink-0">
                                                    {member.avatar_initials || member.name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)}
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                                                        <span className="font-medium text-xs sm:text-sm">{member.name}</span>
                                                        <Badge className="text-[9px] px-1.5 py-0 flex-shrink-0" style={{ background: `${roleConfig.color}15`, color: roleConfig.color }}>
                                                            <RoleIcon className="h-2.5 w-2.5 mr-0.5" /> {roleConfig.label}
                                                        </Badge>
                                                        {member.status === 'invited' && (
                                                            <Badge variant="outline" className="text-[9px] py-0 text-re-warning border-re-warning/20">Pending</Badge>
                                                        )}
                                                    </div>
                                                    <div className="text-[11px] sm:text-xs text-muted-foreground truncate">{member.email}</div>
                                                    <div className="text-[11px] text-muted-foreground flex items-center gap-1 mt-0.5 sm:hidden">
                                                        <Clock className="h-3 w-3" />
                                                        {member.last_active || 'Invite sent'}
                                                    </div>
                                                </div>
                                                <div className="text-right text-xs text-muted-foreground items-center gap-1 hidden sm:flex flex-shrink-0">
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
