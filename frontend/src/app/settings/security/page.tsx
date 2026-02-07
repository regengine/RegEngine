'use client';

import Link from 'next/link';
import { Shield, Lock, Key, Smartphone, ArrowLeft, AlertTriangle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';

export default function SecuritySettingsPage() {
    return (
        <>            <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
                <div className="max-w-4xl mx-auto px-4 py-12">
                    {/* Breadcrumb */}
                    <Link href="/settings" className="inline-flex items-center text-sm text-muted-foreground hover:text-primary mb-6">
                        <ArrowLeft className="h-4 w-4 mr-1" />
                        Back to Settings
                    </Link>

                    {/* Page Header */}
                    <div className="mb-8">
                        <h1 className="text-4xl font-bold mb-2">Security Settings</h1>
                        <p className="text-muted-foreground">
                            Manage your password, two-factor authentication, and security preferences
                        </p>
                    </div>

                    {/* Password Section */}
                    <Card className="mb-6">
                        <CardHeader>
                            <div className="flex items-center gap-2">
                                <Lock className="h-5 w-5 text-primary" />
                                <CardTitle>Password</CardTitle>
                            </div>
                            <CardDescription>
                                Update your password to keep your account secure
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <form className="space-y-4">
                                <div className="space-y-2">
                                    <Label htmlFor="current-password">Current Password</Label>
                                    <Input id="current-password" type="password" disabled />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="new-password">New Password</Label>
                                    <Input id="new-password" type="password" disabled />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="confirm-password">Confirm New Password</Label>
                                    <Input id="confirm-password" type="password" disabled />
                                </div>
                                <Button type="button" disabled>
                                    Update Password
                                </Button>
                            </form>
                        </CardContent>
                    </Card>

                    {/* Two-Factor Authentication */}
                    <Card className="mb-6">
                        <CardHeader>
                            <div className="flex items-center gap-2">
                                <Smartphone className="h-5 w-5 text-primary" />
                                <CardTitle>Two-Factor Authentication (2FA)</CardTitle>
                            </div>
                            <CardDescription>
                                Add an extra layer of security to your account
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-4">
                                <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
                                    <div className="flex-1">
                                        <h4 className="font-medium mb-1">Authenticator App</h4>
                                        <p className="text-sm text-muted-foreground">
                                            Use an authenticator app like Google Authenticator or Authy
                                        </p>
                                    </div>
                                    <Switch disabled />
                                </div>

                                <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
                                    <div className="flex-1">
                                        <h4 className="font-medium mb-1">SMS Authentication</h4>
                                        <p className="text-sm text-muted-foreground">
                                            Receive verification codes via text message
                                        </p>
                                    </div>
                                    <Switch disabled />
                                </div>

                                <Button variant="outline" disabled>
                                    Setup 2FA
                                </Button>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Session Management */}
                    <Card className="mb-6">
                        <CardHeader>
                            <div className="flex items-center gap-2">
                                <Key className="h-5 w-5 text-primary" />
                                <CardTitle>Active Sessions</CardTitle>
                            </div>
                            <CardDescription>
                                Manage your active sessions across devices
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-3">
                                <div className="flex items-start justify-between p-3 border rounded-lg">
                                    <div>
                                        <p className="font-medium">Current Session</p>
                                        <p className="text-sm text-muted-foreground">Chrome on macOS • San Francisco, CA</p>
                                        <p className="text-xs text-muted-foreground mt-1">Last active: Just now</p>
                                    </div>
                                    <Badge className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">Active</Badge>
                                </div>

                                <Button variant="destructive" size="sm" disabled>
                                    Sign Out All Other Sessions
                                </Button>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Security Log */}
                    <Card>
                        <CardHeader>
                            <div className="flex items-center gap-2">
                                <Shield className="h-5 w-5 text-primary" />
                                <CardTitle>Security Log</CardTitle>
                            </div>
                            <CardDescription>
                                Recent security events on your account
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-3">
                                <div className="flex items-center justify-between text-sm">
                                    <div>
                                        <p className="font-medium">Successful login</p>
                                        <p className="text-muted-foreground">Jan 30, 2026 at 7:30 PM</p>
                                    </div>
                                    <Badge variant="outline">Success</Badge>
                                </div>
                                <div className="flex items-center justify-between text-sm">
                                    <div>
                                        <p className="font-medium">Password changed</p>
                                        <p className="text-muted-foreground">Jan 25, 2026 at 2:15 PM</p>
                                    </div>
                                    <Badge variant="outline">Updated</Badge>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Info Note */}
                    <div className="mt-6 p-4 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800">
                        <div className="flex items-start gap-3">
                            <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5" />
                            <div className="flex-1">
                                <p className="text-sm text-amber-900 dark:text-amber-200 font-medium mb-1">
                                    Security Features in Development
                                </p>
                                <p className="text-sm text-amber-800 dark:text-amber-300">
                                    Advanced security features are currently being implemented. For immediate password reset or 2FA setup,
                                    please contact security@regengine.co.
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>        </>
    );
}

function Badge({ children, className, variant }: { children: React.ReactNode; className?: string; variant?: string }) {
    return <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${className}`}>{children}</span>;
}
