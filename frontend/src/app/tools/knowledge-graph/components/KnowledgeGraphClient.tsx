'use client';

import React from "react";
import { Network } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import dynamic from "next/dynamic";
import Link from "next/link";
import { RelatedTools } from "@/components/layout/related-tools";
import { FREE_TOOLS } from "@/lib/fsma-tools-data";
import { KnowledgeGraphErrorBoundary } from "./KnowledgeGraphErrorBoundary";

const SupplyChainKnowledgeGraphBuilder = dynamic(
    () => import("./KnowledgeGraph").then(mod => mod.SupplyChainKnowledgeGraphBuilder),
    { ssr: false }
);

export function KnowledgeGraphClient() {
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
                            Supply Chain Knowledge Graph
                        </li>
                    </ol>
                </nav>

                <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                    <div>
                        <div className="text-3xl font-semibold tracking-tight">
                            RegEngine • Supply Chain Knowledge Graph
                        </div>
                        <div className="mt-1 text-sm text-muted-foreground">
                            Interactive visual builder for designing FSMA 204 compliant supply chain networks.
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <Badge className="bg-[var(--re-brand)] rounded-xl py-1 px-3">
                            <Network className="mr-2 h-4 w-4 inline" />
                            Graph Editor Active
                        </Badge>
                    </div>
                </div>

                <div className="mt-6">
                    <KnowledgeGraphErrorBoundary>
                        <SupplyChainKnowledgeGraphBuilder />
                    </KnowledgeGraphErrorBoundary>
                </div>

                <div className="rounded-3xl border p-4 md:p-6 mt-8">
                    <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                        <div>
                            <div className="text-sm font-medium">Compliance Note</div>
                            <div className="text-sm text-muted-foreground">
                                This demo showcases how RegEngine handles high-integrity data under 21 CFR Part 1.
                                Full production mode includes ERP connectors and immutable traceability packets.
                            </div>
                        </div>
                        <Badge variant="secondary" className="rounded-xl">Interactive Demo</Badge>
                    </div>
                </div>

                <RelatedTools
                    tools={FREE_TOOLS.filter(t => ['fsma-unified', 'ftl-checker', 'cte-mapper'].includes(t.id))}
                />
            </div>
        </div>
    );
}
