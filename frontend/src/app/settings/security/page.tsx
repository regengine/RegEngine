'use client';

import Link from 'next/link';
import { Shield, Lock, Key, Smartphone, ArrowLeft, Clock } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

const PLANNED_FEATURES = [
    {
        icon: Lock,
        title: 'Password Management',
        description:
            'Change your account password directly from the dashboard. Includes password strength validation and breach detection powered by HaveIBeenPwned.',
        eta: 'Q2 2026',
    },
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
                        Advanced security controls for your RegEngine account
                    </p>
                </div>

                {/* Current Security Status */}
                <Card className="mb-8 border-primary/20">
                    <CardHeader>
                        <div className="flex items-center gap-2">
                            <Shield className="h-5 w-5 text-primary" />
                            <CardTitle>Current Security</CardTitle>
                        </div>
                        <CardDescription>
                            Your account is protected by your login credentials and session tokens.
                            For immediate security concerns such as password resets or account lockouts,
                            contact <a href="mailto:security@regengine.co" className="text-primary underline underline-offset-2">security@regengine.co</a>.
                        </CardDescription>
                    </CardHeader>
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
