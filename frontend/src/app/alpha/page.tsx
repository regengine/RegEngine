import type { Metadata } from 'next';
import Link from 'next/link';
import {
    Shield, Zap, Users, Star, TrendingUp, FileCheck, Clock,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import AlphaSignupForm from './AlphaSignupForm';

export const metadata: Metadata = {
    title: 'Design Partner Program | RegEngine Private Alpha',
    description: "Join RegEngine's private alpha. 25 spots for design partners shaping food traceability compliance.",
    openGraph: {
        title: 'Design Partner Program | RegEngine Private Alpha',
        description: "Join RegEngine's private alpha. 25 spots for design partners shaping food traceability compliance.",
        url: 'https://www.regengine.co/alpha',
        type: 'website',
    },
};

const T = {
    bg: 'var(--re-surface-base)',
    surface: 'rgba(255,255,255,0.02)',
    border: 'rgba(255,255,255,0.06)',
    text: 'var(--re-text-secondary)',
    textMuted: 'var(--re-text-muted)',
    textDim: 'var(--re-text-disabled)',
    heading: 'var(--re-text-primary)',
    accent: 'var(--re-brand)',
    accentBg: 'rgba(16,185,129,0.1)',
};

const ALPHA_PERKS = [
    { Icon: Zap, title: 'Priority API Access', description: "Be the first to integrate with RegEngine's traceability API and shape the developer experience." },
    { Icon: TrendingUp, title: 'Locked-In Pricing', description: 'Alpha partners lock in founding-member pricing for the duration of their account.' },
    { Icon: Users, title: 'Direct Founder Access', description: 'Weekly office hours with the founding team. Your feedback helps inform product direction.' },
    { Icon: FileCheck, title: 'White-Glove Onboarding', description: 'Dedicated onboarding support to map your supply chain and configure your compliance profile.' },
    { Icon: Shield, title: 'Compliance Head Start', description: 'Get FSMA 204 compliant before the July 2028 deadline while your competitors scramble.' },
    { Icon: Star, title: 'Case Study Feature', description: "Be featured as a launch partner case study \u2014 great for your brand and compliance credibility." },
];

const TIMELINE = [
    { phase: 'Private Alpha', status: 'current', date: 'Current', detail: 'Invite-only \u00b7 25 companies' },
    { phase: 'Design Partner Cohort', status: 'upcoming', date: 'Rolling', detail: 'Application review \u00b7 Guided onboarding' },
    { phase: 'FSMA 204 Deadline', status: 'deadline', date: 'Jul 2028', detail: 'FDA enforcement begins' },
];

export default function AlphaPage() {
    return (
        <div className="re-page" style={{ minHeight: '100vh', background: T.bg, color: T.text }}>
            {/* Hero */}
            <section style={{ position: 'relative', zIndex: 2, maxWidth: '800px', margin: '0 auto', padding: '80px 24px 60px', textAlign: 'center' }}>
                <Badge style={{ background: 'rgba(139,92,246,0.1)', color: '#8b5cf6', border: '1px solid rgba(139,92,246,0.2)', marginBottom: '20px' }}>
                    Private Alpha &middot; 25 Spots
                </Badge>
                <h1 style={{ fontSize: 'clamp(32px, 5vw, 48px)', fontWeight: 700, color: T.heading, lineHeight: 1.1, margin: '0 0 16px' }}>
                    Shape the future of<br />
                    <span className="text-re-brand">food traceability</span>
                </h1>
                <p style={{ fontSize: '18px', color: T.textMuted, maxWidth: '560px', margin: '0 auto 16px', lineHeight: 1.6 }}>
                    Join 25 food companies building FSMA 204 compliance infrastructure alongside our engineering team.
                    Founding-member pricing. Direct founder access. White-glove onboarding.
                </p>
            </section>

            {/* Perks Grid */}
            <section style={{ position: 'relative', zIndex: 2, maxWidth: '900px', margin: '0 auto', padding: '0 24px 60px' }}>
                <h2 style={{ fontSize: '24px', fontWeight: 700, color: T.heading, textAlign: 'center', marginBottom: '32px' }}>
                    What design partners get
                </h2>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '16px' }}>
                    {ALPHA_PERKS.map((perk) => (
                        <div key={perk.title} style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: '12px', padding: '24px' }}>
                            <perk.Icon style={{ width: 20, height: 20, color: T.accent, marginBottom: '12px' }} />
                            <h3 style={{ fontSize: '15px', fontWeight: 600, color: T.heading, marginBottom: '6px' }}>{perk.title}</h3>
                            <p style={{ fontSize: '13px', color: T.textMuted, lineHeight: 1.5 }}>{perk.description}</p>
                        </div>
                    ))}
                </div>
            </section>

            {/* Timeline */}
            <section style={{ position: 'relative', zIndex: 2, borderTop: `1px solid ${T.border}`, background: 'rgba(255,255,255,0.01)' }}>
                <div style={{ maxWidth: '600px', margin: '0 auto', padding: '60px 24px' }}>
                    <h2 style={{ fontSize: '24px', fontWeight: 700, color: T.heading, textAlign: 'center', marginBottom: '32px' }}>
                        Program timeline
                    </h2>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        {TIMELINE.map((t, i) => (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '16px 20px', background: T.surface, border: `1px solid ${t.status === 'current' ? 'rgba(16,185,129,0.3)' : T.border}`, borderRadius: '10px' }}>
                                <div style={{
                                    width: '10px', height: '10px', borderRadius: '50%', flexShrink: 0,
                                    background: t.status === 'current' ? T.accent : t.status === 'deadline' ? '#ef4444' : T.textDim,
                                }} />
                                <div style={{ flex: 1 }}>
                                    <div style={{ fontSize: '14px', fontWeight: 600, color: T.heading }}>{t.phase}</div>
                                    <div style={{ fontSize: '12px', color: T.textMuted }}>{t.detail}</div>
                                </div>
                                <span style={{ fontSize: '12px', fontWeight: 600, color: t.status === 'current' ? T.accent : T.textDim }}>
                                    {t.date}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Signup Form */}
            <section style={{ position: 'relative', zIndex: 2, maxWidth: '480px', margin: '0 auto', padding: '60px 24px 80px' }}>
                <h2 style={{ fontSize: '24px', fontWeight: 700, color: T.heading, textAlign: 'center', marginBottom: '8px' }}>
                    Apply for design partner access
                </h2>
                <p style={{ fontSize: '14px', color: T.textMuted, textAlign: 'center', marginBottom: '32px' }}>
                    We review applications within 48 hours. No credit card required.
                </p>
                <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: '12px', padding: '24px' }}>
                    <AlphaSignupForm />
                </div>
            </section>
        </div>
    );
}
