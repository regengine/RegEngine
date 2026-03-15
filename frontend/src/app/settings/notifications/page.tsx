'use client';

import Link from 'next/link';
import { Bell, Mail, MessageSquare, ArrowLeft, CheckCircle2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';

export default function NotificationsSettingsPage() {
    return (
        <>            <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
                <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8 sm:py-12">
                    {/* Breadcrumb */}
                    <Link href="/settings" className="inline-flex items-center text-sm text-muted-foreground hover:text-primary mb-6">
                        <ArrowLeft className="h-4 w-4 mr-1" />
                        Back to Settings
                    </Link>

                    {/* Page Header */}
                    <div className="mb-8">
                        <h1 className="text-3xl sm:text-4xl font-bold mb-2">Notification Preferences</h1>
                        <p className="text-muted-foreground">
                            Control how you receive updates and alerts
                        </p>
                    </div>

                    {/* Email Notifications */}
                    <Card className="mb-6">
                        <CardHeader>
                            <div className="flex items-center gap-2">
                                <Mail className="h-5 w-5 text-primary" />
                                <CardTitle>Email Notifications</CardTitle>
                            </div>
                            <CardDescription>
                                Choose what notifications you receive via email
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <Label htmlFor="compliance-alerts">Compliance Alerts</Label>
                                    <p className="text-sm text-muted-foreground">Critical compliance deadline reminders</p>
                                </div>
                                <Switch id="compliance-alerts" disabled defaultChecked />
                            </div>

                            <div className="flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <Label htmlFor="audit-updates">Audit Updates</Label>
                                    <p className="text-sm text-muted-foreground">Status changes for audits and reviews</p>
                                </div>
                                <Switch id="audit-updates" disabled defaultChecked />
                            </div>

                            <div className="flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <Label htmlFor="ingestion-complete">Ingestion Complete</Label>
                                    <p className="text-sm text-muted-foreground">When document ingestion jobs finish</p>
                                </div>
                                <Switch id="ingestion-complete" disabled defaultChecked />
                            </div>

                            <div className="flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <Label htmlFor="weekly-digest">Weekly Digest</Label>
                                    <p className="text-sm text-muted-foreground">Weekly summary of platform activity</p>
                                </div>
                                <Switch id="weekly-digest" disabled />
                            </div>

                            <div className="flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <Label htmlFor="product-updates">Product Updates</Label>
                                    <p className="text-sm text-muted-foreground">New features and platform improvements</p>
                                </div>
                                <Switch id="product-updates" disabled />
                            </div>
                        </CardContent>
                    </Card>

                    {/* In-App Notifications */}
                    <Card className="mb-6">
                        <CardHeader>
                            <div className="flex items-center gap-2">
                                <Bell className="h-5 w-5 text-primary" />
                                <CardTitle>In-App Notifications</CardTitle>
                            </div>
                            <CardDescription>
                                Manage notifications within the RegEngine platform
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <Label htmlFor="desktop-notifications">Desktop Notifications</Label>
                                    <p className="text-sm text-muted-foreground">Browser push notifications</p>
                                </div>
                                <Switch id="desktop-notifications" disabled defaultChecked />
                            </div>

                            <div className="flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <Label htmlFor="sound-alerts">Sound Alerts</Label>
                                    <p className="text-sm text-muted-foreground">Play sound for critical alerts</p>
                                </div>
                                <Switch id="sound-alerts" disabled />
                            </div>

                            <div className="flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <Label htmlFor="badge-count">Badge Count</Label>
                                    <p className="text-sm text-muted-foreground">Show notification count on icon</p>
                                </div>
                                <Switch id="badge-count" disabled defaultChecked />
                            </div>
                        </CardContent>
                    </Card>

                    {/* Webhook Notifications */}
                    <Card className="mb-6">
                        <CardHeader>
                            <div className="flex items-center gap-2">
                                <MessageSquare className="h-5 w-5 text-primary" />
                                <CardTitle>Webhook Notifications</CardTitle>
                            </div>
                            <CardDescription>
                                Send notifications to external services via webhooks
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="p-4 bg-muted/50 rounded-lg border-dashed border-2">
                                <p className="text-sm text-muted-foreground text-center">
                                    No webhooks configured
                                </p>
                            </div>
                            <Button variant="outline" disabled>
                                Add Webhook
                            </Button>
                        </CardContent>
                    </Card>

                    {/* Notification Schedule */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Quiet Hours</CardTitle>
                            <CardDescription>
                                Set times when you don't want to receive non-critical notifications
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <Label htmlFor="quiet-hours">Enable Quiet Hours</Label>
                                    <p className="text-sm text-muted-foreground">Pause notifications during specified times</p>
                                </div>
                                <Switch id="quiet-hours" disabled />
                            </div>

                            <div className="grid grid-cols-2 gap-4 opacity-50">
                                <div>
                                    <Label>Start Time</Label>
                                    <select className="w-full mt-1.5 px-3 py-2 border rounded bg-background" disabled>
                                        <option>10:00 PM</option>
                                    </select>
                                </div>
                                <div>
                                    <Label>End Time</Label>
                                    <select className="w-full mt-1.5 px-3 py-2 border rounded bg-background" disabled>
                                        <option>7:00 AM</option>
                                    </select>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Save Button */}
                    <div className="mt-6 flex gap-3">
                        <Button disabled>
                            <CheckCircle2 className="mr-2 h-4 w-4" />
                            Save Preferences
                        </Button>
                        <Button variant="outline" asChild>
                            <Link href="/settings">Cancel</Link>
                        </Button>
                    </div>

                    {/* Info Note */}
                    <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
                        <p className="text-sm text-blue-900 dark:text-blue-200">
                            <strong>Note:</strong> Notification preferences are currently in development.
                            Critical compliance alerts will always be sent regardless of these settings.
                        </p>
                    </div>
                </div>
            </div>        </>
    );
}
