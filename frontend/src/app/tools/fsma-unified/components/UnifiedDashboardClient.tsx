'use client';

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, Network } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import dynamic from "next/dynamic";
import { AnomalyDetectionSimulator } from "./AnomalySimulator";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { RelatedTools } from "@/components/layout/related-tools";
import { FREE_TOOLS } from "@/lib/fsma-tools-data";

const SupplyChainKnowledgeGraphBuilder = dynamic(
    () => import("./KnowledgeGraph").then(mod => mod.SupplyChainKnowledgeGraphBuilder),
    { ssr: false }
);

export function UnifiedDashboardClient() {
    const searchParams = useSearchParams();
    const tab = searchParams.get("tab");
    const [active, setActive] = useState<"anomaly" | "graph">("anomaly");

    React.useEffect(() => {
        if (tab === "graph") setActive("graph");
        else if (tab === "anomaly") setActive("anomaly");
    }, [tab]);

    return (
        <div className="min-h-screen bg-background p-4 md:p-8 pt-4">
            <div className="mx-auto max-w-7xl space-y-6">
                <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground mb-2">
                    <ol className="flex items-center gap-1.5 list-none p-0">
                        <li><Link href="/" className="hover:text-[var(--re-brand)] transition-colors">Home</Link></li>
                        <li aria-hidden="true" className="text-muted-foreground/40">/</li>
                        <li><Link href="/tools" className="hover:text-[var(--re-brand)] transition-colors">Free Tools</Link></li>
                        <li aria-hidden="true" className="text-muted-foreground/40">/</li>
                        <li aria-current="page" className="font-medium text-foreground">
                            {active === "graph" ? "Supply Chain Knowledge Graph" : "Anomaly Detection Simulator"}
                        </li>
                    </ol>
                </nav>

                <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                    <div>
                        <div className="text-3xl font-semibold tracking-tight">
                            RegEngine • Unified FSMA Dashboard
                        </div>
                        <div className="mt-1 text-sm text-muted-foreground">
                            Technical demos for FSMA 204: Anomaly Simulation & Knowledge Graph.
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button
                            className={`rounded-2xl ${active === "anomaly" ? "" : "bg-muted text-foreground hover:bg-muted/80"}`}
                            onClick={() => setActive("anomaly")}
                        >
                            <AlertTriangle className="mr-2 h-4 w-4" />
                            Anomaly Simulator
                        </Button>
                        <Button
                            className={`rounded-2xl ${active === "graph" ? "" : "bg-muted text-foreground hover:bg-muted/80"}`}
                            onClick={() => setActive("graph")}
                        >
                            <Network className="mr-2 h-4 w-4" />
                            Knowledge Graph
                        </Button>
                    </div>
                </div>

                <AnimatePresence mode="wait">
                    {active === "anomaly" ? (
                        <motion.div
                            key="a"
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -10 }}
                        >
                            <AnomalyDetectionSimulator />
                        </motion.div>
                    ) : (
                        <motion.div
                            key="g"
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -10 }}
                        >
                            <SupplyChainKnowledgeGraphBuilder />
                        </motion.div>
                    )}
                </AnimatePresence>

                <div className="rounded-3xl border p-4 md:p-6">
                    <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                        <div>
                            <div className="text-sm font-medium">Compliance Note</div>
                            <div className="text-sm text-muted-foreground">
                                These demos showcase how RegEngine handles high-integrity data under 21 CFR Part 1.
                                Full production mode includes ERP connectors and immutable traceability packets.
                            </div>
                        </div>
                        <Badge variant="secondary" className="rounded-xl">Interactive Demo</Badge>
                    </div>
                </div>

                <RelatedTools
                    tools={FREE_TOOLS.filter(t => ['ftl-checker', 'roi-calculator', 'recall-readiness'].includes(t.id))}
                />
            </div>
        </div>
    );
}
