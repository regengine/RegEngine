import { Metadata } from "next";
import { DataImportClient } from "./components/DataImportClient";
import { Suspense } from "react";
import { JSONLD } from "@/components/seo/json-ld";

export const metadata: Metadata = {
    title: "Data Import Hub | Upload CSV & IoT Data | RegEngine",
    description: "Import your traceability data into RegEngine via CSV upload, IoT temperature logs, or webhook API. Supports Sensitech TempTale and all FSMA 204 CTE types.",
    openGraph: {
        title: "Data Import Hub — RegEngine",
        description: "Get your supply chain data into RegEngine's traceability engine.",
        type: "website",
        url: "https://regengine.co/tools/data-import",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "RegEngine Data Import Hub",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Import traceability data via CSV, IoT logs, or API for FSMA 204 compliance.",
    "offers": {
        "@type": "Offer",
        "price": "0",
        "priceCurrency": "USD"
    },
};

export default function DataImportPage() {
    return (
        <Suspense fallback={
            <div className="min-h-screen bg-[var(--re-surface-base)] px-6 py-16">
                <div className="max-w-2xl mx-auto text-center">
                    <h1 className="text-2xl font-bold text-[var(--re-text-primary)] mb-3">Data Import Hub</h1>
                    <p className="text-sm text-[var(--re-text-muted)] max-w-lg mx-auto mb-4 leading-relaxed">Import your traceability data into RegEngine via CSV upload, XLSX spreadsheets, IoT temperature logs, or webhook API. Supports all FSMA 204 Critical Tracking Event types with automatic validation and auto-cleaning of common formatting issues.</p>
                    <div className="flex gap-2 items-center justify-center text-xs text-[var(--re-text-disabled)]">
                        <div className="w-3 h-3 rounded-full border-2 border-emerald-400 border-t-transparent animate-spin" />
                        Loading import tools…
                    </div>
                </div>
            </div>
        }>
            <JSONLD data={jsonLd} />
            <DataImportClient />
        </Suspense>
    );
}
