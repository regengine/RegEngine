'use client';

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
    UserCog,
    Plus,
    Shield,
    Crown,
    Eye,
    ShieldCheck,
    Mail,
    Clock,
} from 'lucide-react';

interface TeamMember {
    id: string;
    name: string;
    email: string;
    role: 'owner' | 'admin' | 'compliance_manager' | 'viewer';
    status: 'active' | 'invited';
    lastActive: string | null;
    initials: string;
}

const ROLE_CONFIG = {
    owner: { icon: Crown, color: '#f59e0b', label: 'Owner' },
    admin: { icon: Shield, color: '#3b82f6', label: 'Admin' },
    compliance_manager: { icon: ShieldCheck, color: '#10b981', label: 'Compliance Manager' },
    viewer: { icon: Eye, color: '#6b7280', label: 'Viewer' },
};

const INITIAL_TEAM: TeamMember[] = [
    { id: 'u1', name: 'Jordan Smith', email: 'jsmith@example.com', role: 'owner', status: 'active', lastActive: '5 min ago', initials: 'JS' },
    { id: 'u2', name: 'Alex Chen', email: 'achen@example.com', role: 'admin', status: 'active', lastActive: '2 hours ago', initials: 'AC' },
    { id: 'u3', name: 'Maria Garcia', email: 'mgarcia@example.com', role: 'compliance_manager', status: 'active', lastActive: '1 day ago', initials: 'MG' },
    { id: 'u4', name: 'Taylor Williams', email: 'twill@example.com', role: 'viewer', status: 'active', lastActive: '3 days ago', initials: 'TW' },
    { id: 'u5', name: 'Chris Lee', email: 'clee@example.com', role: 'compliance_manager', status: 'invited', lastActive: null, initials: 'CL' },
];

export default function TeamPage() {
    const [team, setTeam] = useState(INITIAL_TEAM);
    const [showInvite, setShowInvite] = useState(false);
    const [newName, setNewName] = useState('');
    const [newEmail, setNewEmail] = useState('');
    const [newRole, setNewRole] = useState<TeamMember['role']>('viewer');

    const active = team.filter(m => m.status === 'active').length;
    const pending = team.filter(m => m.status === 'invited').length;

    const handleInvite = () => {
        if (!newName || !newEmail) return;
        const newMember: TeamMember = {
            id: `u-${Date.now()}`,
            name: newName,
            email: newEmail,
            role: newRole,
            status: 'invited',
            lastActive: null,
            initials: newName.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2),
        };
        setTeam([...team, newMember]);
        setNewName(''); setNewEmail(''); setShowInvite(false);
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
                            {active} active · {pending} pending
                        </p>
                    </div>
                    <Button onClick={() => setShowInvite(!showInvite)} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl">
                        <Plus className="h-4 w-4 mr-1" /> Invite Member
                    </Button>
                </div>

                {/* Invite Form */}
                {showInvite && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
                        <Card className="border-[var(--re-brand)]">
                            <CardContent className="py-4">
                                <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                                    <Input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Full name" className="rounded-xl" />
                                    <Input value={newEmail} onChange={e => setNewEmail(e.target.value)} placeholder="Email" type="email" className="rounded-xl" />
                                    <select value={newRole} onChange={e => setNewRole(e.target.value as TeamMember['role'])} className="flex h-10 rounded-xl border border-input bg-background px-3 text-sm">
                                        <option value="admin">Admin</option>
                                        <option value="compliance_manager">Compliance Manager</option>
                                        <option value="viewer">Viewer</option>
                                    </select>
                                    <Button onClick={handleInvite} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl">
                                        <Mail className="h-4 w-4 mr-1" /> Send Invite
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}

                {/* Roles Reference */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {Object.entries(ROLE_CONFIG).map(([key, config]) => {
                        const Icon = config.icon;
                        const count = team.filter(m => m.role === key).length;
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

                {/* Member List */}
                <div className="space-y-2">
                    {team.map((member, i) => {
                        const roleConfig = ROLE_CONFIG[member.role];
                        const RoleIcon = roleConfig.icon;
                        return (
                            <motion.div key={member.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
                                <Card className="border-[var(--re-border-default)] hover:border-[var(--re-brand)] transition-all">
                                    <CardContent className="py-3">
                                        <div className="flex items-center gap-3">
                                            <div className="w-10 h-10 rounded-full bg-[color-mix(in_srgb,var(--re-brand)_12%,transparent)] flex items-center justify-center text-xs font-bold text-[var(--re-brand)]">
                                                {member.initials}
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
                                                {member.lastActive || 'Invite sent'}
                                            </div>
                                        </div>
                                    </CardContent>
                                </Card>
                            </motion.div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
