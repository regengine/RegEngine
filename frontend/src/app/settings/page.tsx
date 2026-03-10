'use client';

import Link from 'next/link';
import { Settings as SettingsIcon, User, Bell, Lock, Key, Globe } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export default function SettingsPage() {
    return (
        <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            <div className="max-w-6xl mx-auto px-4 py-12">
                {/* Page Header */}
                <div className="mb-8">
                    <h1 className="text-4xl font-bold mb-2">Settings</h1>
                    <p className="text-muted-foreground">
                        Manage your account preferences and platform settings
                    </p>
                </div>

                {/* Settings Categories */}
                <div className="grid md:grid-cols-2 gap-6">
                    {/* Account Settings */}
                    <Card>
                        <CardHeader>
                            <div className="flex items-center gap-2">
                                <User className="h-5 w-5 text-primary" />
                                <CardTitle>Account</CardTitle>
                            </div>
                            <CardDescription>
                                Manage your profile and account information
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-3">
                            <div className="text-sm">
                                <div className="font-medium mb-1">Profile Settings</div>
                                <p className="text-muted-foreground text-xs">
                                    Update your name, email, and profile picture
                                </p>
                            </div>
                            <Link href="/settings/profile">
                                <Button variant="outline" className="w-full">
                                    Edit Profile
                                </Button>
                            </Link>
                        </CardContent>
                    </Card>

                    {/* API Keys */}
                    <Card>
                        <CardHeader>
                            <div className="flex items-center gap-2">
                                <Key className="h-5 w-5 text-primary" />
                                <CardTitle>API Keys</CardTitle>
                            </div>
                            <CardDescription>
                                Manage your API keys for programmatic access
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-3">
                            <div className="text-sm">
                                <div className="font-medium mb-1">API Access</div>
                                <p className="text-muted-foreground text-xs">
                                    Create and manage API keys for integrations
                                </p>
                            </div>
                            <Link href="/api-keys">
                                <Button variant="outline" className="w-full">
                                    Manage API Keys
                                </Button>
                            </Link>
                        </CardContent>
                    </Card>

                    {/* Security */}
                    <Card>
                        <CardHeader>
                            <div className="flex items-center gap-2">
                                <Lock className="h-5 w-5 text-primary" />
                                <CardTitle>Security</CardTitle>
                            </div>
                            <CardDescription>
                                Password and two-factor authentication settings
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-3">
                            <div className="text-sm">
                                <div className="font-medium mb-1">Password & Security</div>
                                <p className="text-muted-foreground text-xs">
                                    Change password and enable 2FA
                                </p>
                            </div>
                            <Link href="/settings/security">
                                <Button variant="outline" className="w-full">
                                    Configure Security
                                </Button>
                            </Link>
                        </CardContent>
                    </Card>

                    {/* Notifications */}
                    <Card>
                        <CardHeader>
                            <div className="flex items-center gap-2">
                                <Bell className="h-5 w-5 text-primary" />
                                <CardTitle>Notifications</CardTitle>
                            </div>
                            <CardDescription>
                                Control how you receive alerts and updates
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-3">
                            <div className="text-sm">
                                <div className="font-medium mb-1">Notification Preferences</div>
                                <p className="text-muted-foreground text-xs">
                                    Email, in-app, and webhook notifications
                                </p>
                            </div>
                            <Link href="/settings/notifications">
                                <Button variant="outline" className="w-full">
                                    Manage Notifications
                                </Button>
                            </Link>
                        </CardContent>
                    </Card>

                    {/* Preferences */}
                    <Card>
                        <CardHeader>
                            <div className="flex items-center gap-2">
                                <SettingsIcon className="h-5 w-5 text-primary" />
                                <CardTitle>Preferences</CardTitle>
                            </div>
                            <CardDescription>
                                Customize your RegEngine experience
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-3">
                            <div className="text-sm">
                                <div className="font-medium mb-1">Display & Language</div>
                                <p className="text-muted-foreground text-xs">
                                    Theme, timezone, and language settings
                                </p>
                            </div>
                            <Button variant="outline" className="w-full" disabled>
                                Edit Preferences
                            </Button>
                        </CardContent>
                    </Card>

                    {/* Organization */}
                    <Card>
                        <CardHeader>
                            <div className="flex items-center gap-2">
                                <Globe className="h-5 w-5 text-primary" />
                                <CardTitle>Organization</CardTitle>
                            </div>
                            <CardDescription>
                                Manage organization and team settings
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-3">
                            <div className="text-sm">
                                <div className="font-medium mb-1">Team & Billing</div>
                                <p className="text-muted-foreground text-xs">
                                    Organization settings and subscription
                                </p>
                            </div>
                            <Link href="/settings/users">
                                <Button variant="outline" className="w-full">
                                    Manage Users
                                </Button>
                            </Link>
                        </CardContent>
                    </Card>
                </div>

                {/* Quick Links */}
                <div className="mt-8 p-6 bg-muted/50 rounded-lg border">
                    <h3 className="font-semibold mb-3">Quick Links</h3>
                    <div className="grid sm:grid-cols-3 gap-4 text-sm">
                        <Link href="/docs" className="text-primary hover:underline">
                            Documentation
                        </Link>
                        <Link href="/admin" className="text-primary hover:underline">
                            Admin Panel
                        </Link>
                        <Link href="/compliance" className="text-primary hover:underline">
                            Compliance Dashboard
                        </Link>
                    </div>
                </div>

                {/* Info Note */}
                <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
                    <p className="text-sm text-blue-900 dark:text-blue-200">
                        <strong>Note:</strong> Some settings are currently in development and will be available soon.
                        For immediate assistance, please contact support.
                    </p>
                </div>
            </div>
        </div>
    );
}
