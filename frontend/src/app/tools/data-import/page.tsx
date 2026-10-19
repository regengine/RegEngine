import { Metadata } from "next";
import { DataImportClient } from "./components/DataImportClient";
import { Suspense } from "react";
import { Container } from "@/components/layout/container";
import { JSONLD } from "@/components/seo/json-ld";
import { RelatedTools } from "@/components/tools/RelatedTools";
import { EmailGate } from "@/components/tools/EmailGate";
import { Skeleton } from "@/components/ui/skeleton";
import { filterExperimentalToolLinks } from "@/lib/experimental-features";

export const metadata: Metadata = {
    title: "FSMA 204 Data Import Hub | Upload CSV, IoT & Webhook Traceability Data | RegEngine",
    description: "Import FSMA 204 traceability data via CSV upload, IoT temperature logs, or webhook API. Supports Sensitech TempTale and all Critical Tracking Event (CTE) types with schema checks and field auto-mapping.",
    alternates: {
        canonical: "https://regengine.co/tools/data-import",
    },
    openGraph: {
        title: "FSMA 204 Data Import Hub | RegEngine",
        description: "Import traceability data via CSV, IoT logs, or webhook API with FSMA 204 schema checks. Free tool.",
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
};

function DataImportFallback() {
    return (
        <div className="min-h-screen bg-re-surface-base py-6 sm:py-8" aria-busy="true">
            <Container width="tool">
                <div className="mx-auto max-w-2xl text-center">
                    <h1 className="text-title text-re-text-primary">Data Import Hub</h1>
                    <p className="mx-auto mt-3 max-w-[70ch] text-ui text-re-text-secondary">Import your traceability data into RegEngine via CSV upload, XLSX spreadsheets, IoT temperature logs, or webhook API. Supports all FSMA 204 Critical Tracking Event (CTE) types with automatic validation and auto-cleaning of common formatting issues.</p>
                </div>
                <div className="mt-8 space-y-4">
                    <Skeleton className="h-10 w-1/3 rounded-md" />
                    <Skeleton className="h-64 w-full rounded-lg" />
                </div>
                <p className="mt-4 text-center text-small text-re-text-muted">
                    Loading import tools…
                </p>
            </Container>
        </div>
    );
}

export default function DataImportPage() {
    return (
        <EmailGate toolName="data-import">
            <>
                <Suspense fallback={<DataImportFallback />}>
                <JSONLD data={jsonLd} />
                <DataImportClient />
            </Suspense>
            <RelatedTools tools={filterExperimentalToolLinks([
                { href: "/tools/scan", title: "GS1 Barcode Scanner", description: "Scan barcodes to decode GTIN and lot codes directly into FSMA 204 traceability records." },
                { href: "/tools/label-scanner", title: "AI Label Scanner", description: "Upload a food label and AI extracts lot code, GTIN, and FSMA 204 Key Data Element (KDE) fields automatically." },
                { href: "/tools/export", title: "FDA-Oriented Export Generator", description: "Generate a verifiable records package from your traceability records." },
            ])} />
            </>
        </EmailGate>
    );
}
