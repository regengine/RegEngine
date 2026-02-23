'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { BlueprintFlow } from '@/components/blueprint/BlueprintFlow';
import { Button } from '@/components/ui/button';
import { Activity, ArrowRight, Zap, ShieldCheck } from 'lucide-react';
import Link from 'next/link';

export default function BlueprintPage() {
    return (
        <div className="re-page relative overflow-hidden">
            {/* Background Texture/Grid */}
            <div className="re-noise" />
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(16,185,129,0.05),transparent_70%)] pointer-events-none" />

            {/* Hero Section */}
            <header className="relative pt-32 pb-24 px-4 border-b border-[var(--re-surface-border)] bg-gradient-to-b from-white/10 to-transparent dark:from-gray-900/40">
                <div className="max-w-5xl mx-auto text-center space-y-8">
                    <motion.div
                        initial={{ opacity: 0, y: -20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.6 }}
                        className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-[var(--re-brand-muted)] text-[var(--re-brand)] text-[11px] font-black uppercase tracking-[0.2em] border border-[var(--re-brand-muted)]"
                    >
                        <Zap className="h-3 w-3" /> System Architecture V1.0
                    </motion.div>

                    <motion.h1
                        initial={{ opacity: 0, scale: 0.95 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ duration: 0.8 }}
                        className="text-6xl md:text-8xl re-heading-industrial"
                    >
                        The Regulatory <br />
                        <span className="bg-gradient-to-r from-[var(--re-brand)] to-emerald-400 bg-clip-text text-transparent">Proof Chain</span>
                    </motion.h1>

                    <motion.p
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.4 }}
                        className="text-2xl text-[var(--re-text-secondary)] font-bold max-w-3xl mx-auto tracking-tight"
                    >
                        We turned regulatory compliance into a deterministic engineering problem.
                        No more guesswork. No more "Manual Interpretation."
                        Just cryptographic certainty.
                    </motion.p>

                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.6 }}
                        className="flex flex-wrap justify-center gap-4"
                    >
                        <Link href="/ftl-checker">
                            <Button size="lg" className="h-16 px-10 rounded-3xl bg-[var(--re-brand)] text-white text-lg font-black italic uppercase shadow-[0_20px_40px_-10px_rgba(16,185,129,0.4)] group">
                                Start Journey <ArrowRight className="ml-2 h-5 w-5 group-hover:translate-x-1 transition-transform" />
                            </Button>
                        </Link>
                        <Button size="lg" variant="outline" className="h-16 px-10 rounded-3xl text-lg font-black italic uppercase border-2 group">
                            Read the Whitepaper
                        </Button>
                    </motion.div>
                </div>
            </header>

            {/* Interactive Flow */}
            <main className="max-w-7xl mx-auto px-4 py-32 space-y-40">
                <section>
                    <div className="flex flex-col items-center text-center mb-24 space-y-4">
                        <div className="h-1 bg-[var(--re-brand)] w-24 rounded-full" />
                        <h2 className="text-4xl re-heading-industrial">The Pipeline architecture</h2>
                        <p className="max-w-2xl text-[var(--re-text-tertiary)] font-bold uppercase text-sm tracking-[0.2em]">
                            From messy federal register entries to clean, auditable knowledge nodes.
                        </p>
                    </div>

                    <BlueprintFlow />
                </section>

                {/* Final Call to Action */}
                <section className="re-card-lp text-center space-y-12">
                    <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(16,185,129,0.1),transparent_50%)]" />
                    <div className="relative z-10 space-y-8 px-8">
                        <div className="h-20 w-20 rounded-3xl bg-white/10 flex items-center justify-center mx-auto backdrop-blur-xl border border-white/10">
                            <ShieldCheck className="h-10 w-10 text-[var(--re-brand)]" />
                        </div>
                        <h2 className="text-4xl md:text-6xl re-heading-industrial text-white lowercase">
                            Build Your Compliance <br />
                            Foundation on <span className="text-[var(--re-brand)] underline decoration-wavy decoration-emerald-800">Immutable Proof</span>.
                        </h2>
                        <p className="text-[var(--re-text-tertiary)] text-xl font-bold max-w-2xl mx-auto italic">
                            The era of "Checking the Box" is over. Start building your Regulatory Proof Chain today.
                        </p>
                        <Link href="/onboarding">
                            <Button size="lg" className="h-20 px-12 rounded-[2.5rem] bg-white text-black text-2xl font-black italic uppercase hover:scale-105 transition-transform">
                                Apply for Early Access →
                            </Button>
                        </Link>
                    </div>
                </section>
            </main>

            {/* Footer Tag */}
            <footer className="py-20 text-center border-t border-[var(--re-surface-border)]">
                <div className="flex items-center justify-center gap-2 text-[var(--re-text-disabled)] font-black text-[10px] uppercase tracking-[0.4em]">
                    <Activity className="h-3 w-3" /> RegEngine Core System Architecture v1.0.4
                </div>
            </footer>
        </div>
    );
}
