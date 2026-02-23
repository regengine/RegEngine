'use client';

import React from 'react';
import { motion } from 'framer-motion';
import {
    Hash,
    ShieldCheck,
    Network,
    Globe
} from 'lucide-react';

const STAGES = [
    {
        id: 'discovery',
        title: 'Ingestion & Discovery',
        description: 'Real-time multi-source monitoring of the regulatory landscape.',
        icon: Globe,
        color: 'text-[var(--re-discovery)]',
        bg: 'bg-[var(--re-discovery)]/10',
        border: 'border-[var(--re-discovery)]/20',
        details: [
            'Direct fetches from FDA, eCFR, EUR-Lex',
            'Multi-format parsing (PDF, DOCX, HTML)',
            'Change detection with version diffing'
        ]
    },
    {
        id: 'decomposition',
        title: 'Deterministic Decomposition',
        description: 'NLP-driven breakdown into structured, immutable compliance atoms.',
        icon: Hash,
        color: 'text-[var(--re-brand)]',
        bg: 'bg-[var(--re-brand)]/10',
        border: 'border-[var(--re-brand)]/20',
        details: [
            'Obligation extraction (Must/Should)',
            'Deterministic SHA-256 fact hashing',
            'Linked citation mapping'
        ]
    },
    {
        id: 'linkage',
        title: 'Relational Graph Linkage',
        description: 'Architecting the network of regulations, entities, and products.',
        icon: Network,
        color: 'text-[var(--re-linkage)]',
        bg: 'bg-[var(--re-linkage)]/10',
        border: 'border-[var(--re-linkage)]/20',
        details: [
            'Entity-to-Obligation mapping',
            'Cross-regulation dependency analysis',
            'Automated product scoping'
        ]
    },
    {
        id: 'evidence',
        title: 'Verifiable Evidence',
        description: 'Audit-ready outputs with cryptographic chain of custody.',
        icon: ShieldCheck,
        color: 'text-[var(--re-evidence)]',
        bg: 'bg-[var(--re-evidence)]/10',
        border: 'border-[var(--re-evidence)]/20',
        details: [
            'Immutable audit trail generation',
            '24-hour recall ready reports',
            'Third-party verification scripts'
        ]
    }
];

export function BlueprintFlow() {
    return (
        <div className="w-full space-y-24">
            {STAGES.map((stage, index) => (
                <motion.div
                    key={stage.id}
                    initial={{ opacity: 0, y: 40 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: '-100px' }}
                    transition={{ duration: 0.8, delay: index * 0.1 }}
                    className="relative"
                >
                    {/* Visual Connector Line */}
                    {index < STAGES.length - 1 && (
                        <div className="absolute left-10 md:left-1/2 top-20 bottom-[-60px] re-journey-line hidden md:block" />
                    )}

                    <div className={`grid grid-cols-1 md:grid-cols-2 gap-12 items-center ${index % 2 === 1 ? 'md:flex-row-reverse' : ''}`}>
                        {/* Content Side */}
                        <div className={`space-y-6 ${index % 2 === 1 ? 'md:order-2 md:pl-12' : 'md:pr-12'}`}>
                            <div className="flex items-center gap-4">
                                <div className={`h-20 w-20 rounded-[2.5rem] ${stage.bg} ${stage.border} border flex items-center justify-center shadow-xl`}>
                                    <stage.icon className={`h-10 w-10 ${stage.color}`} />
                                </div>
                                <div className="space-y-1">
                                    <span className="text-[var(--re-brand)] font-black text-xs tracking-widest uppercase">Stage 0{index + 1}</span>
                                    <h3 className="text-3xl re-heading-industrial text-[var(--re-text-primary)]">
                                        {stage.title}
                                    </h3>
                                </div>
                            </div>

                            <p className="text-xl text-[var(--re-text-secondary)] font-medium leading-relaxed">
                                {stage.description}
                            </p>

                            <ul className="space-y-4 pt-4">
                                {stage.details.map((detail, i) => (
                                    <motion.li
                                        key={i}
                                        initial={{ opacity: 0, x: -10 }}
                                        whileInView={{ opacity: 1, x: 0 }}
                                        transition={{ delay: 0.5 + i * 0.1 }}
                                        className="flex items-center gap-3 text-[var(--re-text-tertiary)] font-bold italic uppercase text-xs"
                                    >
                                        <div className="re-dot bg-[var(--re-brand)]" />
                                        {detail}
                                    </motion.li>
                                ))}
                            </ul>
                        </div>

                        {/* Interactive/Visual Side */}
                        <div className={`relative ${index % 2 === 1 ? 'md:order-1' : ''}`}>
                            <div className="re-card-lp !p-8 aspect-[16/10] overflow-hidden group">
                                <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />

                                {/* Stage-specific Visualization Mockup */}
                                <div className="h-full w-full flex flex-col justify-center items-center gap-6">
                                    {index === 0 && <StageDiscoveryVisual />}
                                    {index === 1 && <StageDecompositionVisual />}
                                    {index === 2 && <StageLinkageVisual />}
                                    {index === 3 && <StageEvidenceVisual />}
                                </div>

                                {/* Premium Glow */}
                                <div className={`absolute -bottom-20 -right-20 h-64 w-64 blur-[100px] opacity-20 pointer-events-none rounded-full ${stage.bg}`} />
                            </div>
                        </div>
                    </div>
                </motion.div>
            ))}
        </div>
    );
}

/* ─── SUB-VISUALS ─── */

function StageDiscoveryVisual() {
    return (
        <div className="w-full space-y-4">
            {[1, 2, 3].map(i => (
                <div key={i} className="h-12 w-full bg-white/5 rounded-xl border border-white/10 flex items-center gap-4 px-4 overflow-hidden relative">
                    <div className="h-2 w-2 rounded-full bg-[var(--re-discovery)] animate-pulse" />
                    <div className="h-2 w-3/4 bg-white/10 rounded" />
                    <div className="ml-auto flex gap-2">
                        <div className="h-4 w-4 rounded bg-white/10" />
                        <div className="h-4 w-4 rounded bg-white/10" />
                    </div>
                </div>
            ))}
            <div className="text-center pt-2">
                <span className="text-[10px] font-black text-[var(--re-discovery)] uppercase tracking-widest animate-pulse">Scanning Global Repositories...</span>
            </div>
        </div>
    );
}

function StageDecompositionVisual() {
    return (
        <div className="grid grid-cols-4 gap-4 w-full">
            {Array.from({ length: 8 }).map((_, i) => (
                <motion.div
                    key={i}
                    animate={{
                        scale: [1, 1.1, 1],
                        opacity: [0.3, 0.6, 0.3]
                    }}
                    transition={{
                        duration: 3,
                        repeat: Infinity,
                        delay: i * 0.2
                    }}
                    className="aspect-square bg-[var(--re-brand-muted)] border border-[var(--re-brand-muted)] rounded-2xl flex items-center justify-center shadow-lg"
                >
                    <Hash className="h-4 w-4 text-[var(--re-brand)]" />
                </motion.div>
            ))}
            <div className="col-span-4 text-center mt-4">
                <code className="text-[10px] text-[var(--re-brand)] re-mono opacity-60">SHA-256 Verified Atomicity</code>
            </div>
        </div>
    );
}

function StageLinkageVisual() {
    return (
        <div className="relative h-48 w-full">
            <Network className="absolute inset-0 m-auto h-24 w-24 text-[var(--re-linkage)] opacity-40" />
            <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 20, repeat: Infinity, ease: 'linear' }}
                className="absolute inset-0 m-auto h-40 w-40 border border-dashed border-[var(--re-linkage)] opacity-20 rounded-full"
            />
            {[0, 90, 180, 270].map(deg => (
                <motion.div
                    key={deg}
                    style={{
                        position: 'absolute',
                        top: '50%',
                        left: '50%',
                        transform: `rotate(${deg}deg) translate(80px)`
                    }}
                    className="h-4 w-4 bg-[var(--re-linkage)] rounded-full shadow-[0_0_15px_rgba(168,85,247,0.5)]"
                />
            ))}
        </div>
    );
}

function StageEvidenceVisual() {
    return (
        <div className="w-full flex flex-col items-center gap-6">
            <div className="relative">
                <ShieldCheck className="h-24 w-24 text-[var(--re-evidence)] drop-shadow-[0_0_20px_rgba(245,158,11,0.4)]" />
                <motion.div
                    animate={{ scale: [1, 1.5], opacity: [0.5, 0] }}
                    transition={{ duration: 2, repeat: Infinity }}
                    className="absolute inset-0 border-4 border-[var(--re-evidence)] rounded-full"
                />
            </div>
            <div className="flex gap-2">
                <div className="h-6 w-20 bg-[var(--re-evidence)]/20 border border-[var(--re-evidence)]/30 rounded flex items-center justify-center">
                    <span className="text-[8px] font-black text-[var(--re-evidence)] uppercase italic">PDF EXPORT</span>
                </div>
                <div className="h-6 w-20 bg-[var(--re-evidence)]/20 border border-[var(--re-evidence)]/30 rounded flex items-center justify-center">
                    <span className="text-[8px] font-black text-[var(--re-evidence)] uppercase italic">SHA-256 SIGN</span>
                </div>
            </div>
        </div>
    );
}
