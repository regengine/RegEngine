'use client';

import Link from 'next/link';
import { ShieldAlert, FileText, Mail } from 'lucide-react';
import { SUPPORT_CHANNELS } from '@/lib/customer-readiness';
import { NOT_SET } from '@/lib/empty-values';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

const RELATED_LINKS = [
    { href: '/trust', label: 'Trust Center' },
    { href: '/dashboard/export-jobs', label: 'FDA Export' },
    { href: '/dashboard/recall-drills', label: 'Recall Drills' },
] as const;

export default function SupportSettingsPage() {
    return (
        <PageContainer>
            <PageHeader
                title="Support & Escalation"
                description="Document support expectations, emergency recall escalation, and where your team should look before a live regulator request."
            />

            <div className="space-y-6">
                <div className="grid gap-4 md:grid-cols-3">
                    {SUPPORT_CHANNELS.map((channel) => (
                        <Card key={channel.tier}>
                            <CardHeader>
                                <div className="min-w-0">
                                    <CardTitle>{channel.tier || NOT_SET}</CardTitle>
                                    <CardDescription>{channel.responseWindow || NOT_SET}</CardDescription>
                                </div>
                            </CardHeader>
                            <CardContent className="space-y-2 text-ui text-re-text-secondary">
                                <p>{channel.escalation || NOT_SET}</p>
                                <p>{channel.notes || NOT_SET}</p>
                            </CardContent>
                        </Card>
                    ))}
                </div>

                <Card>
                    <CardHeader>
                        <div className="min-w-0">
                            <CardTitle>Emergency recall workflow</CardTitle>
                            <CardDescription>
                                Use this flow if you need to produce an FDA-style package under time pressure.
                            </CardDescription>
                        </div>
                    </CardHeader>
                    <CardContent className="p-0">
                        <ul className="divide-y divide-re-border-subtle">
                            <li className="flex items-start gap-2.5 px-5 py-3 text-ui text-re-text-secondary">
                                <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                <span>Run a live drill or export from Recall Drills before reaching out for support.</span>
                            </li>
                            <li className="flex items-start gap-2.5 px-5 py-3 text-ui text-re-text-secondary">
                                <FileText className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                <span>Confirm your recurring export jobs completed successfully so you have off-platform evidence available.</span>
                            </li>
                            <li className="flex items-start gap-2.5 px-5 py-3 text-ui text-re-text-secondary">
                                <Mail className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                <span>Contact support@regengine.co for operational issues. Custom SLA and named contacts apply only where contractually negotiated.</span>
                            </li>
                        </ul>
                    </CardContent>
                </Card>

                <Card>
                    <CardContent className="flex flex-wrap items-center gap-x-2 gap-y-1 text-ui text-re-text-secondary">
                        <span>Related pages:</span>
                        {RELATED_LINKS.map((link, index) => (
                            <span key={link.href} className="inline-flex items-center gap-2">
                                {index > 0 && <span aria-hidden="true">·</span>}
                                <Link
                                    href={link.href}
                                    className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
                                >
                                    {link.label}
                                </Link>
                            </span>
                        ))}
                    </CardContent>
                </Card>
            </div>
        </PageContainer>
    );
}
