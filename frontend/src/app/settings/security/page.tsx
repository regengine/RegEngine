'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Shield, Lock, Key, Smartphone, ArrowLeft, Clock, Loader2, CheckCircle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { apiClient } from '@/lib/api-client';

const MIN_PASSWORD_LENGTH = 12;

const PLANNED_FEATURES = [
    {
        icon: Smartphone,
        title: 'Two-Factor Authentication (2FA)',
        description:
            'Add a second layer of protection with TOTP authenticator apps (Google Authenticator, Authy, 1Password) or hardware security keys via WebAuthn.',
        eta: 'Q2 2026',
    },
    {
        icon: Key,
        title: 'Session Management',
        description:
            'View and revoke active sessions across all your devices. See login history with device type, location, and IP address.',
        eta: 'Q3 2026',
    },
    {
        icon: Shield,
        title: 'Security Audit Log',
        description:
            'A detailed, searchable log of all security-relevant events on your account including logins, permission changes, and API key usage.',
        eta: 'Q3 2026',
    },
];

export default function SecuritySettingsPage() {
    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState(false);

    const handleChangePassword = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setSuccess(false);

        if (newPassword !== confirmPassword) {
            setError('New passwords do not match.');
            return;
        }

        if (newPassword.length < MIN_PASSWORD_LENGTH) {
            setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
            return;
        }

        setIsLoading(true);
        try {
            await apiClient.changePassword(currentPassword, newPassword);
            setSuccess(true);
            setCurrentPassword('');
            setNewPassword('');
            setConfirmPassword('');
        } catch (err: unknown) {
            const axiosError = err as { response?: { status?: number; data?: { detail?: string } } };
            if (axiosError.response?.status === 401) {
                setError('Current password is incorrect.');
            } else if (axiosError.response?.data?.detail) {
                setError(axiosError.response.data.detail);
            } else if (axiosError.response?.status === 429) {
                setError('Too many attempts. Please wait a moment and try again.');
            } else {
                setError('An unexpected error occurred. Please try again.');
            }
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
                {/* Breadcrumb */}
                <Link
                    href="/settings"
                    className="inline-flex items-center text-sm text-muted-foreground hover:text-primary mb-6"
                >
                    <ArrowLeft className="h-4 w-4 mr-1" />
                    Back to Settings
                </Link>

                {/* Page Header */}
                <div className="mb-8">
                    <h1 className="text-3xl sm:text-4xl font-bold mb-2">Security Settings</h1>
                    <p className="text-muted-foreground">
                        Manage your password and security preferences
                    </p>
                </div>

                {/* Change Password */}
                <Card className="mb-8">
                    <CardHeader>
                        <div className="flex items-center gap-2">
                            <Lock className="h-5 w-5 text-primary" />
                            <CardTitle>Change Password</CardTitle>
                        </div>
                        <CardDescription>
                            Update your account password.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <form onSubmit={handleChangePassword} className="space-y-4 max-w-md">
                            {error && (
                                <div
                                    role="alert"
                                    className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-500 dark:border-red-800 dark:bg-red-900/10"
                                >
                                    {error}
                                </div>
                            )}

                            {success && (
                                <div className="flex items-center gap-2 rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-700 dark:border-green-800 dark:bg-green-900/10 dark:text-green-400">
                                    <CheckCircle className="h-4 w-4" />
                                    Password changed successfully.
                                </div>
                            )}

                            <div className="space-y-2">
                                <label className="text-sm font-medium leading-none" htmlFor="currentPassword">
                                    Current Password
                                </label>
                                <Input
                                    id="currentPassword"
                                    type="password"
                                    value={currentPassword}
                                    onChange={(e) => setCurrentPassword(e.target.value)}
                                    disabled={isLoading}
                                    required
                                    autoComplete="current-password"
                                />
                            </div>

                            <div className="space-y-2">
                                <label className="text-sm font-medium leading-none" htmlFor="newPassword">
                                    New Password
                                </label>
                                <Input
                                    id="newPassword"
                                    type="password"
                                    value={newPassword}
                                    onChange={(e) => setNewPassword(e.target.value)}
                                    disabled={isLoading}
                                    required
                                    minLength={MIN_PASSWORD_LENGTH}
                                    autoComplete="new-password"
                                />
                            </div>

                            <div className="space-y-2">
                                <label className="text-sm font-medium leading-none" htmlFor="confirmPassword">
                                    Confirm New Password
                                </label>
                                <Input
                                    id="confirmPassword"
                                    type="password"
                                    value={confirmPassword}
                                    onChange={(e) => setConfirmPassword(e.target.value)}
                                    disabled={isLoading}
                                    required
                                    minLength={MIN_PASSWORD_LENGTH}
                                    autoComplete="new-password"
                                />
                            </div>

                            <p className="text-xs text-muted-foreground">
                                At least {MIN_PASSWORD_LENGTH} characters with uppercase, lowercase, digit, and special character.
                            </p>

                            <Button type="submit" disabled={isLoading}>
                                {isLoading ? (
                                    <>
                                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                        Changing...
                                    </>
                                ) : (
                                    'Change Password'
                                )}
                            </Button>
                        </form>
                    </CardContent>
                </Card>

                {/* Planned Features */}
                <div className="mb-6">
                    <h2 className="text-lg font-semibold mb-1">Planned Security Features</h2>
                    <p className="text-sm text-muted-foreground mb-4">
                        The following features are on our roadmap and will be available in upcoming releases.
                    </p>
                </div>

                <div className="grid gap-4">
                    {PLANNED_FEATURES.map((feature) => (
                        <Card key={feature.title} className="border-dashed">
                            <CardHeader className="pb-2">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <feature.icon className="h-5 w-5 text-muted-foreground" />
                                        <CardTitle className="text-base">{feature.title}</CardTitle>
                                    </div>
                                    <span className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground bg-muted px-2 py-1 rounded-full">
                                        <Clock className="h-3 w-3" />
                                        {feature.eta}
                                    </span>
                                </div>
                            </CardHeader>
                            <CardContent>
                                <p className="text-sm text-muted-foreground">{feature.description}</p>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            </div>
        </div>
    );
}
