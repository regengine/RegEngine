
'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
import { Badge } from '@/components/ui/badge';
import { useAuth } from '@/lib/auth-context';
import { apiClient } from '@/lib/api-client';
import { User, Invite, Role } from '@/types/api';
import { Loader2, UserPlus, Shield, Ban, CheckCircle, Clock } from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';

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

    useEffect(() => {
        loadData();
    }, []);

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
        if (!confirm("Are you sure you want to remove this user from the tenant?")) return;
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

    if (isLoading) {
        return <div className="flex justify-center p-8"><Loader2 className="animate-spin h-8 w-8 text-primary" /></div>;
    }

    return (
        <div className="container mx-auto py-6 sm:py-8 px-4 sm:px-6 max-w-5xl space-y-6 sm:space-y-8">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div>
                    <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Team Management</h1>
                    <p className="text-muted-foreground">Manage users, roles, and invitations.</p>
                </div>
                <Dialog open={isInviteOpen} onOpenChange={setIsInviteOpen}>
                    <DialogTrigger asChild>
                        <Button>
                            <UserPlus className="mr-2 h-4 w-4" />
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
                            <div className="space-y-2">
                                <label className="text-sm font-medium">Email Address</label>
                                <Input
                                    type="email"
                                    placeholder="colleague@company.com"
                                    value={inviteEmail}
                                    onChange={e => setInviteEmail(e.target.value)}
                                    required
                                />
                            </div>
                            <div className="space-y-2">
                                <label className="text-sm font-medium">Role</label>
                                <select
                                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                    value={inviteRoleId}
                                    onChange={e => setInviteRoleId(e.target.value)}
                                >
                                    {roles.map(role => (
                                        <option key={role.id} value={role.id}>
                                            {role.name} {role.is_system ? '(System)' : ''}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <DialogFooter>
                                <Button type="submit" disabled={isInviting}>
                                    {isInviting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                    Send Invite
                                </Button>
                            </DialogFooter>
                        </form>
                    </DialogContent>
                </Dialog>
            </div>

            <Tabs defaultValue="users">
                <TabsList>
                    <TabsTrigger value="users">Active Users ({users.length})</TabsTrigger>
                    <TabsTrigger value="invites">Pending Invites ({invites.length})</TabsTrigger>
                </TabsList>

                <TabsContent value="users">
                    <Card>
                        <CardHeader>
                            <CardTitle>Active Members</CardTitle>
                            <CardDescription>Users with access to this tenant.</CardDescription>
                        </CardHeader>
                        <CardContent className="overflow-x-auto">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>User</TableHead>
                                        <TableHead>Role</TableHead>
                                        <TableHead>Status</TableHead>
                                        <TableHead>Actions</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {users.map(u => (
                                        <TableRow key={u.id}>
                                            <TableCell>
                                                <div className="font-medium">{u.email}</div>
                                                <div className="text-xs text-muted-foreground">Joined {new Date(u.created_at || '').toLocaleDateString()}</div>
                                            </TableCell>
                                            <TableCell>
                                                <select
                                                    className="h-8 rounded border border-input bg-transparent px-2 text-sm"
                                                    value={u.role_id}
                                                    onChange={(e) => handleRoleChange(u.id, e.target.value)}
                                                    disabled={u.id === user?.id} // Prevent self-demotion lockout prevention logic (frontend safeguard)
                                                >
                                                    {roles.map(r => (
                                                        <option key={r.id} value={r.id}>{r.name}</option>
                                                    ))}
                                                </select>
                                            </TableCell>
                                            <TableCell>
                                                <Badge variant={u.status === 'active' ? 'default' : 'secondary'}>
                                                    {u.status}
                                                </Badge>
                                            </TableCell>
                                            <TableCell>
                                                {u.id !== user?.id && (
                                                    <Button variant="ghost" size="sm" onClick={() => handleDeactivate(u.id)}>
                                                        <Ban className="h-4 w-4 text-red-500" />
                                                    </Button>
                                                )}
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="invites">
                    <Card>
                        <CardHeader>
                            <CardTitle>Pending Invitations</CardTitle>
                            <CardDescription>Invitations sent but not yet accepted.</CardDescription>
                        </CardHeader>
                        <CardContent className="overflow-x-auto">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Email</TableHead>
                                        <TableHead>Role</TableHead>
                                        <TableHead>Sent</TableHead>
                                        <TableHead>Expires</TableHead>
                                        <TableHead>Actions</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {invites.length === 0 && (
                                        <TableRow>
                                            <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                                                No pending invitations.
                                            </TableCell>
                                        </TableRow>
                                    )}
                                    {invites.map(inv => (
                                        <TableRow key={inv.id}>
                                            <TableCell>{inv.email}</TableCell>
                                            <TableCell>
                                                {roles.find(r => r.id === inv.role_id)?.name || 'Unknown'}
                                            </TableCell>
                                            <TableCell>{new Date(inv.created_at).toLocaleDateString()}</TableCell>
                                            <TableCell>
                                                <div className="flex items-center gap-1">
                                                    <Clock className="h-3 w-3" />
                                                    {new Date(inv.expires_at).toLocaleDateString()}
                                                </div>
                                            </TableCell>
                                            <TableCell>
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
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
}
