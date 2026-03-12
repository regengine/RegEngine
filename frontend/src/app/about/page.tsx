import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
    title: 'About | RegEngine',
    description: 'Founder-led FSMA 204 compliance infrastructure with an explicit trust surface for customer diligence and implementation readiness.',
    openGraph: {
        title: 'About | RegEngine',
        description: 'Founder-led FSMA 204 compliance infrastructure with an explicit trust surface for customer diligence and implementation readiness.',
        url: 'https://www.regengine.co/about',
        type: 'website',
    },
};

const beliefs = [
    { title: "Compliance data should be verifiable, not trusted.", body: "Every record is SHA-256 hashed. Run our open verification script \u2014 if the hashes don\u2019t match, don\u2019t trust us." },
    { title: "Pricing should be public.", body: "We publish our prices. No \u2018contact sales\u2019 gates, no opaque enterprise contracts." },
    { title: "Regulations are public. Tooling should be accessible.", body: "The CFR is free. We charge for the infrastructure that makes it operationally useful." },
];

export default function AboutPage() {
    return (
        <div className="re-page">
            <section className="relative z-[2] max-w-[720px] mx-auto pt-20 px-6 pb-12">
                <span className="text-[11px] font-mono font-medium text-re-text-disabled tracking-widest uppercase">About</span>
                <h1 className="text-4xl font-bold text-[var(--re-text-primary)] mt-4 mb-5 leading-[1.15] tracking-tight">
                    Compliance infrastructure, built from the ground up
                </h1>
                <p className="text-base text-[var(--re-text-muted)] leading-[1.7]">
                    RegEngine turns FSMA 204 requirements into machine-readable, cryptographically verifiable records. The product is founder-led, FSMA-first, and explicit about where customer process, upstream data quality, and off-platform archives still matter.
                </p>
            </section>

            <section className="relative z-[2] border-t border-white/[0.06] bg-white/[0.02]">
                <div className="max-w-[720px] mx-auto py-12 px-6">
                    <div className="flex gap-6 items-start">
                        <div className="w-[72px] h-[72px] rounded-xl shrink-0 bg-[rgba(16,185,129,0.08)] border border-[rgba(16,185,129,0.2)] flex items-center justify-center text-[28px] font-bold text-[var(--re-brand)]">CS</div>
                        <div>
                            <h2 className="text-[22px] font-bold text-[var(--re-text-primary)] mb-1">Christopher Sellers</h2>
                            <p className="text-sm font-semibold text-[var(--re-brand)] mb-4">Founder &amp; CEO</p>
                            <div className="flex flex-col gap-3">
                                <div className="flex gap-2.5 items-baseline">
                                    <span className="text-xs font-mono font-medium text-[var(--re-text-disabled)] min-w-[20px]">01</span>
                                    <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">U.S. Senate &mdash; served as aide to Senator Jeff Merkley, supporting 150+ constituent engagements statewide.</p>
                                </div>
                                <div className="flex gap-2.5 items-baseline">
                                    <span className="text-xs font-mono font-medium text-[var(--re-text-disabled)] min-w-[20px]">02</span>
                                    <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">AmeriCorps NCCC &mdash; Team Leader during Hurricane Katrina disaster response. President&apos;s Volunteer Service Award.</p>
                                </div>
                                <div className="flex gap-2.5 items-baseline">
                                    <span className="text-xs font-mono font-medium text-[var(--re-text-disabled)] min-w-[20px]">03</span>
                                    <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">Built every layer of RegEngine &mdash; architecture, backend, frontend, compliance logic, and cryptographic verification. Founder-led product with a public trust center rather than enterprise theater.</p>
                                </div>
                            </div>
                            <a href="https://www.linkedin.com/in/clsellers/" target="_blank" rel="noopener noreferrer" className="inline-block text-[13px] text-[var(--re-brand)] font-medium mt-4 hover:underline">LinkedIn &rarr;</a>
                        </div>
                    </div>
                </div>
            </section>

            <section className="relative z-[2] border-t border-white/[0.06]">
                <div className="max-w-[720px] mx-auto py-12 px-6">
                    <h2 className="text-2xl font-bold text-[var(--re-text-primary)] mb-6">What we believe</h2>
                    <div className="flex flex-col gap-4">
                        {beliefs.map((b, i) => (
                            <div key={i} className="p-4 px-5 bg-white/[0.02] rounded-lg border border-white/[0.06]">
                                <h3 className="text-[15px] font-semibold text-[var(--re-text-primary)] mb-1">{b.title}</h3>
                                <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">{b.body}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            <section className="relative z-[2] border-t border-white/[0.06] max-w-[720px] mx-auto py-12 px-6 text-center">
                <h2 className="text-[22px] font-bold text-[var(--re-text-primary)] mb-2">Talk to the founder directly</h2>
                <p className="text-[15px] text-[var(--re-text-muted)] mb-6">chris@regengine.co &mdash; no sales team, no gatekeepers, and the trust center documents the current status model versus guided rollout.</p>
                <div className="flex gap-3 justify-center flex-wrap">
                    <Link href="/trust" className="inline-flex items-center gap-2 px-7 py-3.5 bg-[var(--re-brand)] text-[var(--re-surface-base)] rounded-lg text-[15px] font-semibold hover:opacity-90 transition-opacity">Review Trust Center &rarr;</Link>
                    <Link href="/pricing" className="inline-flex items-center gap-2 px-7 py-3.5 bg-transparent text-[var(--re-text-primary)] rounded-lg text-[15px] font-semibold border border-white/[0.06] hover:border-white/[0.12] transition-colors">View Pricing</Link>
                </div>
            </section>
        </div>
    );
}
