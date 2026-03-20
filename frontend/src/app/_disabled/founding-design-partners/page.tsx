import type { Metadata } from 'next';
import Link from 'next/link';
import {
    Shield, Zap, Users, Star, TrendingUp, FileCheck, Clock,
    Target, Flame, Wrench, CheckCircle2,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import AlphaSignupForm from './AlphaSignupForm';

export const metadata: Metadata = {
    title: 'Founding Design Partner Program | RegEngine',
    description: "Become a Founding Design Partner. Custom integrations, white-glove onboarding, locked-in pricing, and direct founder access for FSMA 204 compliance.",
    openGraph: {
        title: 'Founding Design Partner Program | RegEngine',
        description: "Become a Founding Design Partner. Custom integrations, white-glove onboarding, locked-in pricing, and direct founder access for FSMA 204 compliance.",
        url: 'https://www.regengine.co/alpha',
        type: 'website',
    },
};
const ALPHA_PERKS = [
    { Icon: Zap, title: 'Priority API Access', description: "Be the first to integrate with RegEngine's traceability API and shape the developer experience." },
    { Icon: TrendingUp, title: 'Founding Pricing — Locked In', description: 'Founding Design Partners lock in their pricing for the life of their account. No surprise increases.' },
    { Icon: Users, title: 'Direct Founder Access', description: 'Weekly office hours with the founding team. Your feedback helps inform product direction.' },
    { Icon: FileCheck, title: 'White-Glove Onboarding', description: 'Dedicated onboarding support to map your supply chain and configure your compliance profile.' },
    { Icon: Shield, title: 'Compliance Head Start', description: 'Get FSMA 204 compliant before the July 2028 deadline while your competitors scramble.' },
    { Icon: Star, title: 'Case Study Feature', description: "Be featured as a launch partner case study \u2014 great for your brand and compliance credibility." },
];

const TIMELINE = [
    { phase: 'Design Partner Cohort', status: 'current', date: 'Now Open', detail: 'Custom integrations \u00b7 Guided onboarding \u00b7 Direct founder access' },
    { phase: 'Customer Pilot Rollout', status: 'upcoming', date: 'Rolling', detail: 'Application review \u00b7 Customer-specific implementation' },
    { phase: 'FSMA 204 Deadline', status: 'deadline', date: 'Jul 2028', detail: 'FDA enforcement begins \u00b7 Retailer audits expected earlier' },
];
export default function AlphaPage() {
    return (
        <div className="re-page" style={{ minHeight: '100vh' }}>
            {/* ═══ HERO with subtle background visual ═══ */}
            <section className="relative z-[2] overflow-hidden" style={{ maxWidth: '800px', margin: '0 auto', padding: 'clamp(3.5rem, 8vw, 80px) clamp(1rem, 4vw, 24px) clamp(2.5rem, 6vw, 60px)', textAlign: 'center' }}>
                {/* Faint supply-chain grid background */}
                <div className="absolute inset-0 pointer-events-none opacity-[0.04]" style={{
                    backgroundImage: `
                        linear-gradient(var(--re-brand) 1px, transparent 1px),
                        linear-gradient(90deg, var(--re-brand) 1px, transparent 1px)
                    `,
                    backgroundSize: '60px 60px',
                    maskImage: 'radial-gradient(ellipse 70% 60% at 50% 40%, black 20%, transparent 80%)',
                    WebkitMaskImage: 'radial-gradient(ellipse 70% 60% at 50% 40%, black 20%, transparent 80%)',
                }} />
                {/* Accent glow */}
                <div className="absolute top-[-60px] left-1/2 -translate-x-1/2 w-[600px] h-[400px] pointer-events-none"
                    style={{ background: 'radial-gradient(ellipse, var(--re-brand-muted) 0%, transparent 70%)' }}
                />
                <div className="relative z-10">
                    <Badge className="bg-[var(--re-brand-muted)] text-[var(--re-brand)] border border-[var(--re-brand)]/20 mb-5 text-xs font-bold uppercase tracking-widest">
                        Founding Design Partner Program
                    </Badge>
                    <h1 className="text-[clamp(32px,5vw,48px)] font-bold text-[var(--re-text-primary)] leading-[1.1] mb-4">
                        Shape the future of<br />
                        <span className="bg-gradient-to-r from-[var(--re-brand)] to-emerald-400 bg-clip-text text-transparent">
                            food traceability
                        </span>
                    </h1>
                    <p className="text-lg text-[var(--re-text-muted)] max-w-[560px] mx-auto leading-relaxed mb-6">
                        Custom integrations. Guided rollout. Direct founder access.
                        Built for teams who want to be FSMA 204 ready before anyone asks.
                    </p>
                    <a href="#apply">
                        <button className="px-8 py-3.5 rounded-xl bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white font-semibold text-sm transition-all shadow-lg hover:shadow-xl hover:-translate-y-0.5 min-h-[48px] active:scale-[0.97]">
                            Apply to Become a Founding Design Partner →
                        </button>
                    </a>
                </div>
            </section>
            {/* ═══ PERKS GRID with shadows + hover ═══ */}
            <section className="relative z-[2]" style={{ maxWidth: '900px', margin: '0 auto', padding: '0 clamp(1rem, 4vw, 24px) clamp(2.5rem, 6vw, 60px)' }}>
                <h2 className="text-2xl font-bold text-[var(--re-text-primary)] text-center mb-8">
                    What design partners get
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {ALPHA_PERKS.map((perk) => (
                        <div
                            key={perk.title}
                            className="group rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6 shadow-sm hover:shadow-md hover:border-[var(--re-brand)] hover:-translate-y-0.5 transition-all"
                        >
                            <div className="w-10 h-10 rounded-xl bg-[var(--re-brand-muted)] flex items-center justify-center mb-4 group-hover:bg-[var(--re-brand)] transition-colors">
                                <perk.Icon className="w-5 h-5 text-[var(--re-brand)] group-hover:text-white transition-colors" />
                            </div>
                            <h3 className="text-[15px] font-semibold text-[var(--re-text-primary)] mb-1.5">
                                {perk.title}
                            </h3>
                            <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed">
                                {perk.description}
                            </p>
                        </div>
                    ))}
                </div>
            </section>
            {/* ═══ WHAT WE LOOK FOR — 3-Criteria Framework ═══ */}
            <section className="relative z-[2] border-t border-[var(--re-surface-border)]">
                <div style={{ maxWidth: '900px', margin: '0 auto', padding: 'clamp(2.5rem, 6vw, 60px) 24px' }}>
                    <h2 className="text-2xl font-bold text-[var(--re-text-primary)] text-center mb-3">
                        What we look for in design partners
                    </h2>
                    <p className="text-sm text-[var(--re-text-muted)] text-center max-w-[560px] mx-auto mb-10">
                        We evaluate every application on three criteria to ensure deep, productive partnerships {'\u2014'} not just signups.
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                        {/* Representativeness */}
                        <div className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6 shadow-sm">
                            <div className="w-10 h-10 rounded-xl bg-blue-500/10 flex items-center justify-center mb-4">
                                <Target className="w-5 h-5 text-blue-500" />
                            </div>
                            <h3 className="text-[15px] font-semibold text-[var(--re-text-primary)] mb-2">
                                Representativeness
                            </h3>
                            <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed mb-3">
                                Does your operation mirror our ideal customer? We prioritize partners whose size, food categories, and supply-chain complexity represent the broader market.
                            </p>
                            <div className="space-y-1.5">
                                <div className="flex items-start gap-2 text-[12px] text-[var(--re-text-secondary)]">
                                    <CheckCircle2 className="w-3.5 h-3.5 text-[var(--re-brand)] mt-0.5 shrink-0" />
                                    <span>FTL-covered products (leafy greens, seafood, dairy, etc.)</span>
                                </div>
                                <div className="flex items-start gap-2 text-[12px] text-[var(--re-text-secondary)]">
                                    <CheckCircle2 className="w-3.5 h-3.5 text-[var(--re-brand)] mt-0.5 shrink-0" />
                                    <span>Multi-supplier or multi-facility operations</span>
                                </div>
                                <div className="flex items-start gap-2 text-[12px] text-[var(--re-text-secondary)]">
                                    <CheckCircle2 className="w-3.5 h-3.5 text-[var(--re-brand)] mt-0.5 shrink-0" />
                                    <span>Retailer relationships requiring compliance proof</span>
                                </div>
                            </div>
                        </div>

                        {/* Urgency */}
                        <div className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6 shadow-sm">
                            <div className="w-10 h-10 rounded-xl bg-amber-500/10 flex items-center justify-center mb-4">
                                <Flame className="w-5 h-5 text-amber-500" />
                            </div>
                            <h3 className="text-[15px] font-semibold text-[var(--re-text-primary)] mb-2">
                                Urgency
                            </h3>
                            <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed mb-3">
                                Is FSMA 204 compliance a real, pressing problem {'\u2014'} not a someday-maybe? We want partners who feel the deadline pressure and have already tried solving it.
                            </p>
                            <div className="space-y-1.5">
                                <div className="flex items-start gap-2 text-[12px] text-[var(--re-text-secondary)]">
                                    <CheckCircle2 className="w-3.5 h-3.5 text-[var(--re-brand)] mt-0.5 shrink-0" />
                                    <span>Actively preparing for FSMA 204 or retailer audits</span>
                                </div>
                                <div className="flex items-start gap-2 text-[12px] text-[var(--re-text-secondary)]">
                                    <CheckCircle2 className="w-3.5 h-3.5 text-[var(--re-brand)] mt-0.5 shrink-0" />
                                    <span>Tried spreadsheets, manual logs, or other tools</span>
                                </div>
                                <div className="flex items-start gap-2 text-[12px] text-[var(--re-text-secondary)]">
                                    <CheckCircle2 className="w-3.5 h-3.5 text-[var(--re-brand)] mt-0.5 shrink-0" />
                                    <span>Budget or exec buy-in for compliance tooling</span>
                                </div>
                            </div>
                        </div>

                        {/* Capacity */}
                        <div className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6 shadow-sm">
                            <div className="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center mb-4">
                                <Wrench className="w-5 h-5 text-emerald-500" />
                            </div>
                            <h3 className="text-[15px] font-semibold text-[var(--re-text-primary)] mb-2">
                                Capacity
                            </h3>
                            <p className="text-[13px] text-[var(--re-text-muted)] leading-relaxed mb-3">
                                Can you actually implement and test? We need a named internal champion with time to provide feedback and access to systems for integration testing.
                            </p>
                            <div className="space-y-1.5">
                                <div className="flex items-start gap-2 text-[12px] text-[var(--re-text-secondary)]">
                                    <CheckCircle2 className="w-3.5 h-3.5 text-[var(--re-brand)] mt-0.5 shrink-0" />
                                    <span>Dedicated point person (2{'\u2013'}4 hours/week)</span>
                                </div>
                                <div className="flex items-start gap-2 text-[12px] text-[var(--re-text-secondary)]">
                                    <CheckCircle2 className="w-3.5 h-3.5 text-[var(--re-brand)] mt-0.5 shrink-0" />
                                    <span>Access to ERP, WMS, or data export for integration</span>
                                </div>
                                <div className="flex items-start gap-2 text-[12px] text-[var(--re-text-secondary)]">
                                    <CheckCircle2 className="w-3.5 h-3.5 text-[var(--re-brand)] mt-0.5 shrink-0" />
                                    <span>Willingness to test on mobile devices in the field</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Cohort Details Callout */}
                    <div className="mt-8 rounded-2xl border border-[var(--re-brand)]/20 bg-[var(--re-brand-muted)] p-5 sm:p-6 flex flex-col sm:flex-row items-start sm:items-center gap-4 sm:gap-6">
                        <div className="flex items-center gap-3 shrink-0">
                            <div className="w-10 h-10 rounded-xl bg-[var(--re-brand)] flex items-center justify-center">
                                <Users className="w-5 h-5 text-white" />
                            </div>
                            <div>
                                <div className="text-[15px] font-semibold text-[var(--re-text-primary)]">5{'\u2013'}10 partners per cohort</div>
                                <div className="text-[12px] text-[var(--re-text-muted)]">3{'\u2013'}6 month engagement</div>
                            </div>
                        </div>
                        <div className="text-[13px] text-[var(--re-text-secondary)] leading-relaxed">
                            Each cohort includes bi-weekly feedback calls, early access to new modules, and direct input on the product roadmap. We defer pricing conversations until month 3{'\u2013'}4 {'\u2014'} this is research first, sales second.
                        </div>
                    </div>
                </div>
            </section>

            {/* ═══ TIMELINE with styled nodes + connecting line ═══ */}
            <section className="relative z-[2] border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]">
                <div style={{ maxWidth: '600px', margin: '0 auto', padding: 'clamp(2.5rem, 6vw, 60px) clamp(1rem, 4vw, 24px)' }}>
                    <h2 className="text-2xl font-bold text-[var(--re-text-primary)] text-center mb-8">
                        Program timeline
                    </h2>
                    <div className="relative flex flex-col gap-4">
                        {/* Connecting line */}
                        <div className="absolute left-[19px] top-[28px] bottom-[28px] w-[2px] bg-gradient-to-b from-[var(--re-brand)] via-[var(--re-brand)]/40 to-red-400/40" />

                        {TIMELINE.map((t, i) => (
                            <div
                                key={i}
                                className="relative flex items-center gap-4 p-4 pl-12 rounded-xl border bg-[var(--re-surface-card)] shadow-sm transition-all"
                                style={{ borderColor: t.status === 'current' ? 'var(--re-brand)' : 'var(--re-surface-border)' }}
                            >
                                {/* Node */}
                                <div className="absolute left-3 top-1/2 -translate-y-1/2">
                                    <div className={`w-[14px] h-[14px] rounded-full border-[3px] ${
                                        t.status === 'current'
                                            ? 'bg-[var(--re-brand)] border-[var(--re-brand-muted)] shadow-[0_0_8px_var(--re-brand)]'
                                            : t.status === 'deadline'
                                                ? 'bg-red-500 border-red-200 dark:border-red-900'
                                                : 'bg-[var(--re-text-disabled)] border-[var(--re-surface-border)]'
                                    }`} />
                                </div>                                <div className="flex-grow">
                                    <div className="text-sm font-semibold text-[var(--re-text-primary)]">{t.phase}</div>
                                    <div className="text-xs text-[var(--re-text-muted)] mt-0.5">{t.detail}</div>
                                </div>
                                <span className={`text-xs font-bold shrink-0 ${
                                    t.status === 'current' ? 'text-[var(--re-brand)]'
                                        : t.status === 'deadline' ? 'text-red-500'
                                            : 'text-[var(--re-text-disabled)]'
                                }`}>
                                    {t.date}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            </section>
            {/* ═══ SIGNUP FORM with solid CTA ═══ */}
            <section id="apply" className="relative z-[2]" style={{ maxWidth: '480px', margin: '0 auto', padding: 'clamp(2.5rem, 6vw, 60px) clamp(1rem, 4vw, 24px) clamp(3rem, 8vw, 80px)' }}>
                <h2 className="text-xl sm:text-2xl font-bold text-[var(--re-text-primary)] text-center mb-2">
                    Apply to become a Founding Design Partner
                </h2>
                <p className="text-sm text-[var(--re-text-muted)] text-center mb-8">
                    We review applications within 48 hours. Founding partners get locked-in pricing, white-glove onboarding, and direct founder access.
                </p>
                <div className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6 shadow-sm">
                    <AlphaSignupForm />
                </div>
            </section>
        </div>
    );
}