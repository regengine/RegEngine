'use client';

import Link from 'next/link';
import { LifeBuoy, ShieldAlert, FileText, Mail } from 'lucide-react';
import { SUPPORT_CHANNELS } from '@/lib/customer-readiness';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export default function SupportSettingsPage() {
    return (
        <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            <div className="max-w-5xl mx-auto px-4 py-12 space-y-6">
                <div>
                    <h1 className="text-4xl font-bold mb-2 flex items-center gap-3">
                        <LifeBuoy className="h-8 w-8 text-[var(--re-brand)]" />
                        Support & Escalation
                    </h1>
                    <p className="text-muted-foreground">
                        Document support expectations, emergency recall escalation, and where your team should look before a live regulator request.
                    </p>
                </div>

                <div className="grid gap-4 md:grid-cols-3">
                    {SUPPORT_CHANNELS.map((channel) => (
                        <Card key={channel.tier}>
                            <CardHeader>
                                <CardTitle>{channel.tier}</CardTitle>
                                <CardDescription>{channel.responseWindow}</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-2 text-sm text-muted-foreground">
                                <p>{channel.escalation}</p>
                                <p>{channel.notes}</p>
                            </CardContent>
                        </Card>
                    ))}
                </div>

                <Card>
                    <CardHeader>
                        <CardTitle>Emergency recall workflow</CardTitle>
                        <CardDescription>
                            Use this flow if you need to produce an FDA-style package under time pressure.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3 text-sm text-muted-foreground">
                        <p className="inline-flex items-start gap-2"><ShieldAlert className="h-4 w-4 mt-0.5 text-[var(--re-brand)]" /> Run a live drill or export from the Recall Drill Workspace before reaching out for support.</p>
                        <p className="inline-flex items-start gap-2"><FileText className="h-4 w-4 mt-0.5 text-[var(--re-brand)]" /> Confirm your recurring archive jobs completed successfully so you have off-platform evidence available.</p>
                        <p className="inline-flex items-start gap-2"><Mail className="h-4 w-4 mt-0.5 text-[var(--re-brand)]" /> Contact support@regengine.co for operational issues. Custom SLA and named contacts apply only where contractually negotiated.</p>
                    </CardContent>
                </Card>

                <div className="rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-5 text-sm text-muted-foreground">
                    Related pages:{' '}
                    <Link href="/trust" className="text-[var(--re-brand)] underline">Trust Center</Link>
                    {' '}·{' '}
                    <Link href="/dashboard/export-jobs" className="text-[var(--re-brand)] underline">Archive Jobs</Link>
                    {' '}·{' '}
                    <Link href="/dashboard/recall-drills" className="text-[var(--re-brand)] underline">Recall Drill Workspace</Link>
                </div>
            </div>
        </div>
    );
}
