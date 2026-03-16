import type { Metadata } from 'next';
import Link from 'next/link';
import {
    ArrowLeft,
    ArrowRight,
    AlertTriangle,
    Clock,
    HeadphonesIcon,
    Layers,
    LifeBuoy,
    Mail,
    MessageCircle,
    Phone,
    ShieldAlert,
    Siren,
    Users,
    Zap,
} from 'lucide-react';
import { SUPPORT_CHANNELS } from '@/lib/customer-readiness';

export const metadata: Metadata = {
    title: 'Support & Escalation Model | RegEngine',
    description:
        'Response windows, escalation paths, recall emergency procedures, and support boundaries by plan tier.',
    openGraph: {
        title: 'Support & Escalation Model | RegEngine',
        description: 'Support and escalation model for RegEngine FSMA 204 compliance platform.',
        url: 'https://www.regengine.co/trust/support',        type: 'website',
    },
};

const card = 'rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] shadow-sm';
const sectionAlt = 'border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]';

const ESCALATION_PATH = [
    {
        step: '1',
        title: 'Self-serve documentation',
        description: 'FSMA 204 Guide, API docs, FTL Checker, and compliance dashboard. Most operational questions are answered here without waiting for a human.',
        icon: LifeBuoy,
        color: 'bg-blue-500/15 text-blue-400',
        availability: 'Always available',
    },
    {
        step: '2',
        title: 'Email support',
        description: 'Standard support channel for configuration questions, export issues, data mapping help, and non-urgent compliance questions.',
        icon: Mail,
        color: 'bg-emerald-500/15 text-emerald-400',
        availability: 'Business hours · All plans',
    },
    {
        step: '3',
        title: 'Priority queue',
        description: 'Faster response for production issues affecting compliance workflows — ingestion failures, scoring errors, export failures, or integration breakages.',        icon: Zap,
        color: 'bg-amber-500/15 text-amber-400',
        availability: 'Business hours · Growth and Enterprise',
    },
    {
        step: '4',
        title: 'Emergency recall escalation',
        description: 'Dedicated path for active FDA investigations or live recall events. Direct founder access for coordination on data exports, regulatory response packaging, and timeline management.',
        icon: Siren,
        color: 'bg-red-500/15 text-red-400',
        availability: 'Extended hours · Enterprise (contractual)',
    },
];

const SUPPORT_BOUNDARIES = [
    {
        title: 'What support covers',
        items: [
            'Platform configuration and data mapping',
            'Export format questions and scheduling',
            'Compliance scoring interpretation',
            'Integration troubleshooting',
            'Ingestion error diagnosis',
            'Account and billing questions',
        ],
    },
    {
        title: 'What support does not cover',
        items: [            'Regulatory legal advice or audit representation',
            'Upstream ERP/WMS system administration',
            'Custom report development outside your plan',
            'Recall operations or logistics coordination',
            'Food safety consulting or PCQI services',
            'Guaranteed SLAs without enterprise contract',
        ],
    },
];

export default function SupportPage() {
    return (
        <div className="re-page">
            {/* Header */}
            <section className="relative z-[2] max-w-[860px] mx-auto pt-14 sm:pt-20 px-4 sm:px-6 pb-10 sm:pb-14">
                <Link
                    href="/trust"
                    className="inline-flex items-center gap-1.5 text-sm text-[var(--re-text-muted)] hover:text-[var(--re-brand)] transition-colors mb-6"
                >
                    <ArrowLeft className="h-3.5 w-3.5" />
                    Trust Center
                </Link>
                <span className="block text-[11px] font-mono font-medium text-[var(--re-text-disabled)] tracking-widest uppercase">
                    Support &amp; Escalation
                </span>
                <h1 className="text-4xl font-bold text-[var(--re-text-primary)] mt-4 mb-4 leading-tight">
                    Who to call, when, and what to expect
                </h1>                <p className="text-base text-[var(--re-text-muted)] leading-relaxed max-w-[720px]">
                    Support posture depends on plan tier. This page documents the escalation path from self-serve through
                    emergency recall response so your team knows exactly what&apos;s available before they need it.
                </p>
            </section>

            {/* Escalation path */}
            <section className={`relative z-[2] ${sectionAlt}`}>
                <div className="max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                    <h2 className="text-2xl font-bold text-[var(--re-text-primary)] mb-2">Escalation path</h2>
                    <p className="text-sm text-[var(--re-text-muted)] mb-6 max-w-[720px]">
                        Four tiers, from self-serve to emergency recall. Each tier has a defined availability window and plan requirement.
                    </p>
                    <div className="space-y-3">
                        {ESCALATION_PATH.map((tier) => {
                            const Icon = tier.icon;
                            return (
                                <div key={tier.step} className={`${card} p-5 flex gap-4`}>
                                    <div className={`w-10 h-10 rounded-xl ${tier.color} flex items-center justify-center flex-shrink-0`}>
                                        <Icon className="h-5 w-5" />
                                    </div>
                                    <div className="flex-1">
                                        <div className="flex items-start justify-between gap-3">
                                            <div className="text-sm font-semibold text-[var(--re-text-primary)]">{tier.title}</div>
                                            <span className="text-[10px] uppercase tracking-wider text-[var(--re-text-disabled)] flex-shrink-0 mt-0.5">{tier.availability}</span>
                                        </div>
                                        <p className="text-sm text-[var(--re-text-muted)] mt-1.5 leading-relaxed">{tier.description}</p>
                                    </div>
                                </div>
                            );
                        })}                    </div>
                </div>
            </section>

            {/* Response windows by plan */}
            <section className="relative z-[2] max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                <h2 className="text-2xl font-bold text-[var(--re-text-primary)] mb-2">Response windows by plan</h2>
                <p className="text-sm text-[var(--re-text-muted)] mb-6 max-w-[720px]">
                    Response windows are target timeframes, not contractual SLAs unless you have an enterprise agreement.
                </p>
                <div className="space-y-3">
                    {SUPPORT_CHANNELS.map((channel) => (
                        <div key={channel.tier} className={`${card} p-5`}>
                            <div className="flex items-center justify-between gap-3 mb-2">
                                <div className="text-base font-semibold text-[var(--re-text-primary)]">{channel.tier}</div>
                                <div className="flex items-center gap-1.5 text-sm text-[var(--re-text-muted)]">
                                    <Clock className="h-3.5 w-3.5" />
                                    {channel.responseWindow}
                                </div>
                            </div>
                            <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">{channel.escalation}</p>
                            <p className="text-xs text-[var(--re-text-disabled)] mt-2">{channel.notes}</p>
                        </div>
                    ))}
                </div>
            </section>
            {/* Recall emergency */}
            <section className={`relative z-[2] ${sectionAlt}`}>
                <div className="max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                    <h2 className="text-2xl font-bold text-[var(--re-text-primary)] mb-4">During a live recall</h2>
                    <div className={`${card} p-6 border-red-500/20 bg-red-500/[0.02]`}>
                        <div className="flex items-start gap-4">
                            <div className="w-10 h-10 rounded-xl bg-red-500/15 flex items-center justify-center flex-shrink-0">
                                <ShieldAlert className="h-5 w-5 text-red-400" />
                            </div>
                            <div>
                                <h3 className="text-base font-semibold text-[var(--re-text-primary)] mb-2">What RegEngine does during a recall</h3>
                                <ul className="space-y-2 text-sm text-[var(--re-text-muted)]">
                                    <li>Generates FDA-formatted sortable spreadsheet for the affected product and date range</li>
                                    <li>Provides hash-chain verification proof for all records in the recall scope</li>
                                    <li>Exports complete CTE/KDE trail for affected lots with one-click bundle</li>
                                    <li>Enterprise customers receive direct founder coordination for timeline management</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                    <div className={`${card} p-6 mt-3`}>
                        <div className="flex items-start gap-4">
                            <div className="w-10 h-10 rounded-xl bg-amber-500/15 flex items-center justify-center flex-shrink-0">
                                <AlertTriangle className="h-5 w-5 text-amber-400" />
                            </div>
                            <div>
                                <h3 className="text-base font-semibold text-[var(--re-text-primary)] mb-2">What RegEngine does not do during a recall</h3>
                                <ul className="space-y-2 text-sm text-[var(--re-text-muted)]">                                    <li>RegEngine does not coordinate recall logistics, supplier notifications, or retail removals</li>
                                    <li>RegEngine does not provide legal representation or regulatory advice</li>
                                    <li>RegEngine does not guarantee FDA acceptance of any export or report format</li>
                                    <li>Public support windows are not a substitute for your recall-readiness plan</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Support boundaries */}
            <section className="relative z-[2] max-w-[980px] mx-auto py-10 sm:py-14 px-4 sm:px-6">
                <h2 className="text-2xl font-bold text-[var(--re-text-primary)] mb-4">Support scope and boundaries</h2>
                <div className="grid gap-4 md:grid-cols-2">
                    {SUPPORT_BOUNDARIES.map((group) => (
                        <div key={group.title} className={`${card} p-5`}>
                            <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-3">{group.title}</h3>
                            <ul className="space-y-2">
                                {group.items.map((item, i) => (
                                    <li key={i} className="flex items-start gap-2 text-sm text-[var(--re-text-muted)]">
                                        <span className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${
                                            group.title.includes('not') ? 'bg-red-500/50' : 'bg-emerald-500/50'
                                        }`} />
                                        {item}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    ))}                </div>
            </section>

            {/* CTA */}
            <section className={`relative z-[2] ${sectionAlt}`}>
                <div className="max-w-[860px] mx-auto py-10 sm:py-14 px-4 sm:px-6 text-center">
                    <p className="text-sm text-[var(--re-text-muted)] mb-4">
                        Questions about support coverage for your plan? Enterprise escalation terms are defined in your service agreement.
                    </p>
                    <div className="flex flex-wrap gap-3 justify-center">
                        <Link href="/pricing">
                            <span className="inline-flex items-center gap-1.5 text-sm text-[var(--re-brand)] hover:opacity-80 transition-opacity">
                                Compare plans <ArrowRight className="h-3.5 w-3.5" />
                            </span>
                        </Link>
                        <Link href="/contact">
                            <span className="inline-flex items-center gap-1.5 text-sm text-[var(--re-text-muted)] hover:text-[var(--re-brand)] transition-colors">
                                Contact us <ArrowRight className="h-3.5 w-3.5" />
                            </span>
                        </Link>
                        <Link href="/trust">
                            <span className="inline-flex items-center gap-1.5 text-sm text-[var(--re-text-muted)] hover:text-[var(--re-brand)] transition-colors">
                                Trust Center <ArrowRight className="h-3.5 w-3.5" />
                            </span>
                        </Link>
                    </div>
                </div>
            </section>
        </div>
    );
}
