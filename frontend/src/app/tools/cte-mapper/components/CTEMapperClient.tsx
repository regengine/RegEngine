'use client';

import { FSMAToolShell } from '@/components/fsma/FSMAToolShell';
import { ToolConfig } from '@/types/fsma-tools';
import { usePostHog } from '@/lib/posthog-provider';
import { Card, CardContent } from '@/components/ui/card';
import { motion } from 'framer-motion';
import { Truck, Factory, Warehouse, ShoppingCart, Send, Info } from 'lucide-react';
import { RelatedTools } from '@/components/layout/related-tools';
import { FREE_TOOLS } from '@/lib/fsma-tools-data';

const CTE_MAPPER_CONFIG: ToolConfig = {
    id: 'cte-mapper',
    title: 'CTE Mapper',
    description: 'Map your supply chain links to see which Critical Tracking Events typically apply at each step under 21 CFR Part 1 Subpart S. Educational only — exemptions under §1.1305 may change which CTEs apply to your specific operation.',
    icon: 'Truck',
    stages: {
        questions: [
            {
                id: 'user_role',
                text: 'What is your role in this transaction?',
                type: 'select',
                options: [
                    { label: 'Farm / Grower (harvesting, cooling)', value: 'farm' },
                    { label: 'Initial Packer (RAC, not from a fishing vessel)', value: 'packer' },
                    { label: 'First Land-Based Receiver (seafood from a fishing vessel)', value: 'flbr' },
                    { label: 'Manufacturer / Processor (transformation)', value: 'processor' },
                    { label: 'Distributor / Warehouse', value: 'distributor' },
                    { label: 'Retailer (RFE)', value: 'retail' },
                    { label: 'Restaurant / direct-to-consumer (subject to §1.1305(j) exemption)', value: 'restaurant' },
                ]
            },
            {
                id: 'source_role',
                text: 'Who do you receive this food from?',
                type: 'select',
                options: [
                    { label: 'Direct from Farm', value: 'farm' },
                    { label: 'From a Packer', value: 'packer' },
                    { label: 'From a Processor', value: 'processor' },
                    { label: 'From a Distributor', value: 'distributor' },
                    { label: 'From a Fishing Vessel (we are the FLBR)', value: 'fishing_vessel' },
                    { label: 'N/A (We are the source)', value: 'none' },
                ]
            },
            {
                id: 'destination_role',
                text: 'Who do you ship this food to?',
                type: 'select',
                options: [
                    { label: 'To a Processor', value: 'processor' },
                    { label: 'To a Distributor', value: 'distributor' },
                    { label: 'To a Retailer / Restaurant', value: 'retail' },
                    { label: 'Direct to Consumer', value: 'consumer' },
                ]
            }
        ],
        leadGate: {
            title: 'Get the Full Data Exchange Reference',
            description: 'We will send you a starter API and CSV spec for the connections you indicated. This is a starting reference; verify against the rule for your specific operation.',
            cta: 'Send My Reference'
        }
    }
};

const RoleIcon = ({ role, className }: { role: string; className?: string }) => {
    switch (role) {
        case 'farm': return <Factory className={className} />;
        case 'packer': return <Warehouse className={className} />;
        case 'flbr': return <Warehouse className={className} />;
        case 'fishing_vessel': return <Send className={className} />;
        case 'processor': return <Warehouse className={className} />;
        case 'distributor': return <Truck className={className} />;
        case 'retail': return <ShoppingCart className={className} />;
        case 'restaurant': return <ShoppingCart className={className} />;
        case 'consumer': return <ShoppingCart className={className} />;
        default: return <Info className={className} />;
    }
};

// CTE assignment by role under 21 CFR Part 1 Subpart S. This is a starting
// reference; §1.1305 exemptions may remove a CTE for a given operation.
const ROLE_TO_CTES: Record<string, { ctes: string[]; note: string }> = {
    farm: {
        ctes: ['§1.1325 Harvesting and Cooling'],
        note: 'Field-level harvesting and on-farm cooling records. If you also pack on-farm, see §1.1330 Initial Packing.',
    },
    packer: {
        ctes: ['§1.1330 Initial Packing of a RAC (other than from a fishing vessel)', '§1.1340 Shipping'],
        note: 'Initial Packing applies to raw agricultural commodities not obtained from a fishing vessel. Seafood from a vessel uses §1.1335 First Land-Based Receiving instead.',
    },
    flbr: {
        ctes: ['§1.1335 First Land-Based Receiving (seafood from a fishing vessel)', '§1.1340 Shipping'],
        note: 'FLBR applies only to food obtained from a fishing vessel. Non-seafood importers use §1.1345 Receiving, not FLBR.',
    },
    processor: {
        ctes: ['§1.1345 Receiving', '§1.1350 Transformation', '§1.1340 Shipping'],
        note: 'Transformation links input TLCs to a new TLC for the output product.',
    },
    distributor: {
        ctes: ['§1.1345 Receiving', '§1.1340 Shipping'],
        note: 'Receiving and Shipping records track lot movement through your facility.',
    },
    retail: {
        ctes: ['§1.1345 Receiving (subject to the §1.1305(j) exemption)'],
        note: 'Retail food establishments selling FTL food directly to consumers may qualify for the §1.1305(j) exemption. Confirm whether the exemption applies before relying on this.',
    },
    restaurant: {
        ctes: ['§1.1345 Receiving (likely exempt under §1.1305(j))'],
        note: '§1.1305(j) exempts restaurants and retail food establishments from the records requirement for food sold or distributed directly to consumers. Verify scope with counsel — you may still owe §1.1345 records for FTL food received but not sold direct.',
    },
};

export function CTEMapperClient() {
    const posthog = usePostHog();

    const renderResults = (answers: Record<string, any>) => {
        const { user_role, source_role, destination_role } = answers;

        const getRoleName = (r: string) => {
            const opt = [...CTE_MAPPER_CONFIG.stages.questions[0].options!, ...CTE_MAPPER_CONFIG.stages.questions[1].options!, ...CTE_MAPPER_CONFIG.stages.questions[2].options!]
                .find(o => o.value === r);
            return opt?.label || r;
        };

        return (
            <div className="space-y-10">
                <h3 className="text-center text-heading text-re-text-primary">Your Data Flow Map</h3>

                <div className="flex flex-col items-center gap-6 py-4">
                    {/* Source Node */}
                    {source_role !== 'none' && (
                        <>
                            <motion.div
                                initial={{ opacity: 0, y: -20 }}
                                animate={{ opacity: 1, y: 0 }}
                                className="flex flex-col items-center"
                            >
                                <div className="flex h-16 w-16 items-center justify-center rounded-full border border-re-border bg-re-surface-inset text-re-text-tertiary">
                                    <RoleIcon role={source_role} className="h-8 w-8" />
                                </div>
                                <span className="mt-2 max-w-[18ch] text-center text-small font-medium text-re-text-secondary">{getRoleName(source_role)}</span>
                            </motion.div>
                            <motion.div
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                className="flex items-center gap-3"
                            >
                                <span className="block h-10 w-px bg-re-border-strong" aria-hidden="true" />
                                <span className="font-mono uppercase text-label text-re-text-muted">
                                    Must Send KDEs + TLC
                                </span>
                            </motion.div>
                        </>
                    )}

                    {/* User Node */}
                    <motion.div
                        initial={{ scale: 0.8 }}
                        animate={{ scale: 1 }}
                        className="flex flex-col items-center"
                    >
                        <div className="flex h-24 w-24 flex-col items-center justify-center rounded-lg border border-re-border-strong bg-re-surface-inset">
                            <RoleIcon role={user_role} className="mb-1 h-10 w-10 text-re-text-primary" />
                            <span className="font-mono uppercase text-label text-re-text-secondary">YOU</span>
                        </div>
                        <span className="mt-3 max-w-[22ch] text-center text-ui font-medium text-re-text-primary">{getRoleName(user_role)}</span>
                    </motion.div>

                    {/* Destination Node */}
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="flex items-center gap-3"
                    >
                        <span className="block h-10 w-px bg-re-border-strong" aria-hidden="true" />
                        <span className="font-mono uppercase text-label text-re-text-muted">
                            YOU Provide KDEs
                        </span>
                    </motion.div>
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="flex flex-col items-center"
                    >
                        <div className="flex h-16 w-16 items-center justify-center rounded-full border border-re-border bg-re-surface-inset text-re-text-tertiary">
                            <RoleIcon role={destination_role} className="h-8 w-8" />
                        </div>
                        <span className="mt-2 max-w-[18ch] text-center text-small font-medium text-re-text-secondary">{getRoleName(destination_role)}</span>
                    </motion.div>
                </div>

                <Card>
                    <CardContent className="space-y-3 p-4">
                        <h4 className="flex items-center gap-2 font-mono uppercase text-label text-re-text-muted">
                            <Truck className="h-3.5 w-3.5 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" /> CTEs typically assigned to your role
                        </h4>
                        {ROLE_TO_CTES[user_role] ? (
                            <>
                                <ul className="list-inside list-disc space-y-1 text-ui text-re-text-secondary">
                                    {ROLE_TO_CTES[user_role].ctes.map((c) => <li key={c}>{c}</li>)}
                                </ul>
                                <p className="mt-2 text-small text-re-text-tertiary">{ROLE_TO_CTES[user_role].note}</p>
                            </>
                        ) : (
                            <p className="text-small text-re-text-tertiary">CTE assignment depends on your operation. See the per-event KDE Field Checklist.</p>
                        )}
                    </CardContent>
                </Card>

                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <Card>
                        <CardContent className="space-y-2 p-4">
                            <h4 className="flex items-center gap-2 font-mono uppercase text-label text-re-text-muted">
                                <Send className="h-3.5 w-3.5 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" /> Incoming exchange (informational)
                            </h4>
                            <p className="text-small text-re-text-secondary">
                                If this food is on the FDA Food Traceability List and no §1.1305 exemption applies, your {getRoleName(source_role)} is generally required to send the Traceability Lot Code and ship-from KDEs under 21 CFR §1.1340. This tool does not determine FTL status or exemptions — use the FTL Checker first.
                            </p>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="space-y-2 p-4">
                            <h4 className="flex items-center gap-2 font-mono uppercase text-label text-re-text-muted">
                                <Send className="h-3.5 w-3.5 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" /> Outgoing exchange (informational)
                            </h4>
                            <p className="text-small text-re-text-secondary">
                                If this food is on the FDA Food Traceability List and no §1.1305 exemption applies, you generally provide ship-from KDEs and the TLC to the {getRoleName(destination_role)} under §1.1340. Confirm with counsel before relying on this.
                            </p>
                        </CardContent>
                    </Card>
                </div>

                <p className="mx-auto max-w-[70ch] text-center text-small text-re-text-muted">
                    This map is a starting reference under 21 CFR Part 1 Subpart S. It does not evaluate FTL coverage, partial exemptions, or your specific operation. Verify against the rule and consult counsel before relying on it.
                </p>
            </div>
        );
    };

    return (
        <div className="space-y-8">
            <FSMAToolShell
                config={CTE_MAPPER_CONFIG}
                renderResults={renderResults}
                onLeadCapture={() => {
                    posthog?.capture('cte_mapped', {
                        tool_id: CTE_MAPPER_CONFIG.id,
                        lead_captured: true
                    });
                }}
            />

            <div className="mx-auto max-w-3xl">
                <RelatedTools
                    tools={FREE_TOOLS.filter(t => ['kde-checker', 'recall-readiness', 'drill-simulator'].includes(t.id))}
                />
            </div>
        </div>
    );
}
