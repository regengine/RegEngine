'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Breadcrumbs } from '@/components/layout/breadcrumbs';
import {
    Activity,
    CheckCircle,
    XCircle,
    AlertTriangle,
    Clock,
    Shield,
    Phone,
    Mail,
    ExternalLink,
} from 'lucide-react';

interface ServiceStatus {
    name: string;
    description: string;
    status: 'operational' | 'degraded' | 'down' | 'checking';
    latency?: number;
    lastChecked?: string;
}

const SERVICES: Omit<ServiceStatus, 'status' | 'latency' | 'lastChecked'>[] = [
    { name: 'Graph Service', description: 'Traceability graph, recall drills, FSMA metrics' },
    { name: 'Ingestion Service', description: 'CTE/KDE webhook ingestion, EPCIS processing' },
    { name: 'Compliance Service', description: 'Validation rules, checklists, FTL categories' },
    { name: 'Admin Service', description: 'Authentication, tenant management, API keys' },
];

const SERVICE_ENDPOINTS: Record<string, string> = {
    'Graph Service': '/api/fsma/metrics/health',
    'Compliance Service': '/api/compliance/health',
};

const ESCALATION_MODEL = [
    {
        scenario: 'Active recall event (FDA records request)',
        response: 'Immediate priority',
        channel: 'Emergency email + in-product alert',
        coverage: 'All tiers',
        detail: 'Export packages are pre-generated and available on demand. Customers should verify recurring exports are configured before an active event.',
    },
    {
        scenario: 'Ingestion pipeline failure',
        response: 'Within 4 hours',
        channel: 'Product health dashboard + email alert',
        coverage: 'Scale + Enterprise',
        detail: 'Ingestion failures are retryable. Events are queued and reprocessed when the pipeline recovers.',
    },
    {
        scenario: 'Data quality drift alert',
        response: 'Within 1 business day',
        channel: 'In-product drift dashboard',
        coverage: 'All tiers',
        detail: 'Drift alerts flag supplier format changes or quality degradation. Resolution requires upstream supplier coordination.',
    },
    {
        scenario: 'Export generation failure',
        response: 'Within 4 hours',
        channel: 'Export job status page + email',
        coverage: 'Scale + Enterprise',
        detail: 'Failed exports are flagged for re-processing. Customers maintain access to previous successful exports.',
    },
    {
        scenario: 'Platform outage (all services)',
        response: 'Immediate',
        channel: 'Status page + email to all tenants',
        coverage: 'All tiers',
        detail: 'Full platform outages trigger incident response. Historical exports remain available if stored externally.',
    },
];

const UPTIME_COMMITMENTS = [
    { tier: 'Growth', uptime: '99.5%', detail: 'Best-effort monitoring, email-based incident notification' },
    { tier: 'Scale', uptime: '99.9%', detail: 'Priority monitoring, proactive incident communication, 4-hour response SLA' },
    { tier: 'Enterprise', uptime: 'Custom SLA', detail: 'Negotiated uptime targets, named contacts, dedicated escalation tree' },
];

function StatusIcon({ status }: { status: ServiceStatus['status'] }) {
    switch (status) {
        case 'operational':
            return <CheckCircle className="h-5 w-5 text-green-500" />;
        case 'degraded':
            return <AlertTriangle className="h-5 w-5 text-amber-500" />;
        case 'down':
            return <XCircle className="h-5 w-5 text-red-500" />;
        case 'checking':
            return <Activity className="h-5 w-5 text-muted-foreground animate-pulse" />;
    }
}

function statusLabel(status: ServiceStatus['status']) {
    switch (status) {
        case 'operational': return 'Operational';
        case 'degraded': return 'Degraded';
        case 'down': return 'Unreachable';
        case 'checking': return 'Checking...';
    }
}

function statusBadgeClass(status: ServiceStatus['status']) {
    switch (status) {
        case 'operational': return 'bg-green-500/10 text-green-500 border-green-500/20';
        case 'degraded': return 'bg-amber-500/10 text-amber-500 border-amber-500/20';
        case 'down': return 'bg-red-500/10 text-red-500 border-red-500/20';
        case 'checking': return 'bg-muted text-muted-foreground';
    }
}

export default function StatusPage() {
    const [services, setServices] = useState<ServiceStatus[]>(
        SERVICES.map(s => ({ ...s, status: 'checking' as const }))
    );

    useEffect(() => {
        async function checkService(index: number, endpoint: string | undefined) {
            if (!endpoint) {
                setServices(prev => prev.map((s, i) =>
                    i === index ? { ...s, status: 'down' as const, lastChecked: new Date().toISOString() } : s
                ));
                return;
            }

            const start = performance.now();
            try {
                const resp = await fetch(endpoint, { signal: AbortSignal.timeout(5000) });
                const latency = Math.round(performance.now() - start);
                setServices(prev => prev.map((s, i) =>
                    i === index ? {
                        ...s,
                        status: resp.ok ? 'operational' as const : 'degraded' as const,
                        latency,
                        lastChecked: new Date().toISOString(),
                    } : s
                ));
            } catch {
                setServices(prev => prev.map((s, i) =>
                    i === index ? {
                        ...s,
                        status: 'down' as const,
                        latency: undefined,
                        lastChecked: new Date().toISOString(),
                    } : s
                ));
            }
        }

        SERVICES.forEach((s, i) => {
            checkService(i, SERVICE_ENDPOINTS[s.name]);
        });

        const interval = setInterval(() => {
            SERVICES.forEach((s, i) => {
                checkService(i, SERVICE_ENDPOINTS[s.name]);
            });
        }, 30_000);

        return () => clearInterval(interval);
    }, []);

    const allOperational = services.every(s => s.status === 'operational');
    const anyDown = services.some(s => s.status === 'down');

    return (
        <div className="min-h-screen bg-background">
            <section className="relative overflow-hidden border-b border-[var(--re-border-default)]">
                <div className="absolute inset-0 bg-gradient-to-br from-[var(--re-brand)]/5 to-transparent" />
                <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
                    <Breadcrumbs items={[{ label: 'System Status' }]} />
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="py-12 space-y-4"
                    >
                        <div className="flex items-center gap-3">
                            <div className={`p-2 rounded-full ${allOperational ? 'bg-green-500/10' : anyDown ? 'bg-red-500/10' : 'bg-amber-500/10'}`}>
                                {allOperational ? (
                                    <CheckCircle className="h-8 w-8 text-green-500" />
                                ) : anyDown ? (
                                    <XCircle className="h-8 w-8 text-red-500" />
                                ) : (
                                    <AlertTriangle className="h-8 w-8 text-amber-500" />
                                )}
                            </div>
                            <div>
                                <h1 className="text-3xl font-bold">
                                    {allOperational ? 'All Systems Operational' : anyDown ? 'Service Disruption' : 'Degraded Performance'}
                                </h1>
                                <p className="text-muted-foreground mt-1">
                                    Real-time health checks for RegEngine backend services
                                </p>
                            </div>
                        </div>
                    </motion.div>
                </div>
            </section>

            <section className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
                <h2 className="text-xl font-bold mb-6">Service health</h2>
                <div className="grid gap-4 md:grid-cols-2">
                    {services.map((service, i) => (
                        <motion.div
                            key={service.name}
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: i * 0.05 }}
                        >
                            <Card>
                                <CardContent className="pt-6">
                                    <div className="flex items-start justify-between">
                                        <div className="flex items-center gap-3">
                                            <StatusIcon status={service.status} />
                                            <div>
                                                <p className="font-semibold">{service.name}</p>
                                                <p className="text-sm text-muted-foreground">{service.description}</p>
                                            </div>
                                        </div>
                                        <Badge className={statusBadgeClass(service.status)}>
                                            {statusLabel(service.status)}
                                        </Badge>
                                    </div>
                                    {service.latency !== undefined && (
                                        <p className="text-xs text-muted-foreground mt-3">
                                            <Clock className="inline h-3 w-3 mr-1" />
                                            {service.latency}ms response time
                                        </p>
                                    )}
                                </CardContent>
                            </Card>
                        </motion.div>
                    ))}
                </div>
            </section>

            <section className="border-t">
                <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
                    <h2 className="text-xl font-bold mb-2">Escalation model</h2>
                    <p className="text-sm text-muted-foreground mb-6">
                        Documented response windows by scenario type. This model is not founder-dependent — it defines the operational contract for each plan tier.
                    </p>
                    <div className="overflow-x-auto rounded-xl border">
                        <table className="w-full border-collapse">
                            <thead>
                                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                                    <th className="p-3">Scenario</th>
                                    <th className="p-3">Response</th>
                                    <th className="p-3">Channel</th>
                                    <th className="p-3">Coverage</th>
                                </tr>
                            </thead>
                            <tbody>
                                {ESCALATION_MODEL.map((item) => (
                                    <tr key={item.scenario} className="border-b align-top">
                                        <td className="p-3">
                                            <p className="text-sm font-medium">{item.scenario}</p>
                                            <p className="text-xs text-muted-foreground mt-1">{item.detail}</p>
                                        </td>
                                        <td className="p-3 text-sm">{item.response}</td>
                                        <td className="p-3 text-sm text-muted-foreground">{item.channel}</td>
                                        <td className="p-3 text-sm text-muted-foreground">{item.coverage}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            </section>

            <section className="border-t">
                <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
                    <h2 className="text-xl font-bold mb-6">Uptime commitments by tier</h2>
                    <div className="grid gap-4 md:grid-cols-3">
                        {UPTIME_COMMITMENTS.map((tier) => (
                            <Card key={tier.tier}>
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-lg">{tier.tier}</CardTitle>
                                    <CardDescription>{tier.detail}</CardDescription>
                                </CardHeader>
                                <CardContent>
                                    <p className="text-3xl font-bold">{tier.uptime}</p>
                                    <p className="text-xs text-muted-foreground mt-1">Target uptime SLA</p>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                </div>
            </section>

            <section className="border-t">
                <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
                    <h2 className="text-xl font-bold mb-6">Emergency contact</h2>
                    <div className="grid gap-4 md:grid-cols-2">
                        <Card>
                            <CardContent className="pt-6">
                                <div className="flex items-center gap-3">
                                    <Mail className="h-5 w-5 text-muted-foreground" />
                                    <div>
                                        <p className="font-medium">Recall emergency</p>
                                        <p className="text-sm text-muted-foreground">support@regengine.co</p>
                                        <p className="text-xs text-muted-foreground mt-1">
                                            Subject line: RECALL EMERGENCY — [Tenant ID] for priority routing
                                        </p>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                        <Card>
                            <CardContent className="pt-6">
                                <div className="flex items-center gap-3">
                                    <Shield className="h-5 w-5 text-muted-foreground" />
                                    <div>
                                        <p className="font-medium">Security disclosure</p>
                                        <p className="text-sm text-muted-foreground">security@regengine.co</p>
                                        <p className="text-xs text-muted-foreground mt-1">
                                            For vulnerability reports and security-related concerns
                                        </p>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                </div>
            </section>
        </div>
    );
}
