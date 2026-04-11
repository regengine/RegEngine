'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { User, Mail, Building2, Phone, MapPin, Calendar, ArrowLeft, Info } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/lib/auth-context';

export default function ProfileSettingsPage() {
    const { user } = useAuth();
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [phone, setPhone] = useState('');
    const [company, setCompany] = useState('');
    const [location, setLocation] = useState('');
    const [saveMessage, setSaveMessage] = useState<string | null>(null);

    // Pre-fill what we can from the authenticated user
    useEffect(() => {
        if (user) {
            const meta = (user as { user_metadata?: { full_name?: string; name?: string } }).user_metadata;
            if (meta?.full_name || meta?.name) {
                const parts = (meta.full_name ?? meta.name ?? '').split(' ');
                setFirstName(parts[0] ?? '');
                setLastName(parts.slice(1).join(' '));
            }
        }
    }, [user]);

    const handleSave = (e: React.FormEvent) => {
        e.preventDefault();
        // Profile editing endpoint is not yet implemented on the backend.
        // Show an honest "coming soon" notice rather than silently dropping data.
        setSaveMessage('Profile editing is coming soon. To update your information now, email support@regengine.co.');
        setTimeout(() => setSaveMessage(null), 6000);
    };

    const email = user?.email ?? '';
    const initials = [firstName, lastName]
        .filter(Boolean)
        .map((n) => n[0])
        .join('')
        .toUpperCase() || (email ? email[0].toUpperCase() : '?');

    return (
        <>
            <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
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

                    {/* Not-yet-implemented notice */}
                    <div className="mb-6 p-4 rounded-lg border border-amber-200 dark:border-amber-800 bg-re-warning-muted dark:bg-re-warning/20 flex items-start gap-3">
                        <Info className="h-4 w-4 text-re-warning dark:text-re-warning mt-0.5 flex-shrink-0" />
                        <p className="text-sm text-re-warning dark:text-re-warning">
                            <strong>Profile editing is coming soon.</strong> Fields are editable but changes are not yet saved to the server.
                            To update your information now, email <a href="mailto:support@regengine.co" className="underline">support@regengine.co</a>.
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
                            <form className="space-y-6" onSubmit={handleSave}>
                                {/* Name Fields */}
                                <div className="grid md:grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="firstName">First Name</Label>
                                        <Input
                                            id="firstName"
                                            placeholder="Jane"
                                            value={firstName}
                                            onChange={(e) => setFirstName(e.target.value)}
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label htmlFor="lastName">Last Name</Label>
                                        <Input
                                            id="lastName"
                                            placeholder="Smith"
                                            value={lastName}
                                            onChange={(e) => setLastName(e.target.value)}
                                        />
                                    </div>
                                </div>

                                {/* Email — read-only, sourced from auth */}
                                <div className="space-y-2">
                                    <Label htmlFor="email">Email Address</Label>
                                    <div className="flex gap-2">
                                        <Mail className="h-5 w-5 text-muted-foreground mt-2" />
                                        <Input
                                            id="email"
                                            type="email"
                                            value={email}
                                            readOnly
                                            className="flex-1 bg-muted/50 cursor-not-allowed"
                                        />
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
                                        <Input
                                            id="phone"
                                            type="tel"
                                            placeholder="+1 (555) 123-4567"
                                            value={phone}
                                            onChange={(e) => setPhone(e.target.value)}
                                            className="flex-1"
                                        />
                                    </div>
                                </div>

                                {/* Company */}
                                <div className="space-y-2">
                                    <Label htmlFor="company">Company</Label>
                                    <div className="flex gap-2">
                                        <Building2 className="h-5 w-5 text-muted-foreground mt-2" />
                                        <Input
                                            id="company"
                                            placeholder="Your company name"
                                            value={company}
                                            onChange={(e) => setCompany(e.target.value)}
                                            className="flex-1"
                                        />
                                    </div>
                                </div>

                                {/* Location */}
                                <div className="space-y-2">
                                    <Label htmlFor="location">Location</Label>
                                    <div className="flex gap-2">
                                        <MapPin className="h-5 w-5 text-muted-foreground mt-2" />
                                        <Input
                                            id="location"
                                            placeholder="City, State"
                                            value={location}
                                            onChange={(e) => setLocation(e.target.value)}
                                            className="flex-1"
                                        />
                                    </div>
                                </div>

                                {/* Role and Email */}
                                <div className="grid md:grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                        <Label>Role</Label>
                                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                            <User className="h-4 w-4" />
                                            Account Member
                                        </div>
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Account Email</Label>
                                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                            <Calendar className="h-4 w-4" />
                                            {email || 'Not signed in'}
                                        </div>
                                    </div>
                                </div>

                                {/* Save feedback */}
                                {saveMessage && (
                                    <div className="p-3 rounded-lg border border-amber-200 dark:border-amber-800 bg-re-warning-muted dark:bg-re-warning/20 text-sm text-re-warning dark:text-re-warning">
                                        {saveMessage}
                                    </div>
                                )}

                                {/* Action Buttons */}
                                <div className="flex gap-3 pt-4">
                                    <Button type="submit">
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
                                Profile picture upload is coming soon
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="flex items-center gap-6">
                                <div className="h-20 w-20 rounded-full bg-gradient-to-br from-primary to-primary/50 flex items-center justify-center text-white text-2xl font-bold">
                                    {initials}
                                </div>
                                <div className="flex-1">
                                    <Button variant="outline" disabled>
                                        Upload New Picture
                                    </Button>
                                    <p className="text-xs text-muted-foreground mt-2">
                                        Coming soon — JPG, PNG or GIF. Max size 2MB.
                                    </p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </>
    );
}
