'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { User, Mail, Building2, Phone, MapPin, ArrowLeft } from 'lucide-react';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/lib/auth-context';

export default function ProfileSettingsPage() {
    const { user } = useAuth();
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [phone, setPhone] = useState('');
    const [company, setCompany] = useState('');
    const [location, setLocation] = useState('');
    const [saveMessage, setSaveMessage] = useState<string | null>(null);

    // Prefill from the auth session, which resolves after mount. The fields
    // remain editable, so this is a one-way seed rather than derived state.
    useEffect(() => {
        if (user) {
            const meta = (user as { user_metadata?: { full_name?: string; name?: string } }).user_metadata;
            if (meta?.full_name || meta?.name) {
                const parts = (meta.full_name ?? meta.name ?? '').split(' ');
                // eslint-disable-next-line react-hooks/set-state-in-effect
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
        <PageContainer>
            {/* Back link - the shell owns the breadcrumb, this stays as the
                page's own return affordance. */}
            <Link
                href="/dashboard/settings"
                className="mb-4 inline-flex items-center gap-1.5 text-ui text-re-text-secondary transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
            >
                <ArrowLeft className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                Back to Settings
            </Link>

            <PageHeader
                title="Profile Settings"
                description="Manage your personal information and account details"
            />

            <div className="space-y-6">
                {/* Not-yet-implemented notice */}
                <Callout tone="warning">
                    <p>
                        <strong className="font-medium text-re-text-primary">Profile editing is coming soon.</strong> Fields are editable but changes are not yet saved to the server.
                        To update your information now, email{' '}
                        <a
                            href="mailto:support@regengine.co"
                            className="text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand"
                        >
                            support@regengine.co
                        </a>.
                    </p>
                </Callout>

                {/* Profile Form */}
                <Card>
                    <CardHeader>
                        <div className="min-w-0">
                            <CardTitle>Personal Information</CardTitle>
                            <CardDescription>
                                Update your profile information
                            </CardDescription>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <form className="space-y-6" onSubmit={handleSave}>
                            {/* Name Fields */}
                            <div className="grid gap-4 md:grid-cols-2">
                                <Field label="First Name" htmlFor="firstName">
                                    <Input
                                        id="firstName"
                                        placeholder="Jane"
                                        value={firstName}
                                        onChange={(e) => setFirstName(e.target.value)}
                                    />
                                </Field>
                                <Field label="Last Name" htmlFor="lastName">
                                    <Input
                                        id="lastName"
                                        placeholder="Smith"
                                        value={lastName}
                                        onChange={(e) => setLastName(e.target.value)}
                                    />
                                </Field>
                            </div>

                            {/* Email - read-only, sourced from auth */}
                            <Field
                                label="Email Address"
                                htmlFor="email"
                                hint="Contact support to change your email address"
                            >
                                <Input
                                    id="email"
                                    type="email"
                                    value={email}
                                    readOnly
                                    leadingIcon={<Mail strokeWidth={1.75} />}
                                    className="cursor-not-allowed bg-re-surface-inset"
                                />
                            </Field>

                            {/* Phone */}
                            <Field label="Phone Number" htmlFor="phone">
                                <Input
                                    id="phone"
                                    type="tel"
                                    placeholder="+1 (555) 123-4567"
                                    value={phone}
                                    onChange={(e) => setPhone(e.target.value)}
                                    leadingIcon={<Phone strokeWidth={1.75} />}
                                />
                            </Field>

                            {/* Company */}
                            <Field label="Company" htmlFor="company">
                                <Input
                                    id="company"
                                    placeholder="Your company name"
                                    value={company}
                                    onChange={(e) => setCompany(e.target.value)}
                                    leadingIcon={<Building2 strokeWidth={1.75} />}
                                />
                            </Field>

                            {/* Location */}
                            <Field label="Location" htmlFor="location">
                                <Input
                                    id="location"
                                    placeholder="City, State"
                                    value={location}
                                    onChange={(e) => setLocation(e.target.value)}
                                    leadingIcon={<MapPin strokeWidth={1.75} />}
                                />
                            </Field>

                            {/* Role and Email - read-only account facts */}
                            <dl className="grid gap-4 md:grid-cols-2">
                                <div className="space-y-2">
                                    <dt className="text-label text-re-text-muted">Role</dt>
                                    <dd className="flex items-center gap-2 text-ui text-re-text-secondary">
                                        <User className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                        Member
                                    </dd>
                                </div>
                                <div className="space-y-2">
                                    <dt className="text-label text-re-text-muted">Account Email</dt>
                                    <dd className="flex min-w-0 items-center gap-2 text-ui text-re-text-secondary">
                                        <Mail className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                        <span className="truncate font-mono text-[0.8125rem]">{email || 'Not signed in'}</span>
                                    </dd>
                                </div>
                            </dl>

                            {/* Save feedback */}
                            {saveMessage && (
                                <Callout tone="warning" role="status">
                                    {saveMessage}
                                </Callout>
                            )}

                            {/* Action Buttons */}
                            <div className="flex flex-wrap gap-3 pt-4">
                                <Button type="submit">
                                    Save Changes
                                </Button>
                                <Button type="button" variant="outline" asChild>
                                    <Link href="/dashboard/settings">Cancel</Link>
                                </Button>
                            </div>
                        </form>
                    </CardContent>
                </Card>

                {/* Avatar Section */}
                <Card>
                    <CardHeader>
                        <div className="min-w-0">
                            <CardTitle>Profile Picture</CardTitle>
                            <CardDescription>
                                Profile picture upload is coming soon
                            </CardDescription>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="flex flex-wrap items-center gap-6">
                            <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-full border border-re-border bg-re-surface-inset text-heading text-re-text-primary">
                                {initials}
                            </div>
                            <div className="min-w-0 flex-1">
                                <Button variant="outline" disabled>
                                    Upload New Picture
                                </Button>
                                <p className="mt-2 text-small text-re-text-tertiary">
                                    Coming soon: JPG, PNG or GIF. Max size 2MB.
                                </p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </PageContainer>
    );
}
