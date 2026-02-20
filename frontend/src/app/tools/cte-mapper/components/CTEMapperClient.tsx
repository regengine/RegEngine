'use client';

import { FSMAToolShell } from '@/components/fsma/FSMAToolShell';
import { ToolConfig } from '@/types/fsma-tools';
import { Card, CardContent } from '@/components/ui/card';
import { motion } from 'framer-motion';
import { ArrowDown, Truck, Factory, Warehouse, ShoppingCart, Send, Info, ChevronRight } from 'lucide-react';
import { RelatedTools } from '@/components/layout/related-tools';
import { FREE_TOOLS } from '@/lib/fsma-tools-data';

const CTE_MAPPER_CONFIG: ToolConfig = {
    id: 'cte-mapper',
    title: 'CTE Coverage Mapper',
    description: 'Map your supply chain nodes to see who owes whom traceability data.',
    icon: 'Truck',
    stages: {
        questions: [
            {
                id: 'user_role',
                text: 'What is your role in this transaction?',
                type: 'select',
                options: [
                    { label: 'Farm (Primary Producer)', value: 'farm' },
                    { label: 'Packer / Initial Packer', value: 'packer' },
                    { label: 'Manufacturer / Processor', value: 'processor' },
                    { label: 'Distributor / Warehouse', value: 'distributor' },
                    { label: 'Retailer / Restaurant', value: 'retail' },
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
            title: 'Get the Full Data Exchange Protocol',
            description: 'We will send you a technical spec sheet of the exact API format or spreadsheet schema needed for this connection.',
            cta: 'Send My Protocol'
        }
    }
};

const RoleIcon = ({ role, className }: { role: string; className?: string }) => {
    switch (role) {
        case 'farm': return <Factory className={className} />;
        case 'packer': return <Warehouse className={className} />;
        case 'processor': return <Warehouse className={className} />;
        case 'distributor': return <Truck className={className} />;
        case 'retail': return <ShoppingCart className={className} />;
        case 'consumer': return <ShoppingCart className={className} />;
        default: return <Info className={className} />;
    }
};

export function CTEMapperClient() {
    const renderResults = (answers: Record<string, any>) => {
        const { user_role, source_role, destination_role } = answers;

        const getRoleName = (r: string) => {
            const opt = [...CTE_MAPPER_CONFIG.stages.questions[0].options!, ...CTE_MAPPER_CONFIG.stages.questions[1].options!, ...CTE_MAPPER_CONFIG.stages.questions[2].options!]
                .find(o => o.value === r);
            return opt?.label || r;
        };

        return (
            <div className="space-y-10">
                <h3 className="text-2xl font-bold text-center">Your Data Flow Map</h3>

                <div className="flex flex-col items-center gap-6 py-4">
                    {/* Source Node */}
                    {source_role !== 'none' && (
                        <>
                            <motion.div
                                initial={{ opacity: 0, y: -20 }}
                                animate={{ opacity: 1, y: 0 }}
                                className="flex flex-col items-center"
                            >
                                <div className="w-16 h-16 rounded-full bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] flex items-center justify-center text-[var(--re-text-tertiary)]">
                                    <RoleIcon role={source_role} className="h-8 w-8" />
                                </div>
                                <span className="text-xs mt-2 font-medium">{getRoleName(source_role)}</span>
                            </motion.div>
                            <motion.div
                                initial={{ height: 0 }}
                                animate={{ height: 40 }}
                                className="w-0.5 bg-gradient-to-b from-[var(--re-border-default)] to-[var(--re-brand)] relative"
                            >
                                <div className="absolute top-1/2 left-4 w-40 text-[10px] text-[var(--re-brand)] font-bold uppercase tracking-tighter">
                                    Must Send KDEs + TLC
                                </div>
                            </motion.div>
                        </>
                    )}

                    {/* User Node */}
                    <motion.div
                        initial={{ scale: 0.8 }}
                        animate={{ scale: 1 }}
                        className="flex flex-col items-center"
                    >
                        <div className="w-24 h-24 rounded-3xl bg-[var(--re-brand-muted)] border-2 border-[var(--re-brand)] flex flex-col items-center justify-center shadow-[0_0_20px_rgba(var(--re-brand-rgb),0.2)]">
                            <RoleIcon role={user_role} className="h-10 w-10 text-[var(--re-brand)] mb-1" />
                            <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--re-brand)]">YOU</span>
                        </div>
                        <span className="text-sm mt-3 font-bold">{getRoleName(user_role)}</span>
                    </motion.div>

                    {/* Destination Node */}
                    <motion.div
                        initial={{ height: 0 }}
                        animate={{ height: 40 }}
                        className="w-0.5 bg-gradient-to-b from-[var(--re-brand)] to-[var(--re-border-default)] relative"
                    >
                        <div className="absolute top-1/2 left-4 w-40 text-[10px] text-[var(--re-text-muted)] font-bold uppercase tracking-tighter">
                            YOU Provide KDEs
                        </div>
                    </motion.div>
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 20 }}
                        className="flex flex-col items-center"
                    >
                        <div className="w-16 h-16 rounded-full bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] flex items-center justify-center text-[var(--re-text-tertiary)]">
                            <RoleIcon role={destination_role} className="h-8 w-8" />
                        </div>
                        <span className="text-xs mt-2 font-medium">{getRoleName(destination_role)}</span>
                    </motion.div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <Card className="border-[var(--re-border-default)] bg-[var(--re-surface-elevated)]">
                        <CardContent className="p-4 space-y-2">
                            <h4 className="text-xs font-bold uppercase tracking-wider flex items-center gap-2">
                                <Send className="h-3 w-3 text-[var(--re-info)]" /> Incoming Obligations
                            </h4>
                            <p className="text-xs text-[var(--re-text-secondary)]">
                                You must verify that your {getRoleName(source_role)} sends the Traceability Lot Code (TLC) and source location for every delivery.
                            </p>
                        </CardContent>
                    </Card>
                    <Card className="border-[var(--re-border-default)] bg-[var(--re-surface-elevated)]">
                        <CardContent className="p-4 space-y-2">
                            <h4 className="text-xs font-bold uppercase tracking-wider flex items-center gap-2">
                                <Send className="h-3 w-3 text-[var(--re-brand)]" /> Outgoing Obligations
                            </h4>
                            <p className="text-xs text-[var(--re-text-secondary)]">
                                You are responsible for ensuring the {getRoleName(destination_role)} receives your ship-from KDEs and the original TLC.
                            </p>
                        </CardContent>
                    </Card>
                </div>

                <button className="w-full p-4 rounded-xl bg-[var(--re-brand)] text-white font-bold flex items-center justify-center gap-2 hover:brightness-110">
                    Share This Data Protocol <ChevronRight className="h-5 w-5" />
                </button>
            </div>
        );
    };

    return (
        <div className="min-h-screen py-20 px-4" style={{ background: 'var(--re-surface-base)' }}>
            <FSMAToolShell
                config={CTE_MAPPER_CONFIG}
                renderResults={renderResults}
            />

            <div className="max-w-3xl mx-auto">
                <RelatedTools
                    tools={FREE_TOOLS.filter(t => ['kde-checker', 'recall-readiness', 'drill-simulator'].includes(t.id))}
                />
            </div>
        </div>
    );
}
