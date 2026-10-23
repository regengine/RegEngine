'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { DataTable, type DataTableColumn } from '@/components/ui/data-table';
import { Field } from '@/components/ui/field';
import { Input, fieldControlClasses } from '@/components/ui/input';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { StatusBadge } from '@/components/ui/status-badge';
import { useAuth } from '@/lib/auth-context';
import { apiClient } from '@/lib/api-client';
import { User, Invite, Role } from '@/types/api';
import { UserPlus, Ban, Clock } from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import { cn } from '@/lib/utils';

export default function UserSettingsPage() {
    const { user } = useAuth();
    const { toast } = useToast();
    const router = useRouter();

    const [users, setUsers] = useState<User[]>([]);
    const [invites, setInvites] = useState<Invite[]>([]);
    const [roles, setRoles] = useState<Role[]>([]);
    const [isLoading, setIsLoading] = useState(true);

    // Invite Form State
    const [isInviteOpen, setIsInviteOpen] = useState(false);
    const [inviteEmail, setInviteEmail] = useState('');
    const [inviteRoleId, setInviteRoleId] = useState('');
    const [isInviting, setIsInviting] = useState(false);

    const loadData = async () => {
        setIsLoading(true);
        try {
            const [usersData, invitesData, rolesData] = await Promise.all([
                apiClient.getUsers(),
                apiClient.getInvites(),
                apiClient.getRoles()
            ]);
            setUsers(usersData);
            setInvites(invitesData);
            setRoles(rolesData);

            if (rolesData.length > 0 && !inviteRoleId) {
                // Default to first role (or specific logic)
                setInviteRoleId(rolesData.find(r => r.name === 'Viewer')?.id || rolesData[0].id);
            }
        } catch (error) {
            if (process.env.NODE_ENV !== 'production') {
                console.error('Failed to load data', error);
            }
            toast({
                title: "Error",
                description: "Failed to load user management data.",
                variant: "destructive"
            });
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        loadData();
        // Mount-once load. loadData closes over inviteRoleId and then sets it,
        // so adding it to the dependency array (directly or via useCallback)
        // would re-fire this effect on its own result — an endless fetch loop.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleInvite = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsInviting(true);
        try {
            await apiClient.createInvite({
                email: inviteEmail,
                role_id: inviteRoleId
            });
            toast({
                title: "Invite Sent",
                description: `Invitation sent to ${inviteEmail}`,
            });
            setIsInviteOpen(false);
            setInviteEmail('');
            loadData(); // Refresh list
        } catch (error) {
            toast({
                title: "Invite Failed",
                description: "Could not send invite. Check if user is already invited or exists.",
                variant: "destructive"
            });
        } finally {
            setIsInviting(false);
        }
    };

    const handleRevoke = async (inviteId: string) => {
        try {
            await apiClient.revokeInvite(inviteId);
            toast({ title: "Invite Revoked" });
            loadData();
        } catch (error) {
            toast({
                title: "Error",
                description: "Failed to revoke invite",
                variant: "destructive"
            });
        }
    };

    const handleDeactivate = async (userId: string) => {
        if (!confirm("Are you sure you want to remove this user from this workspace?")) return;
        try {
            await apiClient.deactivateUser(userId);
            toast({ title: "User Removed" });
            loadData();
        } catch (error) {
            toast({
                title: "Error",
                description: "Failed to deactivate user. Ensure you are not removing the last Owner.",
                variant: "destructive"
            });
        }
    };

    const handleRoleChange = async (userId: string, newRoleId: string) => {
        try {
            await apiClient.updateUserRole(userId, newRoleId);
            toast({ title: "Role Updated" });
            loadData();
        } catch (error) {
            toast({
                title: "Error",
                description: "Failed to update role.",
                variant: "destructive"
            });
        }
    };

    const tableStatus = isLoading ? 'loading' : 'idle';

    const userColumns: DataTableColumn<User>[] = [
        {
            key: 'email',
            header: 'User',
            width: '18rem',
            cell: (u) => (
                <div className="min-w-0">
                    <div className="truncate font-medium text-re-text-primary">{u.email}</div>
                    <div className="text-small text-re-text-tertiary">
                        Joined {new Date(u.created_at || '').toLocaleDateString()}
                    </div>
                </div>
            ),
        },
        {
            key: 'role_id',
            header: 'Role',
            width: '11rem',
            cell: (u) => (
                <>
                    <label htmlFor={`user-role-${u.id}`} className="sr-only">
                        Role
                    </label>
                    <select
                        id={`user-role-${u.id}`}
                        className={cn(fieldControlClasses, 'h-8 w-full')}
                        value={u.role_id}
                        onChange={(e) => handleRoleChange(u.id, e.target.value)}
                        disabled={u.id === user?.id} // Prevent self-demotion lockout prevention logic (frontend safeguard)
                    >
                        {roles.map(r => (
                            <option key={r.id} value={r.id}>{r.name}</option>
                        ))}
                    </select>
                </>
            ),
        },
        {
            key: 'status',
            header: 'Status',
            width: '9rem',
            cell: (u) => (
                <StatusBadge
                    state={u.status === 'active' ? 'compliant' : 'pending'}
                    label={u.status}
                />
            ),
        },
        {
            key: 'actions',
            header: 'Actions',
            width: '6rem',
            cell: (u) =>
                u.id !== user?.id ? (
                    <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Remove ${u.email}`}
                        onClick={() => handleDeactivate(u.id)}
                    >
                        <Ban className="h-4 w-4 text-re-danger" strokeWidth={1.75} aria-hidden="true" />
                    </Button>
                ) : null,
        },
    ];

    const inviteColumns: DataTableColumn<Invite>[] = [
        { key: 'email', header: 'Email', width: '16rem' },
        {
            key: 'role',
            header: 'Role',
            width: '9rem',
            cell: (inv) => roles.find(r => r.id === inv.role_id)?.name || 'Unknown',
        },
        {
            key: 'created_at',
            header: 'Sent',
            width: '8rem',
            mono: true,
            cell: (inv) => new Date(inv.created_at).toLocaleDateString(),
        },
        {
            key: 'expires_at',
            header: 'Expires',
            width: '9rem',
            mono: true,
            cell: (inv) => (
                <span className="flex items-center gap-1">
                    <Clock className="h-3.5 w-3.5 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                    {new Date(inv.expires_at).toLocaleDateString()}
                </span>
            ),
        },
        {
            key: 'actions',
            header: 'Actions',
            width: '13rem',
            cell: (inv) => (
                <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={() => {
                        navigator.clipboard.writeText(inv.invite_link || '');
                        toast({ title: "Link Copied" });
                    }}>
                        Copy Link
                    </Button>
                    <Button variant="destructive" size="sm" onClick={() => handleRevoke(inv.id)}>
                        Revoke
                    </Button>
                </div>
            ),
        },
    ];

    return (
        <PageContainer>
            <PageHeader
                title="Team Management"
                description="Manage users, roles, and invitations."
                primaryAction={
                    <Dialog open={isInviteOpen} onOpenChange={setIsInviteOpen}>
                        <DialogTrigger asChild>
                            <Button leadingIcon={<UserPlus strokeWidth={1.75} aria-hidden="true" />}>
                                Invite User
                            </Button>
                        </DialogTrigger>
                        <DialogContent>
                            <DialogHeader>
                                <DialogTitle>Invite New User</DialogTitle>
                                <DialogDescription>
                                    Implement strict access control by assigning the correct role.
                                </DialogDescription>
                            </DialogHeader>
                            <form onSubmit={handleInvite} className="space-y-4">
                                <Field label="Email Address" htmlFor="invite-email">
                                    <Input
                                        id="invite-email"
                                        type="email"
                                        placeholder="colleague@company.com"
                                        value={inviteEmail}
                                        onChange={e => setInviteEmail(e.target.value)}
                                        required
                                    />
                                </Field>
                                <Field label="Role" htmlFor="invite-role">
                                    <select
                                        id="invite-role"
                                        className={fieldControlClasses}
                                        value={inviteRoleId}
                                        onChange={e => setInviteRoleId(e.target.value)}
                                    >
                                        {roles.map(role => (
                                            <option key={role.id} value={role.id}>
                                                {role.name} {role.is_system ? '(System)' : ''}
                                            </option>
                                        ))}
                                    </select>
                                </Field>
                                <DialogFooter>
                                    <Button type="submit" disabled={isInviting} loading={isInviting}>
                                        Send Invite
                                    </Button>
                                </DialogFooter>
                            </form>
                        </DialogContent>
                    </Dialog>
                }
            />

            <Tabs defaultValue="users">
                <TabsList>
                    <TabsTrigger value="users">Active Users ({users.length})</TabsTrigger>
                    <TabsTrigger value="invites">Pending Invites ({invites.length})</TabsTrigger>
                </TabsList>

                <TabsContent value="users">
                    <Card>
                        <CardHeader>
                            <div className="min-w-0">
                                <CardTitle>Active Members</CardTitle>
                                <CardDescription>People with access to this workspace.</CardDescription>
                            </div>
                        </CardHeader>
                        <CardContent className="p-0">
                            <DataTable
                                caption="Active workspace members, their role and status"
                                columns={userColumns}
                                data={users}
                                rowKey={(u) => u.id}
                                status={tableStatus}
                                empty={{ title: 'No active members.' }}
                                minWidth="640px"
                                stickyFirstColumn
                                className="rounded-none border-0"
                            />
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="invites">
                    <Card>
                        <CardHeader>
                            <div className="min-w-0">
                                <CardTitle>Pending Invitations</CardTitle>
                                <CardDescription>Invitations sent but not yet accepted.</CardDescription>
                            </div>
                        </CardHeader>
                        <CardContent className="p-0">
                            <DataTable
                                caption="Invitations sent but not yet accepted"
                                columns={inviteColumns}
                                data={invites}
                                rowKey={(inv) => inv.id}
                                status={tableStatus}
                                empty={{ title: 'No pending invitations.' }}
                                minWidth="720px"
                                stickyFirstColumn
                                className="rounded-none border-0"
                            />
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </PageContainer>
    );
}
