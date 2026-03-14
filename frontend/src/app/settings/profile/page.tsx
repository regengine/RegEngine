'use client';

import Link from 'next/link';
import { User, Mail, Building2, Phone, MapPin, Calendar, ArrowLeft } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export default function ProfileSettingsPage() {
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
                        <h1 className="text-3xl sm:text-4xl font-bold mb-2">Profile Settings</h1>
                        <p className="text-muted-foreground">
                            Manage your personal information and account details
                        </p>
                    </div>

                    {/* Profile Form */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Personal Information</CardTitle>
                            <CardDescription>
                                Update your profile information
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <form className="space-y-6">
                                {/* Name Fields */}
                                <div className="grid md:grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="firstName">First Name</Label>
                                        <Input id="firstName" placeholder="John" disabled />
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="lastName">Last Name</Label>
                                        <Input id="lastName" placeholder="Doe" disabled />
                                    </div>
                                </div>

                                {/* Email */}
                                <div className="space-y-2">
                                    <Label htmlFor="email">Email Address</Label>
                                    <div className="flex gap-2">
                                        <Mail className="h-5 w-5 text-muted-foreground mt-2" />
                                        <Input id="email" type="email" placeholder="john.doe@company.com" disabled className="flex-1" />
                                    </div>
                                    <p className="text-xs text-muted-foreground">
                                        Contact support to change your email address
                                    </p>
                                </div>

                                {/* Phone */}
                                <div className="space-y-2">
                                    <Label htmlFor="phone">Phone Number</Label>
                                    <div className="flex gap-2">
                                        <Phone className="h-5 w-5 text-muted-foreground mt-2" />
                                        <Input id="phone" type="tel" placeholder="+1 (555) 123-4567" disabled className="flex-1" />
                                    </div>
                                </div>

                                {/* Company */}
                                <div className="space-y-2">
                                    <Label htmlFor="company">Company</Label>
                                    <div className="flex gap-2">
                                        <Building2 className="h-5 w-5 text-muted-foreground mt-2" />
                                        <Input id="company" placeholder="Acme Manufacturing Inc." disabled className="flex-1" />
                                    </div>
                                </div>

                                {/* Location */}
                                <div className="space-y-2">
                                    <Label htmlFor="location">Location</Label>
                                    <div className="flex gap-2">
                                        <MapPin className="h-5 w-5 text-muted-foreground mt-2" />
                                        <Input id="location" placeholder="San Francisco, CA" disabled className="flex-1" />
                                    </div>
                                </div>

                                {/* Role and Join Date (Read-only) */}
                                <div className="grid md:grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                        <Label>Role</Label>
                                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                            <User className="h-4 w-4" />
                                            Account Administrator
                                        </div>
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Member Since</Label>
                                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                            <Calendar className="h-4 w-4" />
                                            January 2024
                                        </div>
                                    </div>
                                </div>

                                {/* Action Buttons */}
                                <div className="flex gap-3 pt-4">
                                    <Button type="button" disabled>
                                        Save Changes
                                    </Button>
                                    <Button type="button" variant="outline" asChild>
                                        <Link href="/settings">Cancel</Link>
                                    </Button>
                                </div>
                            </form>
                        </CardContent>
                    </Card>

                    {/* Avatar Section */}
                    <Card className="mt-6">
                        <CardHeader>
                            <CardTitle>Profile Picture</CardTitle>
                            <CardDescription>
                                Upload a profile picture to personalize your account
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="flex items-center gap-6">
                                <div className="h-20 w-20 rounded-full bg-gradient-to-br from-primary to-primary/50 flex items-center justify-center text-white text-2xl font-bold">
                                    JD
                                </div>
                                <div className="flex-1">
                                    <Button variant="outline" disabled>
                                        Upload New Picture
                                    </Button>
                                    <p className="text-xs text-muted-foreground mt-2">
                                        JPG, PNG or GIF. Max size 2MB.
                                    </p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Info Note */}
                    <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
                        <p className="text-sm text-blue-900 dark:text-blue-200">
                            <strong>Note:</strong> Profile editing is currently in development. To update your information,
                            please contact support at support@regengine.co.
                        </p>
                    </div>
                </div>
            </div>        </>
    );
}
